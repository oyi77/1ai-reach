"""WAHA webhook endpoints for WhatsApp message and status events."""

import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from oneai_reach.application.customer_service import CSEngineService
from state_manager import (
    get_wa_number_by_session,
    add_conversation_message,
    get_or_create_conversation,
    is_manual_mode,
)

router = APIRouter(prefix="/api/v1/webhooks/waha", tags=["webhooks"])
logger = logging.getLogger(__name__)

_processed_messages = set()
_CONVERSATION_MESSAGE_COUNTS = {}  # Track message count per conversation
_CONVERSATION_MAX_MESSAGES = 50  # Max messages per conversation before auto-stop
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cs_engine_bg")


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


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to digits-only format (62xxx).

    Handles various Indonesian phone formats:
    - +62812345678 -> 62812345678
    - 0812345678 -> 62812345678
    - 62812345678 -> 62812345678
    - 0062812345678 -> 62812345678

    Returns consistent format for comparison.
    """
    # Remove all non-digit characters
    clean = "".join(filter(str.isdigit, str(phone)))

    # Handle 0062 prefix FIRST (0062812 -> 62812)
    if clean.startswith("0062"):
        clean = clean[2:]
    # Handle leading 0 (Indonesia: 0812 -> 62812)
    elif clean.startswith("0"):
        clean = "62" + clean[1:]
    # Ensure 62 prefix
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


def _get_or_create_conv_id(wa_number_id: str, contact_phone: str) -> int:
    return get_or_create_conversation(wa_number_id, contact_phone, engine_mode="cs")


@router.post("/message", response_model=WAHAWebhookResponse)
async def handle_waha_webhook(request: Request) -> WAHAWebhookResponse:
    """Handle WAHA webhook for WhatsApp messages and events.

    Processes incoming WhatsApp messages, applies rate limiting and guards,
    and triggers CS engine auto-reply when appropriate.
    """
    try:
        data = await request.json()
        event = data.get("event", "")
        session = data.get("session", "")
        payload = data.get("payload") or data.get("data", {})

        logger.info(f"RECV webhook event={event} session={session}")

        if event in ("message", "message.any"):
            sender = payload.get("from") or payload.get("chatId", "")
            body_text = payload.get("body", "")
            msg_type = payload.get("type", "chat")
            from_me = payload.get("fromMe", False)
            msg_id = payload.get("id", "")

            logger.info(f"RECV msg session={session} from={sender} type={msg_type} from_me={from_me} id={msg_id} len={len(body_text)}")

            global _processed_messages
            if msg_id and msg_id in _processed_messages:
                return WAHAWebhookResponse(status="ok", skipped="duplicate")
            if msg_id:
                _processed_messages.add(msg_id)
                if len(_processed_messages) > 1000:
                    _processed_messages.clear()

            if from_me:
                return WAHAWebhookResponse(status="ok", skipped="from_me")

            if "@g.us" in sender:
                return WAHAWebhookResponse(status="ok", skipped="group_message")

            if msg_type not in ("chat", "image", "video", "document", "audio", "ptt"):
                return WAHAWebhookResponse(status="ok", skipped=f"type:{msg_type}")

            if msg_type in ("audio", "ptt"):
                try:
                    from voice_config import get_voice_config

                    voice_config = get_voice_config(session)
                    if voice_config.get("voice_enabled"):
                        media_url = payload.get("media", {}).get("url", "")
                        if media_url:
                            from voice_pipeline import process_inbound_voice

                            wa_number = get_wa_number_by_session(session)
                            voice_result = process_inbound_voice(
                                media_url=media_url,
                                wa_number_id=wa_number.get("id", session),
                                contact_phone=sender,
                                session_name=session,
                                msg_type=msg_type,
                            )
                            return WAHAWebhookResponse(
                                status="ok",
                                action=voice_result.get("action"),
                                transcription=voice_result.get("transcription", "")[
                                    :100
                                ],
                            )
                except ImportError:
                    pass
                except Exception as e:
                    logger.error(f"VOICE ERROR session={session} err={e}")

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

            # Detect self-message by comparing normalized phone numbers
            wa_phone = wa_number.get("phone", "")
            if wa_phone:
                normalized_sender = _normalize_phone(sender)
                normalized_wa_phone = _normalize_phone(wa_phone)
                if normalized_sender == normalized_wa_phone:
                    return WAHAWebhookResponse(status="ok", skipped="self_message")

            # Check conversation message limit to prevent infinite loops
            conv_key = f"{wa_number_id}:{sender}"
            if conv_key not in _CONVERSATION_MESSAGE_COUNTS:
                _CONVERSATION_MESSAGE_COUNTS[conv_key] = 0

            _CONVERSATION_MESSAGE_COUNTS[conv_key] += 1

            if _CONVERSATION_MESSAGE_COUNTS[conv_key] > _CONVERSATION_MAX_MESSAGES:
                logger.warning(f"LOOP GUARD conv={conv_key} count={_CONVERSATION_MESSAGE_COUNTS[conv_key]} max={_CONVERSATION_MAX_MESSAGES}")
                return WAHAWebhookResponse(
                    status="ok",
                    skipped=f"infinite_loop_guard:{_CONVERSATION_MESSAGE_COUNTS[conv_key]}",
                )

            if _is_manual_mode_active(wa_number_id, sender):
                add_conversation_message(
                    conversation_id=_get_or_create_conv_id(wa_number_id, sender),
                    message_text=body_text,
                    direction="in",
                    message_type=msg_type,
                )
                return WAHAWebhookResponse(status="ok", skipped="manual_mode")

            # Instantiate CS engine service and handle inbound message
            from oneai_reach.config.settings import get_settings
            from oneai_reach.application.customer_service import (
                ConversationService,
                OutcomesService,
                PlaybookService,
            )
            from oneai_reach.infrastructure.database import (
                SQLiteConversationRepository,
            )
            import sqlite3

            settings = get_settings()
            conv_repo = SQLiteConversationRepository(settings.database.db_file)

            def get_db_connection():
                conn = sqlite3.connect(settings.database.db_file)
                conn.row_factory = sqlite3.Row
                return conn

            conversation_service = ConversationService(settings, get_db_connection)
            outcomes_service = OutcomesService(settings, get_db_connection)
            playbook_service = PlaybookService()
            cs_engine = CSEngineService(
                settings, conversation_service, outcomes_service, playbook_service
            )

            def _run_cs_engine():
                try:
                    return cs_engine.handle_inbound_message(
                        wa_number_id=wa_number_id,
                        contact_phone=sender,
                        message_text=body_text,
                        session_name=session,
                    )
                except Exception as e:
                    logger.error(f"CS ENGINE ERROR session={session} from={sender} err={e}")
                    return {"response": None, "error": str(e)}

            try:
                result = _run_cs_engine()
            except Exception as e:
                logger.error(f"SYNC ERROR session={session} from={sender} err={e}")
                result = {"response": None, "skip": "error"}

            response_preview = ""
            if result.get("response"):
                response_preview = result.get("response", "")[:100] + "..."

            return WAHAWebhookResponse(
                status="ok",
                action=result.get("action"),
                response_sent=response_preview,
            )

        return WAHAWebhookResponse(status="ok", event=event)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WEBHOOK ERROR event={data.get('event','')} session={data.get('session','')} err={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status", response_model=WAHAWebhookResponse)
async def handle_waha_status(request: Request) -> WAHAWebhookResponse:
    """Handle WAHA status webhook events.

    Processes WhatsApp status updates (delivery, read receipts, etc).
    """
    try:
        data = await request.json()
        event = data.get("event", "")
        session = data.get("session", "")

        logger.info(f"RECV STATUS event={event} session={session}")

        return WAHAWebhookResponse(status="ok", event=event)

    except Exception as e:
        logger.error(f"STATUS WEBHOOK ERROR err={e}")
        raise HTTPException(status_code=500, detail=str(e))
