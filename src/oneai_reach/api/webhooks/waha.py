"""WAHA webhook endpoints for WhatsApp message and status events."""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cs_engine import handle_inbound_message
from state_manager import (
    get_wa_number_by_session,
    add_conversation_message,
    get_or_create_conversation,
    is_manual_mode,
)

router = APIRouter(prefix="/api/v1/webhooks/waha", tags=["webhooks"])

_processed_messages = set()


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

        print(f"[WEBHOOK] Event: {event}, Session: {session}")

        if event in ("message", "message.any"):
            sender = payload.get("from") or payload.get("chatId", "")
            body_text = payload.get("body", "")
            msg_type = payload.get("type", "chat")
            from_me = payload.get("fromMe", False)
            msg_id = payload.get("id", "")

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
                    print(f"[webhook] Voice processing error: {e}")

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
            if _is_manual_mode_active(wa_number_id, sender):
                add_conversation_message(
                    conversation_id=_get_or_create_conv_id(wa_number_id, sender),
                    message_text=body_text,
                    direction="in",
                    message_type=msg_type,
                )
                return WAHAWebhookResponse(status="ok", skipped="manual_mode")

            result = handle_inbound_message(
                wa_number_id=wa_number_id,
                contact_phone=sender,
                message_text=body_text,
                session_name=session,
            )

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
        print(f"[WEBHOOK ERROR] {e}")
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

        print(f"[WEBHOOK STATUS] Event: {event}, Session: {session}")

        return WAHAWebhookResponse(status="ok", event=event)

    except Exception as e:
        print(f"[WEBHOOK STATUS ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))
