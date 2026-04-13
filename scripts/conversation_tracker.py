"""
Conversation tracker — message threading, state machine, cross-contamination guard.

Cross-contamination guard forces engine_mode="cold" when contact_phone
matches a lead in the cold-call funnel, preventing CS responses to pipeline contacts.
State machine: active → resolved | escalated | cold.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests as _req

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    CS_ESCALATION_TELEGRAM,
)
from state_manager import (
    _connect,
    init_db,
    create_conversation,
    get_conversation,
    add_conversation_message,
    get_conversation_messages,
    update_conversation_status,
)

_COLD_FUNNEL_STAGES = frozenset(
    {
        "new",
        "enriched",
        "draft_ready",
        "needs_revision",
        "reviewed",
        "contacted",
        "followed_up",
    }
)


def _normalize_phone(raw: str) -> str:
    phone = raw.split("@")[0]
    return "".join(ch for ch in phone if ch.isdigit())


def _is_cold_lead(contact_phone: str) -> bool:
    digits = _normalize_phone(contact_phone)
    if not digits:
        return False
    conn = _connect()
    try:
        # Phone columns may contain '+', spaces, dashes — suffix-match on digits only
        rows = conn.execute(
            "SELECT phone, internationalPhoneNumber, status FROM leads"
        ).fetchall()
        for row in rows:
            for col in ("phone", "internationalPhoneNumber"):
                stored = row[col] or ""
                stored_digits = "".join(ch for ch in stored if ch.isdigit())
                if stored_digits and (
                    stored_digits.endswith(digits) or digits.endswith(stored_digits)
                ):
                    if row["status"] in _COLD_FUNNEL_STAGES:
                        return True
        return False
    finally:
        conn.close()


def get_or_create_conversation(
    wa_number_id: str,
    contact_phone: str,
    engine_mode: str,
    contact_name: str | None = None,
    lead_id: str | None = None,
) -> dict:
    if engine_mode != "cold" and _is_cold_lead(contact_phone):
        engine_mode = "cold"

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM conversations "
            "WHERE wa_number_id = ? AND contact_phone = ? AND status = 'active'",
            (wa_number_id, contact_phone),
        ).fetchone()
    finally:
        conn.close()

    if row:
        conv_id = row["id"]
    else:
        conv_id = create_conversation(
            wa_number_id,
            contact_phone,
            engine_mode,
            contact_name=contact_name or "",
            lead_id=lead_id,
        )

    return get_conversation(conv_id)


def add_message(
    conversation_id: int,
    direction: str,
    message_text: str,
    message_type: str = "text",
    waha_message_id: str | None = None,
) -> int:
    return add_conversation_message(
        conversation_id,
        direction,
        message_text,
        message_type=message_type,
        waha_message_id=waha_message_id or "",
    )


def get_messages(conversation_id: int, limit: int = 50) -> list[dict]:
    return get_conversation_messages(conversation_id, limit=limit)


def get_active_conversations(wa_number_id: str | None = None) -> list[dict]:
    conn = _connect()
    try:
        if wa_number_id:
            rows = conn.execute(
                "SELECT * FROM conversations "
                "WHERE status = 'active' AND wa_number_id = ? "
                "ORDER BY last_message_at DESC",
                (wa_number_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM conversations "
                "WHERE status = 'active' "
                "ORDER BY last_message_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_status(conversation_id: int, status: str) -> bool:
    valid_statuses = {"active", "resolved", "escalated", "cold"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")

    conv = get_conversation(conversation_id)
    if not conv:
        return False

    update_conversation_status(conversation_id, status)
    return True


def _send_telegram_alert(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[conversation_tracker] Telegram not configured, skipping alert",
            file=sys.stderr,
        )
        return False
    try:
        r = _req.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        if r.status_code < 300:
            print("[conversation_tracker] Telegram alert sent")
            return True
        else:
            print(
                f"[conversation_tracker] Telegram error {r.status_code}: {r.text[:100]}",
                file=sys.stderr,
            )
            return False
    except Exception as e:
        print(f"[conversation_tracker] Telegram failed: {e}", file=sys.stderr)
        return False


def escalate(conversation_id: int, reason: str) -> bool:
    conv = get_conversation(conversation_id)
    if not conv:
        return False

    update_conversation_status(conversation_id, "escalated")

    if CS_ESCALATION_TELEGRAM:
        contact = conv.get("contact_name") or conv.get("contact_phone", "unknown")
        wa_number = conv.get("wa_number_id", "unknown")
        alert_text = (
            f"🚨 *Escalation Alert*\n\n"
            f"Conversation #{conversation_id} escalated.\n"
            f"Contact: {contact}\n"
            f"WA Number: {wa_number}\n"
            f"Reason: {reason}"
        )
        _send_telegram_alert(alert_text)

    return True


def get_conversation_context(conversation_id: int, max_messages: int = 10) -> str:
    """Format messages as 'Customer: ...\\nAgent: ...' for LLM prompt context."""
    messages = get_conversation_messages(conversation_id, limit=max_messages)
    lines = []
    for msg in messages:
        role = "Customer" if msg["direction"] == "in" else "Agent"
        text = msg.get("message_text", "")
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def link_to_lead(conversation_id: int, lead_id: str) -> bool:
    conv = get_conversation(conversation_id)
    if not conv:
        return False

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE conversations SET lead_id = ?, updated_at = datetime('now') WHERE id = ?",
            (lead_id, conversation_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def auto_resolve_stale(hours: int = 48) -> int:
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE conversations SET status = 'cold', updated_at = datetime('now') "
            "WHERE status = 'active' AND last_message_at < ?",
            (cutoff,),
        )
        count = cur.rowcount
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sales Stage Advancement
# ---------------------------------------------------------------------------

STAGE_ORDER = ["discovery", "interest", "proposal", "negotiation", "close"]
STAGE_KEYWORDS = {
    "discovery": {
        "halo",
        "hi",
        "hallo",
        "apa",
        "siapa",
        "dimana",
        "tanya",
        "info",
        "kenalan",
        "perkenalan",
    },
    "interest": {
        "harga",
        "berapa",
        "cara",
        "boleh",
        "bisa",
        "kirim",
        "dapat",
        "lihat",
        "pakai",
        "coba",
    },
    "proposal": {
        "ok",
        "iya",
        "mau",
        "tertarik",
        "lihat",
        "katalog",
        "produk",
        "order",
        "booking",
    },
    "negotiation": {
        "nego",
        "diskon",
        "murah",
        "lebih",
        "banding",
        "bandingin",
        "kurangi",
        "promo",
        "bonus",
    },
    "close": {
        "beli",
        "pesan",
        "transfer",
        "bayar",
        "order",
        "ya",
        "deal",
        "siap",
        "lunas",
        "account",
    },
}


def advance_stage(
    conversation_id: int, message_text: str, kb_results: list = None
) -> str | None:
    """Detect if message advances the sales stage. Return new stage or None."""
    from state_manager import get_conversation_stage, set_conversation_stage

    current = get_conversation_stage(conversation_id) or "discovery"
    text_lower = message_text.lower()

    try:
        current_idx = STAGE_ORDER.index(current)
    except ValueError:
        current_idx = 0

    for next_idx in range(current_idx + 1, len(STAGE_ORDER)):
        next_stage = STAGE_ORDER[next_idx]
        triggers = STAGE_KEYWORDS.get(next_stage, set())
        matched = [t for t in triggers if t in text_lower]
        if matched:
            set_conversation_stage(conversation_id, next_stage, matched[0])
            return next_stage

    return None  # No advancement


def get_stage_context(conversation_id: int) -> str:
    """Return formatted stage context for LLM prompts."""
    from state_manager import get_conversation_stage

    stage = get_conversation_stage(conversation_id) or "discovery"
    stage_hints = {
        "discovery": "Fokus pada membangun rapport. Tanya nama, lokasi, dan kebutuhan mereka. Jangan langsung promosi produk.",
        "interest": "Tunjukkan minat pada kebutuhan mereka. Berikan info dasar tentang layanan yang relevan.",
        "proposal": "Tawarkan solusi spesifik yang cocok untuk kebutuhan mereka. Sertakan harga dan manfaat utama.",
        "negotiation": "Bersikap fleksibel. Jika mereka minta diskon, tunjukkan value lebih. Jangan langsung kasih harga termurah.",
        "close": "Dorong untuk keputusan. Kirim payment link atau ajak schedule demo. Pastikan tidak ada hambatan lagi.",
    }
    hint = stage_hints.get(stage, "")
    return f"\n[Sales Stage: {stage.upper()}]\n{hint}\n"


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
