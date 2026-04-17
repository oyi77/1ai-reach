"""Closer agent service - intent classification and conversational sales closer.

Classifies replied lead intent (BUY/INFO/REJECT/UNCLEAR) and sends
appropriate payment or calendar links. Replaces static meeting invites
with intelligent, intent-driven responses.
"""

import sys
from pathlib import Path

# Add scripts directory to path for external client imports
_scripts_dir = Path(__file__).parent.parent.parent.parent.parent / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import brain_client
import llm_client
from senders import send_email, send_whatsapp
from state_manager import (
    add_event_log,
    get_lead_by_id,
    get_leads_by_status,
    update_lead_status,
)

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

_VALID_INTENTS = {"BUY", "INFO", "REJECT", "UNCLEAR"}

_MOCK_REPLIES = {
    "test_buy": "I'm ready to proceed, please send the invoice.",
    "test_ready": "I'm ready to proceed, please send the invoice.",
    "test_reject": "Not interested, thank you.",
}
_MOCK_DEFAULT = "Can you tell me more about your services?"


class CloserService:
    """Service for intent classification and conversational sales closing."""

    def __init__(self, config: Settings):
        self.config = config
        self.payment_link = config.booking.payment_link
        self.calendly_link = config.booking.calendly_link

    def classify_intent(self, reply_text: str, lead_name: str) -> str:
        prompt = (
            "Classify the intent of this sales reply into exactly one of: "
            "BUY, INFO, REJECT, UNCLEAR\n\n"
            "BUY: prospect wants to proceed, pay, or is ready to start\n"
            "INFO: prospect has questions or wants more details\n"
            "REJECT: prospect is not interested or says no\n"
            "UNCLEAR: cannot determine intent from the text\n\n"
            f"Lead: {lead_name}\n"
            f"Reply: {reply_text}\n\n"
            "Respond with ONLY the intent word (BUY/INFO/REJECT/UNCLEAR), nothing else."
        )
        result = llm_client.classify(prompt)
        if result in _VALID_INTENTS:
            return result
        return self._classify_heuristic(reply_text)

    def _classify_heuristic(self, text: str) -> str:
        t = text.lower()
        buy_signals = [
            "proceed",
            "invoice",
            "payment",
            "pay",
            "ready",
            "start",
            "let's go",
            "deal",
            "sign",
        ]
        reject_signals = [
            "not interested",
            "no thanks",
            "no thank",
            "decline",
            "pass",
            "unsubscribe",
            "stop",
        ]
        for word in reject_signals:
            if word in t:
                return "REJECT"
        for word in buy_signals:
            if word in t:
                return "BUY"
        if "?" in t or "more" in t or "info" in t or "detail" in t or "tell me" in t:
            return "INFO"
        return "UNCLEAR"

    def generate_response(self, intent: str, lead: dict) -> tuple[str, str]:
        name = lead.get("name") or lead.get("displayName") or "there"
        if intent == "BUY":
            email_body = (
                f"Hi {name},\n\n"
                f"Great to hear you're ready to move forward! "
                f"Here's your payment link:\n\n"
                f"👉 {self.payment_link}\n\n"
                f"Once completed, we'll get started right away.\n\n"
                f"Best,\nVilona\nBerkahKarya"
            )
            wa_msg = f"Halo {name}! Senang sekali dengarnya 🙏\nBerikut link pembayarannya: {self.payment_link}"
            return email_body, wa_msg
        elif intent in ("INFO", "UNCLEAR"):
            email_body = (
                f"Hi {name},\n\n"
                f"Happy to answer your questions! "
                f"Let's jump on a quick call to discuss in detail:\n\n"
                f"👉 {self.calendly_link}\n\n"
                f"Pick any time that works for you.\n\n"
                f"Best,\nVilona\nBerkahKarya"
            )
            wa_msg = f"Halo {name}! Yuk kita jadwalkan panggilan singkat untuk diskusi: {self.calendly_link}"
            return email_body, wa_msg
        else:
            return "", ""

    def _log_to_brain(self, lead: dict, intent: str) -> None:
        name = lead.get("name") or lead.get("displayName") or "Unknown"
        vertical = lead.get("type") or lead.get("primaryType") or "Business"
        status_map = {
            "BUY": "replied",
            "INFO": "replied",
            "REJECT": "lost",
            "UNCLEAR": "replied",
        }
        try:
            brain_client.learn_outcome(
                lead_name=name,
                vertical=vertical,
                status=status_map.get(intent, "replied"),
                pain_points=f"closer_intent={intent}",
            )
        except Exception as e:
            logger.warning(f"Brain log failed: {e}")

    def _make_mock_lead(self, lead_id: str) -> dict:
        reply = _MOCK_REPLIES.get(lead_id, _MOCK_DEFAULT)
        return {
            "id": lead_id,
            "name": "Test Company",
            "displayName": "Test Company",
            "email": "test@example.com",
            "phone": "+6281234567890",
            "reply_text": reply,
            "type": "Digital Agency",
            "status": "replied",
        }

    def process_replied_leads(self, dry_run: bool = False, lead_id: str = None) -> None:
        if lead_id:
            lead = get_lead_by_id(lead_id)
            if lead is None and lead_id.startswith("test"):
                lead = self._make_mock_lead(lead_id)
            leads = [lead] if lead else []
        else:
            leads = get_leads_by_status("replied")

        if not leads:
            logger.info("No replied leads to process.")
            return

        logger.info(f"Processing {len(leads)} lead(s)...")

        for lead in leads:
            if not lead:
                continue

            name = lead.get("name") or lead.get("displayName") or "Unknown"
            reply_text = lead.get("reply_text") or ""

            if not reply_text:
                logger.warning(
                    f"Lead {name} (id={lead.get('id')}) has no reply_text, skipping"
                )
                continue

            intent = self.classify_intent(reply_text, name)
            email_body, wa_msg = self.generate_response(intent, lead)

            if dry_run:
                logger.info(f"[DRY-RUN] Lead: {name} | Intent: {intent}")
                if email_body:
                    link = self.payment_link if intent == "BUY" else self.calendly_link
                    logger.info(f"[DRY-RUN] Response contains: {link}")
                else:
                    logger.info(f"[DRY-RUN] No response (REJECT — will mark lost)")
                continue

            if intent == "REJECT":
                update_lead_status(lead["id"], "lost")
                add_event_log(lead["id"], "closer_ran", f"intent={intent}")
                self._log_to_brain(lead, intent)
                logger.info(f"❌ {name}: REJECT → marked lost")
                continue

            if email_body:
                email = lead.get("email") or ""
                if email:
                    send_email(email, "Re: Our proposal", email_body)
                phone = lead.get("phone") or lead.get("internationalPhoneNumber") or ""
                if phone:
                    send_whatsapp(phone, wa_msg)

                new_status = "meeting_booked"
                update_lead_status(lead["id"], new_status)
                add_event_log(lead["id"], "closer_ran", f"intent={intent}")
                self._log_to_brain(lead, intent)
                link = self.payment_link if intent == "BUY" else self.calendly_link
                logger.info(f"✅ {name}: {intent} → sent {link}")
