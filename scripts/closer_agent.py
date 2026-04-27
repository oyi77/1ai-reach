"""
Closer agent — intent classification and conversational sales closer.

Classifies replied lead intent (BUY/INFO/REJECT/UNCLEAR) and sends
appropriate payment or calendar links. Replaces static meeting invites
with intelligent, intent-driven responses.

Run after reply_tracker.py in the pipeline.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import brain_client
from config import PAYMENT_LINK, CALENDLY_LINK, GENERATOR_MODEL
from senders import send_email, send_whatsapp
from state_manager import (
    get_lead_by_id,
    get_leads_by_status,
    update_lead,
    update_lead_status,
    add_event_log,
    init_db,
)

_VALID_INTENTS = {"BUY", "INFO", "REJECT", "UNCLEAR"}

_MOCK_REPLIES = {
    "test_buy": "I'm ready to proceed, please send the invoice.",
    "test_ready": "I'm ready to proceed, please send the invoice.",
    "test_reject": "Not interested, thank you.",
}
_MOCK_DEFAULT = "Can you tell me more about your services?"


# -------------------------------------------------------------------------
# Intent classification
# -------------------------------------------------------------------------


import llm_client


def classify_intent(reply_text: str, lead_name: str) -> str:
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
    return _classify_heuristic(reply_text)


def _classify_heuristic(text: str) -> str:
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


# -------------------------------------------------------------------------
# Response generation
# -------------------------------------------------------------------------


def generate_response(intent: str, lead: dict) -> tuple[str, str]:
    name = lead.get("name") or lead.get("displayName") or "there"
    if intent == "BUY":
        email_body = (
            f"Hi {name},\n\n"
            f"Great to hear you're ready to move forward! "
            f"Here's your payment link:\n\n"
            f"👉 {PAYMENT_LINK}\n\n"
            f"Once completed, we'll get started right away.\n\n"
            f"Best,\nVilona\nBerkahKarya"
        )
        wa_msg = f"Halo {name}! Senang sekali dengarnya 🙏\nBerikut link pembayarannya: {PAYMENT_LINK}"
        return email_body, wa_msg
    elif intent in ("INFO", "UNCLEAR"):
        email_body = (
            f"Hi {name},\n\n"
            f"Happy to answer your questions! "
            f"Let's jump on a quick call to discuss in detail:\n\n"
            f"👉 {CALENDLY_LINK}\n\n"
            f"Pick any time that works for you.\n\n"
            f"Best,\nVilona\nBerkahKarya"
        )
        wa_msg = f"Halo {name}! Yuk kita jadwalkan panggilan singkat untuk diskusi: {CALENDLY_LINK}"
        return email_body, wa_msg
    else:
        return "", ""


# -------------------------------------------------------------------------
# Brain logging (all wrapped in try/except)
# -------------------------------------------------------------------------


def _log_to_brain(lead: dict, intent: str) -> None:
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
        print(f"[closer] Brain log failed: {e}", file=sys.stderr)


# -------------------------------------------------------------------------
# Mock lead factory for --dry-run testing
# -------------------------------------------------------------------------


def _make_mock_lead(lead_id: str) -> dict:
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


# -------------------------------------------------------------------------
# Main processing
# -------------------------------------------------------------------------


def process_replied_leads(dry_run: bool = False, lead_id: str = None) -> None:
    if lead_id:
        lead = get_lead_by_id(lead_id)
        if lead is None and lead_id.startswith("test"):
            lead = _make_mock_lead(lead_id)
        leads = [lead] if lead else []
    else:
        leads = get_leads_by_status("replied")

    if not leads:
        print("No replied leads to process.")
        return

    print(f"[closer] Processing {len(leads)} lead(s)...")

    for lead in leads:
        if not lead:
            continue

        name = lead.get("name") or lead.get("displayName") or "Unknown"
        reply_text = lead.get("reply_text") or ""

        if not reply_text:
            print(f"  ⚠️ Lead {name} (id={lead.get('id')}) has no reply_text, skipping")
            continue

        intent = classify_intent(reply_text, name)
        email_body, wa_msg = generate_response(intent, lead)

        if dry_run:
            print(f"[DRY-RUN] Lead: {name} | Intent: {intent}")
            if email_body:
                link = PAYMENT_LINK if intent == "BUY" else CALENDLY_LINK
                print(f"[DRY-RUN] Response contains: {link}")
            else:
                print(f"[DRY-RUN] No response (REJECT — will mark lost)")
            continue

        if intent == "REJECT":
            update_lead_status(lead["id"], "lost")
            add_event_log(lead["id"], "closer_ran", f"intent={intent}")
            _log_to_brain(lead, intent)
            print(f"  ❌ {name}: REJECT → marked lost")
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
            _log_to_brain(lead, intent)
            link = PAYMENT_LINK if intent == "BUY" else CALENDLY_LINK
            print(f"  ✅ {name}: {intent} → sent {link}")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Closer agent — classify intent and send payment/calendar links"
    )
    parser.add_argument(
        "--lead-id", type=str, default=None, help="Process a single lead by ID"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview actions without sending"
    )
    args = parser.parse_args()

    init_db()
    process_replied_leads(dry_run=args.dry_run, lead_id=args.lead_id)


if __name__ == "__main__":
    main()
