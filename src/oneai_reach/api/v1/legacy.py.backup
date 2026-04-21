import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

# Make sure we can import legacy scripts
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import state_manager
import kb_manager
from voice_config import get_voice_config, update_voice_config

router = APIRouter(tags=["legacy"])

# ── WA Numbers & Voice ───────────────────────────────────────────────────

@router.get("/voice-config/{session_name}")
async def api_voice_config_get(session_name: str):
    config = get_voice_config(session_name)
    if config is None:
        config = {
            "voice_enabled": False,
            "voice_reply_mode": "auto",
            "voice_language": "ms",
        }
    # Wrap in our standard format
    return {"status": "success", "data": config}

@router.post("/voice-config/{session_name}")
async def api_voice_config_update(session_name: str, request: Request):
    data = await request.json()
    voice_enabled = data.get("voice_enabled")
    voice_reply_mode = data.get("voice_reply_mode")
    voice_language = data.get("voice_language")

    ok = update_voice_config(
        session_name,
        voice_enabled=voice_enabled,
        voice_reply_mode=voice_reply_mode,
        voice_language=voice_language,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="update_failed")
    return {"status": "success", "data": {"ok": True}}

# ── Knowledge Base ───────────────────────────────────────────────────────

@router.get("/kb/{wa_number_id}")
async def api_kb_list(wa_number_id: str, category: Optional[str] = None):
    entries = state_manager.get_kb_entries(wa_number_id, category=category)
    return {"status": "success", "data": {"entries": entries, "count": len(entries)}}

@router.post("/kb/{wa_number_id}")
async def api_kb_add(wa_number_id: str, request: Request):
    data = await request.json()
    if not data.get("question") or not data.get("answer"):
        raise HTTPException(status_code=400, detail="question and answer required")
    entry_id = kb_manager.add_entry(
        wa_number_id=wa_number_id,
        question=data["question"],
        answer=data["answer"],
        category=data.get("category", "faq"),
        tags=data.get("tags", ""),
    )
    return JSONResponse(status_code=201, content={"status": "success", "data": {"ok": True, "entry_id": entry_id}})

@router.patch("/kb/entry/{entry_id}")
async def api_kb_update(entry_id: int, request: Request):
    data = await request.json()
    ok = kb_manager.update_entry(entry_id, **data)
    if not ok:
        raise HTTPException(status_code=404, detail="not_found")
    return {"status": "success", "data": {"ok": True}}

@router.delete("/kb/entry/{entry_id}")
async def api_kb_delete(entry_id: int):
    state_manager.delete_kb_entry(entry_id)
    return {"status": "success", "data": {"ok": True}}

@router.post("/kb/{wa_number_id}/import")
async def api_kb_import(wa_number_id: str, request: Request):
    data = await request.json()
    entries = data.get("entries", [])
    count = kb_manager.import_entries(wa_number_id, entries)
    return {"status": "success", "data": {"ok": True, "imported": count}}

@router.get("/kb/{wa_number_id}/export")
async def api_kb_export(wa_number_id: str):
    entries = kb_manager.export_entries(wa_number_id)
    return {"status": "success", "data": {"entries": entries, "count": len(entries)}}

# ── Conversations ────────────────────────────────────────────────────────

@router.get("/conversations")
async def api_conversations(wa_number_id: Optional[str] = None):
    convs = state_manager.get_all_conversation_stages(wa_number_id=wa_number_id)
    return {"status": "success", "data": {"conversations": convs, "count": len(convs)}}

@router.get("/conversations/{conv_id}/messages")
async def api_conversation_messages(conv_id: int, limit: int = 50):
    msgs = state_manager.get_conversation_messages(conv_id, limit=limit)
    return {"status": "success", "data": {"messages": msgs, "count": len(msgs)}}

@router.post("/conversations/{conv_id}/messages")
async def api_conversation_send(conv_id: int, request: Request):
    data = await request.json()
    text = data.get("message", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message required")
    msg_id = state_manager.add_conversation_message(
        conversation_id=conv_id,
        message_text=text,
        direction="out",
        message_type="text",
    )
    return JSONResponse(status_code=201, content={"status": "success", "data": {"ok": True, "message_id": msg_id}})

@router.patch("/conversations/{conv_id}/stage")
async def api_conversation_stage(conv_id: int, request: Request):
    data = await request.json()
    stage = data.get("stage")
    if not stage:
        raise HTTPException(status_code=400, detail="stage required")
    state_manager.set_conversation_stage(conv_id, stage)
    return {"status": "success", "data": {"ok": True}}

@router.patch("/conversations/{conv_id}/manual")
async def api_conversation_manual(conv_id: int, request: Request):
    data = await request.json()
    enabled = data.get("manual_mode", data.get("enabled", True))
    state_manager.set_manual_mode(conv_id, enabled)
    return {"status": "success", "data": {"ok": True, "manual_mode": enabled}}

@router.post("/conversations/{conv_id}/feedback")
async def api_conversation_feedback(conv_id: int, request: Request):
    data = await request.json()
    message_id = data.get("message_id")
    rating = data.get("rating")
    note = data.get("note", "")
    corrected = data.get("corrected_response", "")

    if not message_id or rating not in ("good", "bad"):
        raise HTTPException(status_code=400, detail="message_id and rating required")

    conn = state_manager._connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS admin_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                rating TEXT NOT NULL,
                note TEXT DEFAULT '',
                corrected_response TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            """INSERT INTO admin_feedback (conversation_id, message_id, rating, note, corrected_response)
               VALUES (?, ?, ?, ?, ?)""",
            (conv_id, message_id, rating, note, corrected),
        )

        if rating == "good":
            conn.execute(
                "UPDATE response_outcomes SET was_effective = 1, outcome_score = 1.0 WHERE conversation_id = ?",
                (conv_id,),
            )
        elif rating == "bad":
            conn.execute(
                "UPDATE response_outcomes SET was_effective = 0, outcome_score = 0.0 WHERE conversation_id = ?",
                (conv_id,),
            )
        conn.commit()
    finally:
        conn.close()

    return {"status": "success", "data": {"ok": True, "rating": rating, "note": note}}

@router.get("/conversations/{conv_id}/feedback")
async def api_conversation_feedback_get(conv_id: int):
    conn = state_manager._connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS admin_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                rating TEXT NOT NULL,
                note TEXT DEFAULT '',
                corrected_response TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        rows = conn.execute(
            "SELECT * FROM admin_feedback WHERE conversation_id = ? ORDER BY created_at DESC",
            (conv_id,),
        ).fetchall()
        return {"status": "success", "data": {"feedback": [dict(r) for r in rows]}}
    finally:
        conn.close()

# ── Pipeline / Auto-Learn ────────────────────────────────────────────────

@router.get("/pipeline/scripts")
async def api_pipeline_scripts():
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
    return {"status": "success", "data": {"scripts": PIPELINE_SCRIPTS}}

@router.get("/auto-learn/report")
async def api_auto_learn_report(session: Optional[str] = None):
    return {"status": "success", "data": {"report": "Auto-learn report generation stub"}}

@router.post("/auto-learn/improve")
async def api_auto_learn_improve(request: Request):
    return {"status": "success", "data": {"ok": True, "message": "Improvement triggered"}}

