"""Conversation tracking service - message threading, state machine, cross-contamination guard."""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import requests

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import (
    ConversationNotFoundError,
    InvalidConversationStateError,
    DatabaseError,
)
from oneai_reach.domain.models import (
    Conversation,
    ConversationStatus,
    EngineMode,
    Message,
    MessageDirection,
)
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

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


class ConversationService:
    """Service for managing conversation state, threading, and cross-contamination prevention."""

    def __init__(self, config: Settings = None, db_connection = None):
        """Initialize conversation service.

        Args:
            config: Application settings
            db_connection: Database connection function
        """
        self.config = config
        self._connect = db_connection

    def _normalize_phone(self, raw: str) -> str:
        """Normalize phone number to digits only."""
        phone = raw.split("@")[0]
        return "".join(ch for ch in phone if ch.isdigit())

    def is_cold_lead(self, contact_phone: str) -> bool:
        """Check if contact is in cold-call funnel (cross-contamination guard).

        Args:
            contact_phone: Contact phone number

        Returns:
            True if contact is a cold lead, False otherwise
        """
        digits = self._normalize_phone(contact_phone)
        if not digits:
            return False

        conn = self._connect()
        try:
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
        except Exception as e:
            logger.error(f"Failed to check cold lead status: {e}")
            raise DatabaseError(operation="select", table="leads", reason=str(e))
        finally:
            conn.close()

    def get_or_create_conversation(
        self,
        wa_number_id: str,
        contact_phone: str,
        engine_mode: str,
        contact_name: Optional[str] = None,
        lead_id: Optional[str] = None,
    ) -> dict:
        """Get existing active conversation or create new one.

        Args:
            wa_number_id: WhatsApp number ID
            contact_phone: Contact phone number
            engine_mode: Engine mode (cs/cold/manual)
            contact_name: Optional contact name
            lead_id: Optional lead ID

        Returns:
            Conversation dictionary
        """
        # Cross-contamination guard
        if engine_mode != "cold" and self.is_cold_lead(contact_phone):
            engine_mode = "cold"

        conn = self._connect()
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
            from state_manager import create_conversation

            conv_id = create_conversation(
                wa_number_id,
                contact_phone,
                engine_mode,
                contact_name=contact_name or "",
                lead_id=lead_id,
            )

        from state_manager import get_conversation

        return get_conversation(conv_id)

    def add_message(
        self,
        conversation_id: int,
        direction: str,
        message_text: str,
        message_type: str = "text",
        waha_message_id: Optional[str] = None,
    ) -> int:
        """Add message to conversation.

        Args:
            conversation_id: Conversation ID
            direction: Message direction (in/out)
            message_text: Message text content
            message_type: Message type (text/voice/image)
            waha_message_id: Optional WAHA message ID

        Returns:
            Message ID
        """
        from state_manager import add_conversation_message

        return add_conversation_message(
            conversation_id,
            direction,
            message_text,
            message_type=message_type,
            waha_message_id=waha_message_id or "",
        )

    def get_messages(self, conversation_id: int, limit: int = 50) -> list[dict]:
        """Get conversation messages.

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of messages

        Returns:
            List of message dictionaries
        """
        from state_manager import get_conversation_messages

        return get_conversation_messages(conversation_id, limit=limit)

    def get_active_conversations(
        self, wa_number_id: Optional[str] = None
    ) -> list[dict]:
        """Get all active conversations.

        Args:
            wa_number_id: Optional filter by WhatsApp number ID

        Returns:
            List of active conversation dictionaries
        """
        conn = self._connect()
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

    def update_status(self, conversation_id: int, status: str) -> bool:
        """Update conversation status.

        Args:
            conversation_id: Conversation ID
            status: New status (active/resolved/escalated/cold)

        Returns:
            True if updated successfully

        Raises:
            InvalidConversationStateError: If status is invalid
        """
        valid_statuses = {"active", "resolved", "escalated", "cold"}
        if status not in valid_statuses:
            raise InvalidConversationStateError(
                conversation_id=str(conversation_id),
                current_state="unknown",
                operation=f"set status to {status}",
            )

        from state_manager import get_conversation, update_conversation_status

        conv = get_conversation(conversation_id)
        if not conv:
            return False

        update_conversation_status(conversation_id, status)
        return True

    def escalate(self, conversation_id: int, reason: str) -> bool:
        """Escalate conversation to human agent.

        Args:
            conversation_id: Conversation ID
            reason: Escalation reason

        Returns:
            True if escalated successfully
        """
        from state_manager import get_conversation, update_conversation_status

        conv = get_conversation(conversation_id)
        if not conv:
            return False

        update_conversation_status(conversation_id, "escalated")

        # Send Telegram alert if configured
        if self.config.cs.escalation_telegram:
            contact = conv.get("contact_name") or conv.get("contact_phone", "unknown")
            wa_number = conv.get("wa_number_id", "unknown")
            alert_text = (
                f"🚨 *Escalation Alert*\n\n"
                f"Conversation #{conversation_id} escalated.\n"
                f"Contact: {contact}\n"
                f"WA Number: {wa_number}\n"
                f"Reason: {reason}"
            )
            self._send_telegram_alert(alert_text)

        return True

    def _send_telegram_alert(self, text: str) -> bool:
        """Send Telegram alert notification."""
        if not self.config.telegram.bot_token or not self.config.telegram.chat_id:
            logger.warning("Telegram not configured, skipping alert")
            return False

        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.config.telegram.bot_token}/sendMessage",
                json={
                    "chat_id": self.config.telegram.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            if r.status_code < 300:
                logger.info("Telegram alert sent")
                return True
            else:
                logger.error(f"Telegram error {r.status_code}: {r.text[:100]}")
                return False
        except Exception as e:
            logger.error(f"Telegram failed: {e}")
            return False

    def get_conversation_context(
        self, conversation_id: int, max_messages: int = 10
    ) -> str:
        """Format conversation messages as context for LLM prompts.

        Args:
            conversation_id: Conversation ID
            max_messages: Maximum messages to include

        Returns:
            Formatted conversation context string
        """
        from state_manager import get_conversation_messages

        messages = get_conversation_messages(conversation_id, limit=max_messages)
        lines = []
        for msg in messages:
            role = "Customer" if msg["direction"] == "in" else "Agent"
            text = msg.get("message_text", "")
            if text:
                lines.append(f"{role}: {text}")
        return "\n".join(lines)

    def link_to_lead(self, conversation_id: int, lead_id: str) -> bool:
        """Link conversation to a lead.

        Args:
            conversation_id: Conversation ID
            lead_id: Lead ID

        Returns:
            True if linked successfully
        """
        from state_manager import get_conversation

        conv = get_conversation(conversation_id)
        if not conv:
            return False

        conn = self._connect()
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

    def auto_resolve_stale(self, hours: int = 48) -> int:
        """Auto-resolve stale conversations.

        Args:
            hours: Hours of inactivity threshold

        Returns:
            Number of conversations resolved
        """
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn = self._connect()
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

    def advance_stage(
        self, conversation_id: int, message_text: str, kb_results: list = None
    ) -> Optional[str]:
        """Detect if message advances the sales stage.

        Args:
            conversation_id: Conversation ID
            message_text: Customer message text
            kb_results: Optional KB search results

        Returns:
            New stage name or None if no advancement
        """
        from state_manager import get_conversation_stage, set_conversation_stage

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

        return None

    def get_stage_context(self, conversation_id: int) -> str:
        """Get formatted stage context for LLM prompts.

        Args:
            conversation_id: Conversation ID

        Returns:
            Formatted stage context string
        """
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
