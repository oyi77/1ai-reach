import json
import requests
from datetime import datetime
from config import N8N_WEBHOOK_URL


def trigger_n8n(event_type: str, data: dict) -> bool:
    if not N8N_WEBHOOK_URL:
        return False

    payload = {
        "event": event_type,
        "timestamp": datetime.now().isoformat(),
        "source": "1ai-reach",
        "data": data,
    }

    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            timeout=5,
            headers={"Content-Type": "application/json"},
        )
        return response.status_code < 300
    except Exception as e:
        print(f"n8n webhook failed: {e}")
        return False


def notify_conversation_started(phone: str, session: str, wa_number_id: str) -> bool:
    return trigger_n8n(
        "cs_conversation_started",
        {
            "phone": phone,
            "session": session,
            "wa_number_id": wa_number_id,
            "timestamp": datetime.now().isoformat(),
        },
    )


def notify_escalation(phone: str, reason: str, conversation_id: int) -> bool:
    return trigger_n8n(
        "cs_escalated",
        {
            "phone": phone,
            "reason": reason,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
        },
    )


def notify_hot_lead(phone: str, message_count: int, conversation_id: int) -> bool:
    return trigger_n8n(
        "cs_hot_lead",
        {
            "phone": phone,
            "message_count": message_count,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
        },
    )


def notify_purchase_signal(phone: str, message: str, conversation_id: int) -> bool:
    return trigger_n8n(
        "cs_purchase_signal",
        {
            "phone": phone,
            "message": message,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
        },
    )
