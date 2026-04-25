"""Conversation management API endpoints."""

import logging
import sqlite3
from typing import Optional
from urllib.parse import quote as url_quote

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from oneai_reach.config.settings import get_settings

import sys
from pathlib import Path

# Make sure we can import legacy scripts
_SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import state_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])


def _waha_targets():
    """Build WAHA API target list from settings, deduplicating URLs."""
    settings = get_settings()
    targets = []
    seen = set()
    for name, base_url, api_key in [
        ("WAHA", settings.waha.url, settings.waha.api_key),
        ("WAHA_DIRECT", settings.waha.direct_url, settings.waha.direct_api_key),
    ]:
        url = str(base_url or "").rstrip("/")
        key = str(api_key or "")
        if not url or (url, key) in seen:
            continue
        seen.add((url, key))
        targets.append((name, url, {"X-Api-Key": key, "Content-Type": "application/json"}))
    return targets


# ── List / New / Stop ────────────────────────────────────────────────

@router.get("")
async def api_conversations(wa_number_id: Optional[str] = None):
    """List all conversations, optionally filtered by WA number."""
    convs = state_manager.get_all_conversation_stages(wa_number_id=wa_number_id)
    logger.debug(f"LIST convs wa_number_id={wa_number_id} count={len(convs)}")
    return {"status": "success", "data": {"conversations": convs, "count": len(convs)}}


@router.post("/new")
async def api_new_conversation(request: Request):
    """Start a new conversation with a phone number."""
    data = await request.json()
    wa_number_id = data.get("wa_number_id", "").strip()
    phone = data.get("phone", "").strip()
    message = data.get("message", "").strip()

    if not wa_number_id or not phone or not message:
        raise HTTPException(status_code=400, detail="wa_number_id, phone, and message required")

    conn = state_manager._connect()
    conn.row_factory = sqlite3.Row

    wa_num = conn.execute("SELECT session_name, phone FROM wa_numbers WHERE id = ?", (wa_number_id,)).fetchone()
    if not wa_num:
        conn.close()
        raise HTTPException(status_code=404, detail="WA number not found")

    conv_id = conn.execute("""
        INSERT INTO conversations (wa_number_id, contact_phone, status, engine_mode, message_count)
        VALUES (?, ?, 'active', 'manual', 1)
    """, (wa_number_id, f"{phone}@c.us")).lastrowid
    conn.commit()

    conn.execute("""
        INSERT INTO conversation_messages (conversation_id, direction, message_text, message_type)
        VALUES (?, 'out', ?, 'text')
    """, (conv_id, message))
    conn.commit()
    conn.close()

    from scripts.senders import send_whatsapp
    logger.info(f"NEW CONV wa_number_id={wa_number_id} phone={phone} session={wa_num['session_name']} msg_len={len(message)}")
    try:
        result = send_whatsapp(phone, message, wa_num["session_name"])
        if result:
            logger.info(f"NEW CONV SEND OK session={wa_num['session_name']} to={phone}")
        else:
            logger.error(f"NEW CONV SEND FAIL session={wa_num['session_name']} to={phone} all_methods_failed")
    except Exception as e:
        logger.error(f"NEW CONV SEND ERROR session={wa_num['session_name']} to={phone} err={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Send failed: {e}")

    return JSONResponse(status_code=201, content={"status": "success", "data": {"ok": True, "conversation_id": conv_id}})


@router.post("/{conv_id}/stop")
async def api_stop_conversation(conv_id: int):
    """Stop AI responses for a conversation."""
    conn = state_manager._connect()
    conn.execute("UPDATE conversations SET status = 'stopped' WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "data": {"ok": True}}


# ── Messages ─────────────────────────────────────────────────────────

@router.get("/{conv_id}/messages")
async def api_conversation_messages(conv_id: int, limit: int = 50):
    """Get messages for a conversation."""
    msgs = state_manager.get_conversation_messages(conv_id, limit=limit)
    return {"status": "success", "data": {"messages": msgs, "count": len(msgs)}}


@router.post("/{conv_id}/messages")
async def api_conversation_send(conv_id: int, request: Request):
    """Send a message in a conversation."""
    data = await request.json()
    text = data.get("message", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message required")

    conn = state_manager._connect()
    conv = conn.execute("SELECT wa_number_id, contact_phone FROM conversations WHERE id = ?", (conv_id,)).fetchone()

    if not conv:
        conn.close()
        raise HTTPException(status_code=404, detail="Conversation not found")

    wa_number_id, contact_phone = conv[0], conv[1]

    wa_num = conn.execute("SELECT session_name, phone FROM wa_numbers WHERE id = ?", (wa_number_id,)).fetchone()
    conn.close()

    msg_id = state_manager.add_conversation_message(
        conversation_id=conv_id,
        message_text=text,
        direction="out",
        message_type="text",
    )

    if wa_num:
        session_name = wa_num[0]
        from scripts.senders import send_whatsapp
        clean_phone = contact_phone.replace("@c.us", "")
        logger.info(f"SEND msg conv={conv_id} session={session_name} to={clean_phone} len={len(text)}")
        try:
            ok = send_whatsapp(clean_phone, text, session_name)
            if ok:
                logger.info(f"SEND OK conv={conv_id} session={session_name} to={clean_phone}")
            else:
                logger.error(f"SEND FAIL conv={conv_id} session={session_name} to={clean_phone} all_methods_failed")
        except Exception as e:
            logger.error(f"SEND ERROR conv={conv_id} session={session_name} to={clean_phone} err={e}")
    else:
        logger.warning(f"SEND SKIP conv={conv_id} no_waha_session wa_number_id={wa_number_id}")

    return JSONResponse(status_code=201, content={"status": "success", "data": {"ok": True, "message_id": msg_id}})


# ── WAHA History ──────────────────────────────────────────────────────

@router.get("/{conv_id}/waha-history")
async def api_conversation_waha_history(conv_id: int, limit: int = 100):
    """Fetch chat history from WAHA for this conversation's contact phone & session.

    Merges WAHA messages with local DB messages, deduplicating by WAHA message ID.
    """
    conn = state_manager._connect()
    conv = conn.execute(
        "SELECT wa_number_id, contact_phone FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    if not conv:
        conn.close()
        raise HTTPException(status_code=404, detail="Conversation not found")

    wa_number_id, contact_phone = conv[0], conv[1]
    conn.close()

    wa_num = None
    try:
        c2 = state_manager._connect()
        wa_num = c2.execute(
            "SELECT session_name, phone FROM wa_numbers WHERE id = ?", (wa_number_id,)
        ).fetchone()
        c2.close()
    except Exception:
        pass

    if not wa_num:
        return {"status": "success", "data": {"messages": [], "count": 0}}

    session_name = wa_num[0]
    chat_id = contact_phone  # Already in @c.us or @lid format

    waha_messages = []
    for target_name, base_url, headers in _waha_targets():
        url = str(base_url or "").rstrip("/")
        if not url:
            continue
        try:
            logger.info(f"WAHA HISTORY conv={conv_id} target={target_name} session={session_name} chat={chat_id}")
            r = http_requests.get(
                f"{url}/api/{session_name}/chats/{url_quote(chat_id, safe='')}/messages",
                params={"limit": str(limit), "downloadMedia": "false"},
                headers={k: v for k, v in headers.items() if k != "Content-Type"},
                timeout=15,
            )
            if r.status_code == 200:
                raw = r.json()
                waha_messages = raw if isinstance(raw, list) else raw.get("messages", [])
                logger.info(f"WAHA HISTORY OK conv={conv_id} target={target_name} msgs={len(waha_messages)}")
                break
            logger.warning(f"WAHA HISTORY FAIL conv={conv_id} target={target_name} status={r.status_code} body={r.text[:100]}")
            if r.status_code == 404:
                continue
        except Exception as e:
            logger.error(f"WAHA HISTORY ERROR conv={conv_id} target={target_name} err={e}")
            continue

    # Also get local messages for dedup
    local_msgs = state_manager.get_conversation_messages(conv_id, limit=500)
    local_waha_ids = {
        m.get("waha_message_id")
        for m in local_msgs
        if m.get("waha_message_id")
    }

    merged = []
    seen_ids = set()

    # Add local messages first
    for m in local_msgs:
        mid = m.get("waha_message_id") or f"local_{m['id']}"
        if mid not in seen_ids:
            seen_ids.add(mid)
            merged.append({
                "id": m["id"],
                "conversation_id": conv_id,
                "direction": m["direction"],
                "message_text": m["message_text"],
                "message_type": m.get("message_type", "text"),
                "timestamp": m.get("timestamp", ""),
                "waha_message_id": m.get("waha_message_id"),
                "source": "local",
            })

    # Add WAHA messages, deduping against local
    for msg in waha_messages:
        key = msg.get("key", {})
        msg_id = key.get("id", "")
        if msg_id in seen_ids:
            continue

        body = msg.get("body", "")
        if not body and isinstance(msg.get("message"), dict):
            msg_obj = msg["message"]
            body = msg_obj.get("conversation", "") or msg_obj.get("extendedTextMessage", {}).get("text", "")

        if not body:
            continue

        from_me = msg.get("fromMe", False)
        timestamp = msg.get("messageTimestamp", "")

        if msg_id and msg_id not in local_waha_ids:
            seen_ids.add(msg_id)
            merged.append({
                "id": f"waha_{msg_id}",
                "conversation_id": conv_id,
                "direction": "out" if from_me else "in",
                "message_text": body,
                "message_type": "text",
                "timestamp": str(timestamp) if timestamp else "",
                "waha_message_id": msg_id,
                "source": "waha",
            })

    # Sort by timestamp
    merged.sort(key=lambda m: m.get("timestamp", "") or "")
    return {"status": "success", "data": {"messages": merged, "count": len(merged)}}


# ── Stage / Manual Mode ───────────────────────────────────────────────

@router.patch("/{conv_id}/stage")
async def api_conversation_stage(conv_id: int, request: Request):
    """Update a conversation's funnel stage."""
    data = await request.json()
    stage = data.get("stage")
    if not stage:
        raise HTTPException(status_code=400, detail="stage required")
    state_manager.set_conversation_stage(conv_id, stage)
    return {"status": "success", "data": {"ok": True}}


@router.patch("/{conv_id}/manual")
async def api_conversation_manual(conv_id: int, request: Request):
    """Toggle manual/AI mode for a conversation."""
    data = await request.json()
    enabled = data.get("manual_mode", data.get("enabled", True))
    state_manager.set_manual_mode(conv_id, enabled)
    return {"status": "success", "data": {"ok": True, "manual_mode": enabled}}


# ── Feedback ─────────────────────────────────────────────────────────

@router.post("/{conv_id}/feedback")
async def api_conversation_feedback(conv_id: int, request: Request):
    """Submit feedback (good/bad) for a conversation message."""
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


@router.get("/{conv_id}/feedback")
async def api_conversation_feedback_get(conv_id: int):
    """Get feedback for a conversation."""
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


# ── Message Log ───────────────────────────────────────────────────────

@router.get("/logs")
async def api_message_logs(
    limit: int = 100,
    direction: Optional[str] = None,
    session: Optional[str] = None,
):
    """Recent message activity log from journald (1ai-reach-api unit).

    Queries journald for the last N log entries matching our structured
    send/receive/error log lines. Filterable by direction (in/out) or session name.
    """
    import subprocess as sp

    cmd = [
        "journalctl", "--user", "-u", "1ai-reach-api",
        "--no-pager", "-n", str(min(limit, 500)),
        "--output=json",
    ]
    try:
        result = sp.run(cmd, capture_output=True, text=True, timeout=10)
        entries = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                import json
                entry = json.loads(line)
                msg = entry.get("MESSAGE", "")
                if not msg:
                    continue
                # Filter to our structured log lines
                if any(kw in msg for kw in ("SEND ", "RECV ", "WAHA ", "NEW CONV")):
                    if direction and direction not in msg:
                        continue
                    if session and session not in msg:
                        continue
                    entries.append({
                        "timestamp": entry.get("__REALTIME_TIMESTAMP", entry.get("__MONOTONIC_TIMESTAMP", "")),
                        "message": msg,
                        "priority": entry.get("PRIORITY", "6"),
                    })
            except (json.JSONDecodeError, KeyError):
                continue
        return {"status": "success", "data": {"logs": entries, "count": len(entries)}}
    except Exception as e:
        logger.error(f"message log query failed: {e}")
        return {"status": "error", "data": {"logs": [], "count": 0, "error": str(e)}}