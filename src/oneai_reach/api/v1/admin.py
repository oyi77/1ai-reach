"""Admin control endpoints for manual conversation management.

Provides emergency controls for stopping/pausing conversations and monitoring
active conversation state. Part of the infinite loop prevention system.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field

from oneai_reach.api.dependencies import verify_api_key

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(verify_api_key)],
)

# Global pause flag for CS engine
_PAUSE_CS_ENGINE = False


class ConversationInfo(BaseModel):
    """Active conversation information."""

    conversation_id: int
    wa_number_id: str
    contact_phone: str
    message_count: int
    last_message_time: Optional[str] = None
    status: str = "active"
    engine_mode: str = "cs"


class AdminResponse(BaseModel):
    status: str
    message: str

import os
import subprocess
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
_LOGS_DIR = _ROOT_DIR / "logs"

_SYSTEMD_UNITS = {
    "dashboard": "1ai-reach-dashboard",
    "api": "1ai-reach-api",
    "mcp": "1ai-reach-mcp",
    "webhook": "1ai-reach-mcp",
    "gmaps-scraper": "gmaps-scraper",
}

_LABELS = {
    "dashboard": "Dashboard",
    "api": "API Server",
    "mcp": "MCP / Webhook",
    "gmaps-scraper": "Google Maps Scraper",
    "oneai_reach_api_v1_webhooks": "Webhook/API",
    "oneai_reach_application_outreach_scraper_service": "Scraper",
    "oneai_reach_application_outreach_enricher_service": "Enricher",
    "oneai_reach_application_outreach_researcher_service": "Researcher",
    "oneai_reach_application_outreach_generator_service": "Generator",
    "oneai_reach_application_outreach_blaster_service": "Blaster",
    "oneai_reach_application_outreach_reviewer_service": "Reviewer",
    "oneai_reach_application_outreach_orchestrator_service": "Orchestrator",
    "oneai_reach_application_outreach_followup_service": "Follow-up",
    "oneai_reach_application_outreach_reply_tracker_service": "Reply Tracker",
    "oneai_reach_application_customer_service_cs_engine_service": "CS Engine",
    "oneai_reach_application_customer_service_conversation_service": "Conversation Service",
    "oneai_reach_application_customer_service_analytics_service": "Analytics Service",
}


class LogSource(BaseModel):
    value: str
    label: str
    source: str


class LogSourceResponse(BaseModel):
    sources: List[LogSource]


def _check_journal(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["journalctl", "--user", "-u", unit, "-n", "1", "--no-pager", "--quiet"],
            capture_output=True, text=True, timeout=3,
        )
        return bool(result.stdout.strip())
    except Exception as e:
        logger.warning(f"journalctl check failed for {unit}: {e}")
        return False


@router.get("/logs", response_model=LogSourceResponse)
async def list_log_sources() -> LogSourceResponse:
    sources = []

    for name, label in _LABELS.items():
        log_file = _LOGS_DIR / f"{name}.log"
        fallback = _ROOT_DIR / ".agent-control" / "logs" / f"{name}.log"

        for candidate in [log_file, fallback]:
            if candidate.exists() and candidate.stat().st_size > 0:
                sources.append(LogSource(value=name, label=label, source=f"file:{candidate.name}"))
                break
        else:
            unit = _SYSTEMD_UNITS.get(name)
            if unit and _check_journal(unit):
                sources.append(LogSource(value=name, label=label, source=f"journal:{unit}"))

    return LogSourceResponse(sources=sources)

class LogResponse(BaseModel):
    lines: List[str]
    count: int
    file: str

@router.get("/logs/{name}", response_model=LogResponse)
async def get_logs(name: str, lines: int = 50) -> LogResponse:
    log_file = _LOGS_DIR / f"{name}.log"
    fallback = _ROOT_DIR / ".agent-control" / "logs" / f"{name}.log"

    for candidate in [log_file, fallback]:
        if candidate.exists() and candidate.stat().st_size > 0:
            try:
                text = candidate.read_text(errors="replace")
                tail = text.strip().splitlines()[-lines:]
                if tail:
                    return LogResponse(lines=tail, count=len(tail), file=str(candidate))
            except Exception as e:
                logger.warning(f"log read failed for {candidate}: {e}")

    unit = _SYSTEMD_UNITS.get(name)
    if not unit:
        safe = name.replace("/", "").replace("..", "")
        unit = f"{safe}" if "1ai-reach" in safe or "gmaps" in safe else f"1ai-reach-{safe}"

    try:
        result = subprocess.run(
            ["journalctl", "--user", "-u", unit, "-n", str(lines), "--no-pager", "--output=short-iso"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            j_lines = result.stdout.strip().splitlines()
            return LogResponse(lines=j_lines, count=len(j_lines), file=f"journal:{unit}")
    except Exception as e:
        logger.warning(f"journalctl read failed for {unit}: {e}")

    try:
        result = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "--output=short-iso"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            j_lines = result.stdout.strip().splitlines()
            return LogResponse(lines=j_lines, count=len(j_lines), file=f"system-journal:{unit}")
    except Exception as e:
        logger.warning(f"system journalctl read failed for {unit}: {e}")

    return LogResponse(lines=["(no logs available)"], count=0, file=f"none:{name}")
    data: Optional[Dict[str, Any]] = None


def get_pause_flag() -> bool:
    """Get current pause flag state (for CS engine integration)."""
    return _PAUSE_CS_ENGINE


@router.get("/conversations", response_model=List[ConversationInfo])
async def list_conversations() -> List[ConversationInfo]:
    """List all active conversations with message counts.

    Returns conversation details including message counts and last activity
    for monitoring and debugging purposes.
    """
    try:
        from oneai_reach.infrastructure.legacy import conversation_tracker

        convs = conversation_tracker.get_active_conversations()

        result = []
        for conv in convs:
            # Skip conversations with missing wa_number_id (data integrity issue)
            wa_number_id = conv.get("wa_number_id")
            if wa_number_id is None:
                wa_number_id = "unknown"

            result.append(
                ConversationInfo(
                    conversation_id=conv.get("id", 0),
                    wa_number_id=wa_number_id,
                    contact_phone=conv.get("contact_phone", ""),
                    message_count=conv.get("message_count", 0),
                    last_message_time=conv.get("last_message_at"),
                    status=conv.get("status", "active"),
                    engine_mode=conv.get("engine_mode", "cs"),
                )
            )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list conversations: {str(e)}"
        )


@router.post("/conversations/{conv_id}/stop", response_model=AdminResponse)
async def stop_conversation(conv_id: int) -> AdminResponse:
    """Force stop a specific conversation.

    Marks the conversation as resolved and clears its message counter.
    Use this to manually intervene when a conversation is stuck in a loop.

    Args:
        conv_id: Conversation ID to stop
    """
    try:
        from oneai_reach.infrastructure.legacy import conversation_tracker

        success = conversation_tracker.update_status(conv_id, "resolved")

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conv_id} not found or already stopped",
            )

        return AdminResponse(
            status="success",
            message=f"Conversation {conv_id} stopped successfully",
            data={"conversation_id": conv_id, "new_status": "resolved"},
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop conversation: {str(e)}"
        )


@router.post("/pause", response_model=AdminResponse)
async def pause_cs_engine() -> AdminResponse:
    """Pause all autonomous CS engine responses.

    Sets a global flag that blocks all CS engine processing.
    Use this as an emergency stop for all automated responses.
    """
    global _PAUSE_CS_ENGINE
    _PAUSE_CS_ENGINE = True

    return AdminResponse(
        status="success",
        message="CS engine paused - all autonomous responses blocked",
        data={"paused": True},
    )


@router.post("/resume", response_model=AdminResponse)
async def resume_cs_engine() -> AdminResponse:
    """Resume CS engine responses.

    Clears the global pause flag to allow normal CS engine operation.
    """
    global _PAUSE_CS_ENGINE
    _PAUSE_CS_ENGINE = False

    return AdminResponse(
        status="success",
        message="CS engine resumed - autonomous responses enabled",
        data={"paused": False},
    )


class ServiceStatus(BaseModel):
    """Service status information."""

    key: str
    label: str
    running: bool
    pid: Optional[int] = None
    port: Optional[int] = None


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get service status list.

    Returns status of webhook, autonomous loop, and dashboard services.
    """
    try:
        import subprocess

        from oneai_reach.infrastructure.legacy import agent_control

        services = []
        
        webhook_running = False
        webhook_pid = None
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", 8766))
            sock.close()
            webhook_running = result == 0

            if webhook_running:
                uid = os.getuid()
                env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{uid}"}
                pid_result = subprocess.run(
                    ["systemctl", "--user", "show", "1ai-reach-mcp", "--property=MainPID"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=env,
                )
                if pid_result.returncode == 0:
                    pid_str = pid_result.stdout.strip().split("=")[-1]
                    webhook_pid = int(pid_str) if pid_str.isdigit() else None
        except Exception as e:
            logger.warning(f"webhook pid lookup failed: {e}")
        
        services.append(ServiceStatus(
            key="webhook",
            label="Webhook/MCP Server",
            running=webhook_running,
            pid=webhook_pid,
            port=8766,
        ))
        
        autonomous_job = None
        if agent_control:
            try:
                jobs_result = agent_control.list_jobs()
                for job in jobs_result.get("items", []):
                    if job.get("stage") == "autonomous_loop" and job.get("running"):
                        autonomous_job = job
                        break
            except Exception as e:
                logger.warning(f"autonomous job lookup failed: {e}")
        
        services.append(ServiceStatus(
            key="autonomous",
            label="Autonomous Loop",
            running=autonomous_job is not None,
            pid=autonomous_job.get("pid") if autonomous_job else None,
        ))
        
        dashboard_running = False
        dashboard_pid = None
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "1ai-reach-dashboard"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            dashboard_running = result.returncode == 0 and result.stdout.strip() == "active"
            
            if dashboard_running:
                pid_result = subprocess.run(
                    ["systemctl", "show", "1ai-reach-dashboard", "--property=MainPID"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if pid_result.returncode == 0:
                    pid_str = pid_result.stdout.strip().split("=")[-1]
                    dashboard_pid = int(pid_str) if pid_str.isdigit() else None
        except Exception as e:
            logger.warning(f"dashboard pid lookup failed: {e}")
        
        services.append(ServiceStatus(
            key="dashboard",
            label="Dashboard (Next.js)",
            running=dashboard_running,
            pid=dashboard_pid,
            port=8502,
        ))
        
        scraper_running = False
        scraper_pid = None
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "gmaps-scraper"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            scraper_running = result.returncode == 0 and result.stdout.strip() == "active"
            
            if scraper_running:
                pid_result = subprocess.run(
                    ["systemctl", "show", "gmaps-scraper", "--property=MainPID"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if pid_result.returncode == 0:
                    pid_str = pid_result.stdout.strip().split("=")[-1]
                    scraper_pid = int(pid_str) if pid_str.isdigit() else None
        except Exception as e:
            logger.warning(f"scraper pid lookup failed: {e}")
        
        services.append(ServiceStatus(
            key="gmaps_scraper",
            label="GMaps Scraper",
            running=scraper_running,
            pid=scraper_pid,
            port=8082,
        ))
        
        import os
        services.append(ServiceStatus(
            key="api",
            label="API Server (FastAPI)",
            running=True,
            pid=os.getpid(),
            port=8001,
        ))

        return {
            "services": [s.model_dump() for s in services],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


# WA Numbers Management
class WANumberResponse(BaseModel):
    """WA number information."""
    id: str
    session_name: str
    phone: Optional[str] = None
    label: Optional[str] = None
    mode: str = "cs"
    kb_enabled: bool = True
    auto_reply: bool = True
    persona: Optional[str] = None
    status: str = "inactive"
    webhook_url: Optional[str] = None


class WANumberUpdate(BaseModel):
    """WA number update request."""
    label: Optional[str] = None
    mode: Optional[str] = None
    kb_enabled: Optional[bool] = None
    auto_reply: Optional[bool] = None
    persona: Optional[str] = None
    status: Optional[str] = None


@router.get("/wa-numbers", response_model=List[WANumberResponse])
async def list_wa_numbers() -> List[WANumberResponse]:
    """List all WA numbers."""
    import sqlite3
    from pathlib import Path
    from oneai_reach.config.settings import get_settings
    
    settings = get_settings()
    db_path = settings.database.db_file
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, session_name, phone, label, mode, kb_enabled, auto_reply, persona, status, webhook_url
            FROM wa_numbers
            ORDER BY created_at DESC
        """)
        
        rows = cursor.fetchall()
    finally:
        conn.close()
    
    return [
        WANumberResponse(
            id=row["id"],
            session_name=row["session_name"],
            phone=row["phone"],
            label=row["label"],
            mode=row["mode"],
            kb_enabled=bool(row["kb_enabled"]),
            auto_reply=bool(row["auto_reply"]),
            persona=row["persona"],
            status=row["status"],
            webhook_url=row["webhook_url"]
        )
        for row in rows
    ]


@router.patch("/wa-numbers/{wa_number_id}", response_model=WANumberResponse)
async def update_wa_number(wa_number_id: str, update: WANumberUpdate) -> WANumberResponse:
    """Update WA number settings including persona."""
    import sqlite3
    from oneai_reach.config.settings import get_settings
    
    settings = get_settings()
    db_path = settings.database.db_file
    
    try:
        conn = sqlite3.connect(db_path)

    finally:
        conn.close()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    update_fields = []
    params = []
    
    if update.label is not None:
        update_fields.append("label = ?")
        params.append(update.label)
    if update.mode is not None:
        update_fields.append("mode = ?")
        params.append(update.mode)
    if update.kb_enabled is not None:
        update_fields.append("kb_enabled = ?")
        params.append(1 if update.kb_enabled else 0)
    if update.auto_reply is not None:
        update_fields.append("auto_reply = ?")
        params.append(1 if update.auto_reply else 0)
    if update.persona is not None:
        update_fields.append("persona = ?")
        params.append(update.persona)
    if update.status is not None:
        update_fields.append("status = ?")
        params.append(update.status)
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_fields.append("updated_at = datetime('now')")
    params.append(wa_number_id)
    
    query = f"UPDATE wa_numbers SET {', '.join(update_fields)} WHERE id = ?"
    
    try:
        cursor.execute(query, params)
        conn.commit()
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail=f"WA number {wa_number_id} not found")
        
        cursor.execute("""
            SELECT id, session_name, phone, label, mode, kb_enabled, auto_reply, persona, status, webhook_url
            FROM wa_numbers
            WHERE id = ?
        """, (wa_number_id,))
        
        row = cursor.fetchone()
        conn.close()

        if update.auto_reply is not None:
            try:
                ch_conn = sqlite3.connect(db_path)
                try:
                    phone = (row["phone"] if row and row["phone"] else "") or ""
                    session_name = (row["session_name"] if row and row["session_name"] else "") or ""
                    ch_conn.execute(
                        "UPDATE channels SET enabled = ?, updated_at = datetime('now') WHERE platform = 'whatsapp' AND (phone = ? OR label = ?)",
                        (1 if update.auto_reply else 0, phone, session_name),
                    )
                    ch_conn.commit()
                finally:
                    ch_conn.close()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to sync channels.enabled for WA number {wa_number_id}: {e}")

        return WANumberResponse(
            id=row["id"],
            session_name=row["session_name"],
            phone=row["phone"],
            label=row["label"],
            mode=row["mode"],
            kb_enabled=bool(row["kb_enabled"]),
            auto_reply=bool(row["auto_reply"]),
            persona=row["persona"],
            status=row["status"],
            webhook_url=row["webhook_url"]
        )
    except sqlite3.Error as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
