"""WAHA webhook endpoints for WhatsApp message and status events.

Key design decisions:
- CS engine processing runs in a background thread pool via run_in_executor
  to avoid blocking the async event loop (was causing /health 504s).
- Service instances are lazily initialized and cached via lru_cache.
- WAHA NOWEB payload format is supported (key.fromMe, message.conversation, etc).
- Deduplication prevents double-processing.
"""

import asyncio
import logging
import sqlite3
import sys
import time as _time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from oneai_reach.config.settings import get_settings as _get_app_settings
from state_manager import (
    add_conversation_message,
    get_or_create_conversation,
    get_wa_number_by_session,
    is_manual_mode,
)

router = APIRouter(prefix="/api/v1/webhooks/waha", tags=["webhooks"])
logger = logging.getLogger(__name__)

# --- Dedup & rate limiting ---
_processed_messages: set[str] = set()
_CONVERSATION_MESSAGE_COUNTS: dict[str, int] = {}
_CONVERSATION_MAX_MESSAGES = 50

# Background thread pool for CS engine (non-blocking)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cs_engine")


# --- Lazy singleton service cache ---
@lru_cache(maxsize=1)
def _get_settings_cached():
    return _get_app_settings()


@lru_cache(maxsize=1)
def _get_cs_engine():
    """Lazily create and cache the CS engine service instance."""
    from oneai_reach.application.customer_service import (
        CSEngineService,
        ConversationService,
        OutcomesService,
        PlaybookService,
    )
    from oneai_reach.infrastructure.database import SQLiteConversationRepository

    settings = _get_settings_cached()

    def get_db_connection():
        conn = sqlite3.connect(settings.database.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    conv_repo = SQLiteConversationRepository(settings.database.db_file)
    conv_service = ConversationService(settings, get_db_connection)
    outcomes_service = OutcomesService(settings, get_db_connection)
    playbook_service = PlaybookService()
    return CSEngineService(settings, conv_service, outcomes_service, playbook_service)


# --- Models ---
class WAHAPayload(BaseModel):
    from_: Optional[str] = Field(None, alias="from")
    chatId: Optional[str] = None
    body: Optional[str] = None
    type: str = "chat"
    fromMe: bool = False
    id: Optional[str] = None
    media: Optional[Dict[str, Any]] = None


class WAHAWebhookRequest(BaseModel):
    event: str
    session: str
    payload: Optional[WAHAPayload] = None
    data: Optional[Dict[str, Any]] = None


class WAHAWebhookResponse(BaseModel):
    status: str
    action: Optional[str] = None
    response_sent: Optional[str] = None
    skipped: Optional[str] = None
    event: Optional[str] = None
    transcription: Optional[str] = None
    reason: Optional[str] = None


# --- Helpers ---
def _normalize_phone(phone: str) -> str:
    """Normalize phone number to digits-only format (62xxx)."""
    clean = "".join(filter(str.isdigit, str(phone)))
    if clean.startswith("0062"):
        clean = clean[2:]
    elif clean.startswith("0"):
        clean = "62" + clean[1:]
    elif not clean.startswith("62"):
        clean = "62" + clean
    return clean


def _is_manual_mode_active(wa_number_id: str, contact_phone: str) -> bool:
    try:
        from state_manager import get_all_conversation_stages

        convs = get_all_conversation_stages(wa_number_id=wa_number_id)
        for c in convs:
            if c.get("contact_phone") == contact_phone and c.get("manual_mode"):
                return True
    except Exception:
        pass
    return False


def _extract_body(payload: dict) -> str:
    """Extract message body from WAHA payload (supports both WEBJS and NOWEB formats)."""
    body = payload.get("body", "")
    if body:
        return body
    # NOWEB format: body nested inside message object
    msg_obj = payload.get("message", {})
    if not isinstance(msg_obj, dict):
        return ""
    return (
        msg_obj.get("conversation", "")
        or (msg_obj.get("extendedTextMessage") or {}).get("text", "")
        or (msg_obj.get("imageMessage") or {}).get("caption", "")
        or (msg_obj.get("videoMessage") or {}).get("caption", "")
        or (msg_obj.get("documentMessage") or {}).get("caption", "")
        or ""
    )


def _extract_msg_id(payload: dict) -> str:
    """Extract message ID from WAHA payload (supports key.id format)."""
    msg_id = payload.get("id", "")
    if not msg_id:
        key_obj = payload.get("key", {})
        if isinstance(key_obj, dict):
            msg_id = key_obj.get("id", "")
    return msg_id


def _extract_from_me(payload: dict) -> bool:
    """Extract fromMe flag (supports key.fromMe format)."""
    if payload.get("fromMe", False):
        return True
    key_obj = payload.get("key", {})
    if isinstance(key_obj, dict):
        return key_obj.get("fromMe", False)
    return False


def _run_cs_engine_sync(
    wa_number_id: str,
    contact_phone: str,
    message_text: str,
    session_name: str,
) -> dict:
    """Run CS engine synchronously (called from thread pool via run_in_executor)."""
    try:
        cs_engine = _get_cs_engine()
        return cs_engine.handle_inbound_message(
            wa_number_id=wa_number_id,
            contact_phone=contact_phone,
            message_text=message_text,
            session_name=session_name,
        )
    except Exception as e:
        logger.error(f"CS ENGINE ERROR session={session_name} from={contact_phone} err={e}", exc_info=True)
        return {"response": None, "error": str(e)}


def _process_voice_sync(
    media_url: str, wa_number_id: str, contact_phone: str, session_name: str, msg_type: str
) -> dict:
    """Process voice note in a background thread."""
    try:
        from voice_pipeline import process_inbound_voice

        return process_inbound_voice(
            media_url=media_url,
            wa_number_id=wa_number_id,
            contact_phone=contact_phone,
            session_name=session_name,
            msg_type=msg_type,
        )
    except Exception as e:
        logger.error(f"VOICE PROCESS ERROR err={e}")
        return {"action": "error", "transcription": str(e)[:100]}


# --- Handlers ---
@router.post("/message", response_model=WAHAWebhookResponse)
async def handle_waha_webhook(request: Request) -> WAHAWebhookResponse:
    """Handle WAHA webhook for WhatsApp messages.

    CS engine processing runs in a background thread via run_in_executor
    to avoid blocking the async event loop (which was causing /health 504s).
    """
    try:
        data = await request.json()
        event = data.get("event", "")
        session = data.get("session", "")
        payload = data.get("payload") or data.get("data", {})

        logger.info(f"RECV webhook event={event} session={session}")

        if event == "session.status":
            status = data.get("status", "")
            logger.info(f"SESSION STATUS session={session} status={status}")
            return WAHAWebhookResponse(status="ok", event=event)

        if event not in ("message", "message.any"):
            return WAHAWebhookResponse(status="ok", event=event)

        # --- Message processing ---
        sender = payload.get("from") or payload.get("chatId", "")
        body_text = _extract_body(payload)
        msg_type = payload.get("type", "chat")
        from_me = _extract_from_me(payload)
        msg_id = _extract_msg_id(payload)

        logger.info(
            f"RECV msg session={session} from={sender} type={msg_type} "
            f"from_me={from_me} id={msg_id} len={len(body_text)}"
        )

        global _processed_messages
        if msg_id and msg_id in _processed_messages:
            return WAHAWebhookResponse(status="ok", skipped="duplicate")
        if msg_id:
            _processed_messages.add(msg_id)
            if len(_processed_messages) > 2000:
                _processed_messages.clear()

        # Skip own messages
        if from_me:
            return WAHAWebhookResponse(status="ok", skipped="from_me")

        # Skip group messages
        if "@g.us" in sender:
            return WAHAWebhookResponse(status="ok", skipped="group_message")

        # Skip unsupported types
        if msg_type not in ("chat", "image", "video", "document", "audio", "ptt"):
            return WAHAWebhookResponse(status="ok", skipped=f"type:{msg_type}")

        # Voice notes — process in background thread
        if msg_type in ("audio", "ptt"):
            try:
                from voice_config import get_voice_config

                voice_config = get_voice_config(session)
                if voice_config.get("voice_enabled"):
                    media_url = payload.get("media", {}).get("url", "")
                    if media_url:
                        wa_number = get_wa_number_by_session(session)
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(
                            _executor,
                            _process_voice_sync,
                            media_url,
                            wa_number.get("id", session) if wa_number else session,
                            sender,
                            session,
                            msg_type,
                        )
                        return WAHAWebhookResponse(
                            status="ok",
                            action=result.get("action"),
                            transcription=result.get("transcription", "")[:100],
                        )
            except ImportError:
                pass
            except Exception as e:
                logger.error(f"VOICE ERROR session={session} err={e}")

        # Media type labels
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
            return WAHAWebhookResponse(status="ok", skipped="no_sender")
        if not body_text:
            body_text = "Halo"

        wa_number = get_wa_number_by_session(session)
        if not wa_number:
            raise HTTPException(status_code=404, detail="session_not_found")

        wa_number_id = wa_number.get("id", session)

        # Self-message detection
        wa_phone = wa_number.get("phone", "")
        if wa_phone:
            normalized_sender = _normalize_phone(sender)
            normalized_wa_phone = _normalize_phone(wa_phone)
            if normalized_sender == normalized_wa_phone:
                return WAHAWebhookResponse(status="ok", skipped="self_message")

        # Infinite loop guard
        conv_key = f"{wa_number_id}:{sender}"
        if conv_key not in _CONVERSATION_MESSAGE_COUNTS:
            _CONVERSATION_MESSAGE_COUNTS[conv_key] = 0
        _CONVERSATION_MESSAGE_COUNTS[conv_key] += 1

        if _CONVERSATION_MESSAGE_COUNTS[conv_key] > _CONVERSATION_MAX_MESSAGES:
            logger.warning(
                f"LOOP GUARD conv={conv_key} "
                f"count={_CONVERSATION_MESSAGE_COUNTS[conv_key]} "
                f"max={_CONVERSATION_MAX_MESSAGES}"
            )
            return WAHAWebhookResponse(
                status="ok",
                skipped=f"infinite_loop_guard:{_CONVERSATION_MESSAGE_COUNTS[conv_key]}",
            )

        # Manual mode — record message, don't auto-reply
        if _is_manual_mode_active(wa_number_id, sender):
            add_conversation_message(
                conversation_id=get_or_create_conversation(wa_number_id, sender, engine_mode="cs"),
                message_text=body_text,
                direction="in",
                message_type=msg_type,
            )
            return WAHAWebhookResponse(status="ok", skipped="manual_mode")

        # --- CS ENGINE: run in background thread to avoid blocking event loop ---
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            _run_cs_engine_sync,
            wa_number_id,
            sender,
            body_text,
            session,
        )

        response_preview = ""
        if result.get("response"):
            response_preview = result.get("response", "")[:100] + "..."

        return WAHAWebhookResponse(
            status="ok",
            action=result.get("action"),
            response_sent=response_preview,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"WEBHOOK ERROR event={data.get('event','')} "
            f"session={data.get('session','')} err={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status", response_model=WAHAWebhookResponse)
async def handle_waha_status(request: Request) -> WAHAWebhookResponse:
    """Handle WAHA status webhook events (delivery receipts, read receipts, etc)."""
    try:
        data = await request.json()
        event = data.get("event", "")
        session = data.get("session", "")
        status = data.get("status", data.get("payload", {}).get("status", ""))

        logger.info(f"RECV STATUS event={event} session={session} status={status}")

        # Update conversation status for read receipts
        if event == "message.ack" and status in ("read", "played"):
            payload = data.get("payload", {})
            msg_id = payload.get("id", "")
            if msg_id:
                logger.info(f"ACK msg_id={msg_id} status={status} session={session}")

        return WAHAWebhookResponse(status="ok", event=event)

    except Exception as e:
        logger.error(f"STATUS WEBHOOK ERROR err={e}")
        raise HTTPException(status_code=500, detail=str(e))
