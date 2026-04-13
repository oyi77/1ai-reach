"""Agent-facing control plane for 1ai-engage.

Provides structured operations for:
- querying funnel/lead state
- starting or previewing pipeline stages
- sending targeted outreach/closer actions
- inspecting runtime integrations (WAHA / brain)

This module is intentionally reusable from both a local CLI facade and an MCP
server so agents can control the system without scraping ad-hoc shell output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import brain_client  # noqa: E402
import state_manager  # noqa: E402
from config import (  # noqa: E402
    HUB_URL,
    LOOP_SLEEP_SECONDS,
    MIN_NEW_LEADS_THRESHOLD,
    WAHA_API_KEY,
    WAHA_SESSION,
    WAHA_URL,
)
from leads import FUNNEL_STAGES, load_leads  # noqa: E402
from senders import send_email, send_whatsapp  # noqa: E402

CONTROL_DIR = ROOT / ".agent-control"
LOGS_DIR = CONTROL_DIR / "logs"

_STAGE_TO_SCRIPT = {
    "strategy": "strategy_agent.py",
    "enricher": "enricher.py",
    "researcher": "researcher.py",
    "generator": "generator.py",
    "reviewer": "reviewer.py",
    "blaster": "blaster.py",
    "reply_tracker": "reply_tracker.py",
    "closer": "closer_agent.py",
    "followup": "followup.py",
    "sheets_sync": "sheets_sync.py",
    "orchestrator": "orchestrator.py",
    "autonomous_loop": "autonomous_loop.py",
    "cs_engine": "cs_engine.py",
    "warmcall_engine": "warmcall_engine.py",
    "conversation_cleanup": "conversation_cleanup.py",
}


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class JobRecord:
    job_id: str
    stage: str
    pid: int
    command: list[str]
    log_path: str
    created_at: str


def _ensure_control_dirs() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _is_pid_running(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        try:
            state = stat_path.read_text().split()[2]
            return state != "Z"
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _run_script(script: str, args: list[str] | None = None) -> CommandResult:
    cmd = [sys.executable, str(SCRIPTS_DIR / script)] + (args or [])
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return CommandResult(
        command=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def start_background_stage(stage: str, args: list[str] | None = None) -> dict[str, Any]:
    if stage not in _STAGE_TO_SCRIPT:
        raise ValueError(f"Unsupported stage: {stage}")
    _ensure_control_dirs()
    job_id = f"{stage}-{uuid4().hex[:12]}"
    log_path = LOGS_DIR / f"{job_id}.log"
    cmd = [sys.executable, str(SCRIPTS_DIR / _STAGE_TO_SCRIPT[stage])] + (args or [])

    if stage == "autonomous_loop":
        owner = job_id
        if not state_manager.acquire_control_lock("autonomous_loop", owner):
            raise ValueError("autonomous_loop is already owned by another running job")

    with open(log_path, "a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    job = asdict(
        JobRecord(
            job_id=job_id,
            stage=stage,
            pid=proc.pid,
            command=cmd,
            log_path=str(log_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    state_manager.create_control_job(
        job_id=job_id,
        stage=stage,
        pid=proc.pid,
        command=json.dumps(cmd),
        status="running",
        log_path=str(log_path),
    )
    state_manager.add_tool_audit(
        "start_background_stage",
        f"stage={stage}",
        payload=json.dumps({"job_id": job_id, "args": args or []}),
    )
    return {**job, "running": True}


def list_jobs() -> dict[str, Any]:
    items = []
    for job in state_manager.list_control_jobs(limit=500):
        pid = int(job["pid"])
        running = _is_pid_running(pid)
        if not running and job.get("status") == "running":
            state_manager.update_control_job(
                job["job_id"],
                status="finished",
                finished_at=datetime.now(timezone.utc).isoformat(),
                exit_code=0 if job.get("exit_code") is None else job.get("exit_code"),
            )
            if job.get("stage") == "autonomous_loop":
                state_manager.release_control_lock("autonomous_loop", job["job_id"])
            job = state_manager.get_control_job(job["job_id"]) or job
        job["running"] = running
        items.append(job)
    return {"count": len(items), "items": items}


def get_job(job_id: str, tail_lines: int = 100) -> dict[str, Any]:
    job = state_manager.get_control_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    pid = int(job["pid"])
    running = _is_pid_running(pid)
    if not running and job.get("status") == "running":
        state_manager.update_control_job(
            job_id,
            status="finished",
            finished_at=datetime.now(timezone.utc).isoformat(),
            exit_code=0 if job.get("exit_code") is None else job.get("exit_code"),
        )
        if job.get("stage") == "autonomous_loop":
            state_manager.release_control_lock("autonomous_loop", job_id)
        job = state_manager.get_control_job(job_id) or job
    log_path = Path(job["log_path"])
    log_tail = ""
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        log_tail = "\n".join(lines[-tail_lines:])
    job["running"] = running
    job["log_tail"] = log_tail
    return job


def stop_job(job_id: str) -> dict[str, Any]:
    job = state_manager.get_control_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    pid = int(job["pid"])
    running = _is_pid_running(pid)
    if running:
        os.killpg(pid, 15)
    state_manager.update_control_job(
        job_id,
        status="stopped",
        finished_at=datetime.now(timezone.utc).isoformat(),
        exit_code=-15 if running else job.get("exit_code"),
    )
    if job.get("stage") == "autonomous_loop":
        state_manager.release_control_lock("autonomous_loop", job_id)
    state_manager.add_tool_audit(
        "stop_job", f"job_id={job_id}", payload=json.dumps({"pid": pid})
    )
    return {"job_id": job_id, "pid": pid, "was_running": running}


def get_system_config() -> dict[str, Any]:
    return {
        "root": str(ROOT),
        "scripts_dir": str(SCRIPTS_DIR),
        "loop_sleep_seconds": LOOP_SLEEP_SECONDS,
        "min_new_leads_threshold": MIN_NEW_LEADS_THRESHOLD,
        "waha_url": WAHA_URL,
        "waha_session_preference": WAHA_SESSION,
        "waha_api_key_configured": bool(WAHA_API_KEY),
        "hub_url": HUB_URL,
        "brain_online": brain_client.is_online(),
    }


def get_funnel_summary() -> dict[str, Any]:
    counts = state_manager.count_by_status()
    ordered = {stage: counts.get(stage, 0) for stage in FUNNEL_STAGES}
    return {
        "counts": ordered,
        "total": sum(ordered.values()),
        "raw_counts": counts,
    }


def list_leads(status: str | None = None, limit: int = 100) -> dict[str, Any]:
    if status:
        rows = state_manager.get_leads_by_status(status)
    else:
        rows = state_manager.get_all_leads()
    rows = rows[:limit]
    return {
        "count": len(rows),
        "items": rows,
    }


def get_lead(lead_id: str) -> dict[str, Any]:
    lead = state_manager.get_lead_by_id(lead_id)
    if not lead:
        raise ValueError(f"Lead not found: {lead_id}")
    return {
        "lead": lead,
        "events": state_manager.get_event_logs(lead_id=lead_id, limit=100),
    }


def get_recent_events(limit: int = 100) -> dict[str, Any]:
    return {"count": limit, "items": state_manager.get_event_logs(limit=limit)}


def run_stage(
    stage: str,
    *,
    dry_run: bool = False,
    query: str | None = None,
    lead_id: str | None = None,
    location: str | None = None,
    count: int | None = None,
    vertical: str | None = None,
) -> dict[str, Any]:
    if stage not in _STAGE_TO_SCRIPT:
        raise ValueError(f"Unsupported stage: {stage}")

    args: list[str] = []
    if stage == "orchestrator":
        if not query:
            raise ValueError("query is required for orchestrator stage")
        args.append(query)
        if dry_run:
            args.append("--dry-run")
    elif stage == "autonomous_loop":
        if dry_run:
            args.append("--dry-run")
        args.append("--run-once")
    else:
        if dry_run and stage in {"strategy", "generator", "closer"}:
            args.append("--dry-run")
        if lead_id and stage in {"generator", "closer"}:
            args.extend(["--lead-id", lead_id])
        if stage == "strategy":
            if vertical:
                args.extend(["--vertical", vertical])
            if location:
                args.extend(["--location", location])
            if count is not None:
                args.extend(["--count", str(count)])

    result = _run_script(_STAGE_TO_SCRIPT[stage], args)
    return asdict(result)


def preview_autonomous_decision() -> dict[str, Any]:
    result = _run_script("autonomous_loop.py", ["--dry-run", "--run-once"])
    return asdict(result)


def send_test_email(to: str, subject: str, body: str) -> dict[str, Any]:
    ok = send_email(to, subject, body)
    return {"ok": ok, "to": to, "subject": subject}


def send_test_whatsapp(phone: str, message: str) -> dict[str, Any]:
    ok = send_whatsapp(phone, message)
    return {"ok": ok, "phone": phone}


def set_lead_status(lead_id: str, status: str, note: str = "") -> dict[str, Any]:
    state_manager.update_lead_status(lead_id, status)
    if note:
        state_manager.add_event_log(lead_id, "agent_status_update", note)
    state_manager.add_tool_audit(
        "set_lead_status",
        f"lead_id={lead_id}",
        payload=json.dumps({"status": status, "note": note}, ensure_ascii=False),
    )
    return {"ok": True, "lead_id": lead_id, "status": status}


def update_lead_fields(lead_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    if not fields:
        raise ValueError("fields must not be empty")
    state_manager.update_lead(lead_id, **fields)
    state_manager.add_event_log(
        lead_id, "agent_field_update", json.dumps(fields, ensure_ascii=False)
    )
    state_manager.add_tool_audit(
        "update_lead_fields",
        f"lead_id={lead_id}",
        payload=json.dumps(fields, ensure_ascii=False),
    )
    return {"ok": True, "lead_id": lead_id, "updated_fields": sorted(fields.keys())}


def inspect_integrations() -> dict[str, Any]:
    result: dict[str, Any] = {
        "brain_online": brain_client.is_online(),
        "waha": {
            "url": WAHA_URL,
            "api_key_configured": bool(WAHA_API_KEY),
            "preferred_session": WAHA_SESSION,
        },
    }
    if WAHA_API_KEY:
        try:
            r = requests.get(
                f"{WAHA_URL.rstrip('/')}/api/sessions",
                params={"all": "true"},
                headers={"X-Api-Key": WAHA_API_KEY},
                timeout=10,
            )
            result["waha"]["status_code"] = r.status_code
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    result["waha"]["sessions"] = [
                        {
                            "name": item.get("name"),
                            "status": item.get("status"),
                        }
                        for item in data
                    ]
        except Exception as exc:
            result["waha"]["error"] = str(exc)
    return result


def load_dataframe_snapshot(limit: int = 100) -> dict[str, Any]:
    df = load_leads()
    if df is None:
        return {"count": 0, "items": []}
    return {
        "count": min(len(df), limit),
        "columns": list(df.columns),
        "items": df.head(limit).to_dict(orient="records"),
    }


def get_tool_audit(limit: int = 100) -> dict[str, Any]:
    return {"count": limit, "items": state_manager.get_tool_audit(limit=limit)}


# ---------------------------------------------------------------------------
# Session management (wa_manager)
# ---------------------------------------------------------------------------

try:
    import wa_manager as _wa_manager
except ImportError:
    _wa_manager = None  # type: ignore[assignment]


def list_wa_sessions() -> dict[str, Any]:
    """List all WhatsApp sessions with WAHA + DB status."""
    if _wa_manager is None:
        return {"error": "wa_manager not available"}
    return {"sessions": _wa_manager.list_sessions()}


def create_wa_session(
    session_name: str,
    phone: str = "",
    label: str = "",
    mode: str = "cs",
    persona: str = "",
) -> dict[str, Any]:
    """Create a new WhatsApp session in WAHA + local DB."""
    if _wa_manager is None:
        return {"error": "wa_manager not available"}
    return _wa_manager.create_session(
        session_name, phone=phone, label=label, mode=mode, persona=persona
    )


def delete_wa_session(session_name: str) -> dict[str, Any]:
    """Delete a WhatsApp session from WAHA + local DB."""
    if _wa_manager is None:
        return {"error": "wa_manager not available"}
    ok = _wa_manager.delete_session(session_name)
    return {"ok": ok, "session_name": session_name}


def get_wa_session_status(session_name: str) -> dict[str, Any]:
    """Get WAHA status for a session."""
    if _wa_manager is None:
        return {"error": "wa_manager not available"}
    return _wa_manager.get_session_status(session_name)


def get_wa_qr_code(session_name: str) -> dict[str, Any]:
    """Get QR code for a session, returned as base64 image."""
    import base64

    if _wa_manager is None:
        return {"error": "wa_manager not available"}
    data = _wa_manager.get_qr_code(session_name)
    if isinstance(data, bytes):
        return {
            "ok": True,
            "session_name": session_name,
            "qr_base64": base64.b64encode(data).decode("ascii"),
            "content_type": "image/png",
        }
    return {"ok": False, "session_name": session_name, "error": str(data)}


# ---------------------------------------------------------------------------
# Knowledge Base (kb_manager)
# ---------------------------------------------------------------------------

try:
    import kb_manager as _kb_manager
except ImportError:
    _kb_manager = None  # type: ignore[assignment]


def list_kb_entries(wa_number_id: str, category: str | None = None) -> dict[str, Any]:
    """List KB entries for a WA number, optionally filtered by category."""
    if _kb_manager is None:
        return {"error": "kb_manager not available"}
    entries = _kb_manager.get_entries(wa_number_id, category)
    return {"count": len(entries), "entries": entries}


def add_kb_entry(
    wa_number_id: str,
    category: str,
    question: str,
    answer: str,
    tags: str = "",
) -> dict[str, Any]:
    """Add a KB entry and return the new entry id."""
    if _kb_manager is None:
        return {"error": "kb_manager not available"}
    entry_id = _kb_manager.add_entry(
        wa_number_id, category, question, answer, tags=tags
    )
    return {"ok": True, "entry_id": entry_id}


def search_kb(wa_number_id: str, query: str) -> dict[str, Any]:
    """FTS5 search KB entries."""
    if _kb_manager is None:
        return {"error": "kb_manager not available"}
    results = _kb_manager.search(wa_number_id, query)
    return {"count": len(results), "results": results}


def delete_kb_entry(entry_id: int) -> dict[str, Any]:
    """Delete a KB entry by ID."""
    if _kb_manager is None:
        return {"error": "kb_manager not available"}
    ok = _kb_manager.delete_entry(entry_id)
    return {"ok": ok, "entry_id": entry_id}


def seed_kb(wa_number_id: str) -> dict[str, Any]:
    """Seed default BerkahKarya FAQ entries for a WA number."""
    if _kb_manager is None:
        return {"error": "kb_manager not available"}
    count = _kb_manager.seed_default_kb(wa_number_id)
    return {"ok": True, "seeded_count": count, "wa_number_id": wa_number_id}


# ---------------------------------------------------------------------------
# Conversation management (conversation_tracker)
# ---------------------------------------------------------------------------

try:
    import conversation_tracker as _conv_tracker
except ImportError:
    _conv_tracker = None  # type: ignore[assignment]


def list_active_conversations(wa_number_id: str | None = None) -> dict[str, Any]:
    """List active conversations, optionally filtered by WA number."""
    if _conv_tracker is None:
        return {"error": "conversation_tracker not available"}
    convs = _conv_tracker.get_active_conversations(wa_number_id)
    return {"count": len(convs), "conversations": convs}


def get_conversation_history(conversation_id: int, limit: int = 50) -> dict[str, Any]:
    """Get message history for a conversation."""
    if _conv_tracker is None:
        return {"error": "conversation_tracker not available"}
    messages = _conv_tracker.get_messages(conversation_id, limit=limit)
    return {"count": len(messages), "messages": messages}


def resolve_conversation(conversation_id: int) -> dict[str, Any]:
    """Mark a conversation as resolved."""
    if _conv_tracker is None:
        return {"error": "conversation_tracker not available"}
    ok = _conv_tracker.update_status(conversation_id, "resolved")
    return {"ok": ok, "conversation_id": conversation_id, "status": "resolved"}


def escalate_conversation(conversation_id: int, reason: str) -> dict[str, Any]:
    """Escalate a conversation with a reason (triggers Telegram alert)."""
    if _conv_tracker is None:
        return {"error": "conversation_tracker not available"}
    ok = _conv_tracker.escalate(conversation_id, reason)
    return {"ok": ok, "conversation_id": conversation_id, "reason": reason}


# ---------------------------------------------------------------------------
# Warm call (warmcall_engine — may not exist yet)
# ---------------------------------------------------------------------------

try:
    import warmcall_engine as _warmcall_engine
except ImportError:
    _warmcall_engine = None  # type: ignore[assignment]


def start_warmcall(
    phone: str,
    name: str,
    context: str,
    session_name: str | None = None,
) -> dict[str, Any]:
    """Start a warm-call sequence for a contact."""
    if _warmcall_engine is None:
        return {"error": "warmcall_engine not available"}
    return _warmcall_engine.start_sequence(
        phone, name, context, session_name=session_name
    )


def get_due_warmcall_followups() -> dict[str, Any]:
    """Get warm-call follow-ups that are due."""
    if _warmcall_engine is None:
        return {"error": "warmcall_engine not available"}
    followups = _warmcall_engine.get_due_followups()
    return {"count": len(followups), "followups": followups}
