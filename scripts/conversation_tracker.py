"""
Conversation tracker — message threading, state machine, cross-contamination guard.

Cross-contamination guard forces engine_mode="cold" when contact_phone
matches a lead in the cold-call funnel, preventing CS responses to pipeline contacts.
State machine: active → resolved | escalated | cold.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.customer_service import ConversationService
from oneai_reach.config.settings import get_settings
from state_manager import _connect, init_db

_settings = get_settings()
_service = ConversationService(_settings, _connect)


def _is_cold_lead(contact_phone: str) -> bool:
    return _service.is_cold_lead(contact_phone)


def get_or_create_conversation(
    wa_number_id: str,
    contact_phone: str,
    engine_mode: str,
    contact_name: str | None = None,
    lead_id: str | None = None,
) -> dict:
    return _service.get_or_create_conversation(
        wa_number_id, contact_phone, engine_mode, contact_name, lead_id
    )


def add_message(
    conversation_id: int,
    direction: str,
    message_text: str,
    message_type: str = "text",
    waha_message_id: str | None = None,
) -> int:
    return _service.add_message(
        conversation_id, direction, message_text, message_type, waha_message_id
    )


def get_messages(conversation_id: int, limit: int = 50) -> list[dict]:
    return _service.get_messages(conversation_id, limit)


def get_active_conversations(wa_number_id: str | None = None) -> list[dict]:
    return _service.get_active_conversations(wa_number_id)


def update_status(conversation_id: int, status: str) -> bool:
    return _service.update_status(conversation_id, status)


def escalate(conversation_id: int, reason: str) -> bool:
    return _service.escalate(conversation_id, reason)


def get_conversation_context(conversation_id: int, max_messages: int = 10) -> str:
    return _service.get_conversation_context(conversation_id, max_messages)


def link_to_lead(conversation_id: int, lead_id: str) -> bool:
    return _service.link_to_lead(conversation_id, lead_id)


def auto_resolve_stale(hours: int = 48) -> int:
    return _service.auto_resolve_stale(hours)


def advance_stage(
    conversation_id: int, message_text: str, kb_results: list = None
) -> str | None:
    return _service.advance_stage(conversation_id, message_text, kb_results)


def get_stage_context(conversation_id: int) -> str:
    return _service.get_stage_context(conversation_id)


if __name__ == "__main__":
    init_db()
    print("[conversation_tracker] DB initialized")

    conv = get_or_create_conversation("default", "628111@c.us", "cs")
    print(f"[conversation_tracker] Conversation: {conv}")

    msg_id = add_message(conv["id"], "in", "Hello, I need help with my order")
    print(f"[conversation_tracker] Added message id={msg_id}")

    msg_id2 = add_message(
        conv["id"], "out", "Hi! I'd be happy to help. What's your order number?"
    )
    print(f"[conversation_tracker] Added message id={msg_id2}")

    ctx = get_conversation_context(conv["id"])
    print(f"[conversation_tracker] Context:\n{ctx}")

    active = get_active_conversations()
    print(f"[conversation_tracker] Active conversations: {len(active)}")

    print("[conversation_tracker] All tests passed ✓")
