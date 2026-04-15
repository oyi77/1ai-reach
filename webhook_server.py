#!/usr/bin/env python3
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS

SCRIPT_DIR = Path(__file__).parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cs_engine import handle_inbound_message
from state_manager import (
    init_db,
    add_event_log,
    get_wa_numbers,
    get_wa_number_by_session,
    count_by_status,
    get_all_leads,
    get_lead_by_id,
    update_lead,
    update_lead_status,
    get_event_logs,
    get_kb_entries,
    search_kb,
    delete_kb_entry,
    get_or_create_conversation,
    get_conversation_messages,
    get_all_conversation_stages,
    update_conversation_status,
    set_conversation_stage,
    set_manual_mode,
    is_manual_mode,
    add_conversation_message,
)
from kb_manager import (
    add_entry as kb_add_entry,
    update_entry as kb_update_entry,
    import_entries,
    export_entries,
)

app = Flask(__name__)
CORS(app, origins=["*"])
_processed_messages = set()

init_db()


# ── WAHA Webhook ──────────────────────────────────────────────────────────


@app.route("/webhook/waha", methods=["POST"])
def webhook_waha():
    try:
        data = request.get_json() or {}
        event = data.get("event", "")
        session = data.get("session", "")
        payload = data.get("payload") or data.get("data", {})
        print(f"[WEBHOOK] Event: {event}, Session: {session}")

        if event in ("message", "message.any"):
            sender = payload.get("from") or payload.get("chatId", "")
            body_text = payload.get("body", "")
            msg_type = payload.get("type", "chat")
            from_me = payload.get("fromMe", False)
            msg_id = payload.get("id", "")

            global _processed_messages
            if msg_id and msg_id in _processed_messages:
                return jsonify({"status": "ok", "skipped": "duplicate"})
            if msg_id:
                _processed_messages.add(msg_id)
                if len(_processed_messages) > 1000:
                    _processed_messages.clear()

            if from_me:
                return jsonify({"status": "ok", "skipped": "from_me"})

            # Skip group messages
            if "@g.us" in sender:
                return jsonify({"status": "ok", "skipped": "group_message"})

            if msg_type not in ("chat", "image", "video", "document", "audio", "ptt"):
                return jsonify({"status": "ok", "skipped": f"type:{msg_type}"})

            if msg_type in ("image", "video", "document", "audio", "ptt"):
                media_labels = {
                    "image": "[Customer mengirim gambar]",
                    "video": "[Customer mengirim video]",
                    "document": "[Customer mengirim dokumen]",
                    "audio": "[Customer mengirim voice note]",
                    "ptt": "[Customer mengirim voice note]",
                }
                body_text = media_labels.get(msg_type, "[Customer mengirim media]")
            if not sender:
                return jsonify({"status": "ok", "skipped": "no_sender"})
            if not body_text:
                body_text = "Halo"

            wa_number = get_wa_number_by_session(session)
            if not wa_number:
                return jsonify({"status": "error", "message": "session_not_found"}), 404

            # Skip auto-reply if manual mode is enabled
            wa_number_id = wa_number.get("id", session)
            if is_manual_mode_active(wa_number_id, sender):
                add_conversation_message(
                    conversation_id=_get_or_create_conv_id(wa_number_id, sender),
                    message_text=body_text,
                    direction="in",
                    message_type=msg_type,
                )
                return jsonify({"status": "ok", "skipped": "manual_mode"})

            result = handle_inbound_message(
                wa_number_id=wa_number_id,
                contact_phone=sender,
                message_text=body_text,
                session_name=session,
            )
            return jsonify(
                {
                    "status": "ok",
                    "action": result.get("action"),
                    "response_sent": (result.get("response", "")[:100] + "...")
                    if result.get("response")
                    else "",
                }
            )

        return jsonify({"status": "ok", "event": event})
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Health ────────────────────────────────────────────────────────────────


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "1ai-engage-api", "version": "2.0.0"})


# ── Funnel / Leads ───────────────────────────────────────────────────────


@app.route("/api/funnel", methods=["GET"])
def api_funnel():
    counts = count_by_status()
    return jsonify({"counts": counts, "total": sum(counts.values())})


@app.route("/api/leads", methods=["GET"])
def api_leads():
    status = request.args.get("status")
    leads = get_all_leads()
    if status:
        leads = [l for l in leads if l.get("status") == status]
    return jsonify({"leads": leads, "count": len(leads)})


@app.route("/api/leads/<lead_id>", methods=["GET"])
def api_lead_detail(lead_id):
    lead = get_lead_by_id(lead_id)
    if not lead:
        return jsonify({"error": "not_found"}), 404
    return jsonify(lead)


@app.route("/api/leads/<lead_id>", methods=["PATCH"])
def api_lead_update(lead_id):
    data = request.get_json() or {}
    if "status" in data:
        update_lead_status(lead_id, data.pop("status"))
    if data:
        update_lead(lead_id, **data)
    return jsonify({"ok": True})


# ── WA Numbers ───────────────────────────────────────────────────────────


@app.route("/api/wa-numbers", methods=["GET"])
def api_wa_numbers():
    numbers = get_wa_numbers()
    return jsonify({"numbers": numbers, "count": len(numbers)})


# ── Knowledge Base ───────────────────────────────────────────────────────


@app.route("/api/kb/<wa_number_id>", methods=["GET"])
def api_kb_list(wa_number_id):
    category = request.args.get("category")
    entries = get_kb_entries(wa_number_id, category=category)
    return jsonify({"entries": entries, "count": len(entries)})


@app.route("/api/kb/<wa_number_id>", methods=["POST"])
def api_kb_add(wa_number_id):
    data = request.get_json() or {}
    required = ["question", "answer"]
    if not all(data.get(k) for k in required):
        return jsonify({"error": "question and answer required"}), 400
    entry_id = kb_add_entry(
        wa_number_id=wa_number_id,
        question=data["question"],
        answer=data["answer"],
        category=data.get("category", "faq"),
        tags=data.get("tags", ""),
    )
    return jsonify({"ok": True, "entry_id": entry_id}), 201


@app.route("/api/kb/entry/<int:entry_id>", methods=["PATCH"])
def api_kb_update(entry_id):
    data = request.get_json() or {}
    ok = kb_update_entry(entry_id, **data)
    if not ok:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"ok": True})


@app.route("/api/kb/entry/<int:entry_id>", methods=["DELETE"])
def api_kb_delete(entry_id):
    delete_kb_entry(entry_id)
    return jsonify({"ok": True})


@app.route("/api/kb/<wa_number_id>/search", methods=["GET"])
def api_kb_search(wa_number_id):
    q = request.args.get("q", "")
    limit = int(request.args.get("limit", 5))
    results = search_kb(wa_number_id, q, limit=limit)
    return jsonify({"results": results, "count": len(results)})


@app.route("/api/kb/<wa_number_id>/import", methods=["POST"])
def api_kb_import(wa_number_id):
    data = request.get_json() or {}
    entries = data.get("entries", [])
    count = import_entries(wa_number_id, entries)
    return jsonify({"ok": True, "imported": count})


@app.route("/api/kb/<wa_number_id>/export", methods=["GET"])
def api_kb_export(wa_number_id):
    entries = export_entries(wa_number_id)
    return jsonify({"entries": entries, "count": len(entries)})


# ── Conversations ────────────────────────────────────────────────────────


@app.route("/api/conversations", methods=["GET"])
def api_conversations():
    wa_filter = request.args.get("wa_number_id")
    convs = get_all_conversation_stages(wa_number_id=wa_filter)
    return jsonify({"conversations": convs, "count": len(convs)})


@app.route("/api/conversations/<int:conv_id>/messages", methods=["GET"])
def api_conversation_messages(conv_id):
    limit = int(request.args.get("limit", 50))
    msgs = get_conversation_messages(conv_id, limit=limit)
    return jsonify({"messages": msgs, "count": len(msgs)})


@app.route("/api/conversations/<int:conv_id>/messages", methods=["POST"])
def api_conversation_send(conv_id):
    data = request.get_json() or {}
    text = data.get("message", "").strip()
    if not text:
        return jsonify({"error": "message required"}), 400
    msg_id = add_conversation_message(
        conversation_id=conv_id,
        message_text=text,
        direction="out",
        message_type="text",
    )
    return jsonify({"ok": True, "message_id": msg_id}), 201


@app.route("/api/conversations/<int:conv_id>/stage", methods=["PATCH"])
def api_conversation_stage(conv_id):
    data = request.get_json() or {}
    stage = data.get("stage")
    if not stage:
        return jsonify({"error": "stage required"}), 400
    set_conversation_stage(conv_id, stage)
    return jsonify({"ok": True})


@app.route("/api/conversations/<int:conv_id>/manual", methods=["PATCH"])
def api_conversation_manual(conv_id):
    data = request.get_json() or {}
    enabled = data.get("manual_mode", data.get("enabled", True))
    set_manual_mode(conv_id, enabled)
    return jsonify({"ok": True, "manual_mode": enabled})


# ── Event Log ────────────────────────────────────────────────────────────


@app.route("/api/events", methods=["GET"])
def api_events():
    lead_id = request.args.get("lead_id")
    limit = int(request.args.get("limit", 100))
    logs = get_event_logs(lead_id=lead_id, limit=limit)
    return jsonify({"events": logs, "count": len(logs)})


# ── Service Control ──────────────────────────────────────────────────────


@app.route("/api/services", methods=["GET"])
def api_services():
    services = []
    checks = [
        {
            "key": "webhook",
            "label": "Webhook Server",
            "pattern": "webhook_server.py",
            "port": 8766,
        },
        {
            "key": "autonomous",
            "label": "Autonomous Loop",
            "pattern": "autonomous_loop.py",
        },
        {
            "key": "dashboard",
            "label": "Dashboard",
            "pattern": "next start",
            "port": 8502,
        },
        {"key": "tunnel", "label": "Cloudflare Tunnel", "pattern": "cloudflared"},
    ]
    for svc in checks:
        running = _is_process_running(svc["pattern"])
        pid = _get_pid(svc["pattern"]) if running else None
        info = {
            "key": svc["key"],
            "label": svc["label"],
            "running": running,
            "pid": pid,
        }
        if svc.get("port"):
            info["port"] = svc["port"]
        services.append(info)
    return jsonify({"services": services})


@app.route("/api/services/autonomous/start", methods=["POST"])
def api_autonomous_start():
    data = request.get_json() or {}
    dry_run = data.get("dry_run", False)
    run_once = data.get("run_once", False)
    if _is_process_running("autonomous_loop.py"):
        return jsonify({"error": "already_running"}), 409

    cmd = [sys.executable, str(SCRIPT_DIR / "autonomous_loop.py")]
    if dry_run:
        cmd.append("--dry-run")
    if run_once:
        cmd.append("--run-once")

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "autonomous.log"

    try:
        with open(log_file, "a") as lf:
            lf.write(
                f"\n[{datetime.now().isoformat()}] Starting loop (dry_run={dry_run}, run_once={run_once})\n"
            )
            subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=str(Path(__file__).parent),
            )
        return jsonify({"ok": True, "message": "Autonomous loop started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/services/autonomous/stop", methods=["POST"])
def api_autonomous_stop():
    try:
        subprocess.run(
            ["pkill", "-f", "autonomous_loop.py"], capture_output=True, timeout=5
        )
        return jsonify({"ok": True, "message": "Autonomous loop stopped"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/services/webhook/restart", methods=["POST"])
def api_webhook_restart():
    return jsonify(
        {
            "ok": False,
            "message": "Cannot restart self — use systemd: sudo systemctl restart 1ai-engage-mcp",
        }
    )


# ── Pipeline Control ─────────────────────────────────────────────────────

PIPELINE_SCRIPTS = [
    {"key": "scrape", "script": "scraper.py"},
    {"key": "enrich", "script": "enricher.py"},
    {"key": "research", "script": "researcher.py"},
    {"key": "generate", "script": "generator.py"},
    {"key": "review", "script": "reviewer.py"},
    {"key": "blast", "script": "blaster.py"},
    {"key": "track", "script": "reply_tracker.py"},
    {"key": "followup", "script": "followup.py"},
    {"key": "sync", "script": "sheets_sync.py"},
]


@app.route("/api/pipeline/scripts", methods=["GET"])
def api_pipeline_scripts():
    return jsonify({"scripts": PIPELINE_SCRIPTS})


@app.route("/api/pipeline/run", methods=["POST"])
def api_pipeline_run():
    data = request.get_json() or {}
    script = data.get("script", "")
    query = data.get("query", "")
    valid = [s["script"] for s in PIPELINE_SCRIPTS]
    if script not in valid:
        return jsonify({"error": f"invalid script. valid: {valid}"}), 400

    cmd = [sys.executable, str(SCRIPT_DIR / script)]
    if script == "scraper.py" and query:
        cmd.append(query)

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"pipeline_{script}.log"

    try:
        with open(log_file, "a") as lf:
            proc = subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(Path(__file__).parent.parent),
            )
        return jsonify({"ok": True, "pid": proc.pid, "log": str(log_file)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Logs ─────────────────────────────────────────────────────────────────


@app.route("/api/logs/<name>", methods=["GET"])
def api_logs(name):
    lines = int(request.args.get("lines", 50))
    log_dir = Path(__file__).parent / "logs"
    log_file = log_dir / f"{name}.log"
    if not log_file.exists():
        return jsonify(
            {
                "error": "log not found",
                "available": [p.stem for p in log_dir.glob("*.log")],
            }
        ), 404
    try:
        text = log_file.read_text(errors="replace")
        tail = text.strip().splitlines()[-lines:]
        return jsonify({"lines": tail, "count": len(tail), "file": str(log_file)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Helpers ──────────────────────────────────────────────────────────────


def _is_process_running(pattern: str) -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _get_pid(pattern: str) -> int | None:
    try:
        r = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip().splitlines()[0])
        return None
    except Exception:
        return None


def is_manual_mode_active(wa_number_id: str, contact_phone: str) -> bool:
    try:
        convs = get_all_conversation_stages(wa_number_id=wa_number_id)
        for c in convs:
            if c.get("contact_phone") == contact_phone and c.get("manual_mode"):
                return True
    except Exception:
        pass
    return False


def _get_or_create_conv_id(wa_number_id: str, contact_phone: str) -> int:
    return get_or_create_conversation(wa_number_id, contact_phone, engine_mode="cs")


if __name__ == "__main__":
    print("Starting 1ai-engage API Server on port 8766...")
    app.run(host="0.0.0.0", port=8766, debug=False, threaded=True)
