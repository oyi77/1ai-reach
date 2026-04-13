"""
Warmcall engine — multi-turn follow-up sequences with intent routing.

Manages personalized WhatsApp follow-up sequences for warm leads:
  - Starts a warmcall conversation with a personalized first message
  - Processes replies with intent classification (BUY/INFO/REJECT/UNCLEAR)
  - Sends scheduled follow-ups at configurable intervals
  - Routes BUY intent → converter flow (meeting booking)
  - Routes REJECT intent → mark cold immediately
  - Max turns enforcement → mark cold after WARMCALL_MAX_TURNS

Follow-up intervals (configurable via WARMCALL_FOLLOWUP_INTERVALS):
  Turn 1 → wait 1 day, Turn 2 → wait 3 days, Turn 3 → wait 7 days, Turn 4 → wait 14 days

CLI:
  python3 scripts/warmcall_engine.py --start --phone 628xxx --name "John" --context "Digital Agency" --session default
  python3 scripts/warmcall_engine.py --process-due
  python3 scripts/warmcall_engine.py --test
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from config import (
    GENERATOR_MODEL,
    RESEARCH_DIR,
    WARMCALL_FOLLOWUP_INTERVALS,
    WARMCALL_MAX_TURNS,
)
from closer_agent import classify_intent, _classify_heuristic
from conversation_tracker import (
    _is_cold_lead,
    add_message,
    get_conversation_context,
    get_messages,
    get_or_create_conversation,
    update_status,
)
from senders import send_typing_indicator, send_whatsapp_session
from state_manager import (
    _connect,
    add_event_log,
    get_lead_by_id,
    init_db,
    update_lead_status,
)
from utils import safe_filename


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _days_since(iso_str: str) -> float:
    """Return fractional days elapsed since the given ISO timestamp."""
    try:
        dt = datetime.fromisoformat(str(iso_str)).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return 0


def _outbound_turn_count(conversation_id: int) -> int:
    """Count how many outbound messages we have sent in this conversation."""
    messages = get_messages(conversation_id, limit=200)
    return sum(1 for m in messages if m.get("direction") == "out")


def _last_outbound_timestamp(conversation_id: int) -> str | None:
    """Return ISO timestamp of our last outbound message, or None."""
    messages = get_messages(conversation_id, limit=200)
    for m in reversed(messages):
        if m.get("direction") == "out":
            return m.get("timestamp")
    return None


def _followup_interval(turn: int) -> float:
    """Return wait-in-days for the given turn number (0-indexed from outbound count)."""
    intervals = WARMCALL_FOLLOWUP_INTERVALS
    if turn < len(intervals):
        return float(intervals[turn])
    # Beyond configured intervals, use the last interval
    return float(intervals[-1]) if intervals else 14.0


def _load_research_brief(lead_id: str | None) -> str:
    """Load research brief from data/research/ if available."""
    if not lead_id:
        return ""
    lead = get_lead_by_id(lead_id)
    if not lead:
        return ""
    name = lead.get("displayName") or lead.get("name") or ""
    if not name:
        return ""
    path = os.path.join(str(RESEARCH_DIR), f"{lead_id}_{safe_filename(name)}.txt")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def _phone_to_chat_id(phone: str) -> str:
    """Convert phone to WAHA chat ID format."""
    clean = "".join(ch for ch in str(phone) if ch.isdigit())
    if not clean.startswith("62"):
        clean = "62" + clean.lstrip("0")
    if not clean.endswith("@c.us"):
        return f"{clean}@c.us"
    return clean


def _generate_message(prompt: str) -> str:
    """Generate a message using the multi-provider LLM client."""
    import llm_client

    result = llm_client.generate(prompt)
    if result:
        return result
    print("[warmcall] All LLM providers failed", file=sys.stderr)
    return ""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def start_sequence(
    wa_number_id: str,
    contact_phone: str,
    contact_name: str,
    context: str,
    lead_id: str | None = None,
) -> dict:
    """Create a warmcall conversation and send the personalized first message.

    Args:
        wa_number_id: WAHA session name (e.g. "default")
        contact_phone: Prospect phone number
        contact_name: Prospect name
        context: Business context (vertical, pain points, etc.)
        lead_id: Optional link to leads table

    Returns:
        dict with keys: conversation_id, status, message_sent, error
    """
    # Cross-contamination guard: don't warmcall cold leads
    if _is_cold_lead(contact_phone):
        return {
            "conversation_id": None,
            "status": "blocked",
            "message_sent": False,
            "error": "Contact is in cold-call funnel — cannot start warmcall",
        }

    # Get or create conversation with engine_mode="warmcall"
    conv = get_or_create_conversation(
        wa_number_id,
        contact_phone,
        engine_mode="warmcall",
        contact_name=contact_name,
        lead_id=lead_id,
    )
    conv_id = conv["id"]

    # Check if we already have outbound messages (sequence already started)
    turns = _outbound_turn_count(conv_id)
    if turns > 0:
        return {
            "conversation_id": conv_id,
            "status": "already_started",
            "message_sent": False,
            "error": f"Sequence already has {turns} outbound messages",
        }

    # Load research brief for personalization
    research = _load_research_brief(lead_id)

    # Build first-message prompt
    prompt = (
        "Write a short, casual WhatsApp follow-up message (3-5 sentences) in Indonesian.\n"
        "You are Vilona from BerkahKarya — an AI automation and digital marketing agency.\n\n"
        f"Prospect: {contact_name}\n"
        f"Business context: {context}\n"
    )
    if research:
        prompt += f"\nResearch brief:\n{research[:1500]}\n"
    prompt += (
        "\nTone: Warm, professional but friendly. Reference something specific about their business.\n"
        "Goal: Re-engage the prospect and offer value. Do NOT be pushy.\n"
        "Include a soft call-to-action (e.g., ask if they'd like to chat).\n"
        "Output: Just the WhatsApp message text, nothing else."
    )

    message = _generate_message(prompt)
    if not message:
        # Static fallback
        message = (
            f"Halo {contact_name}! 👋\n\n"
            f"Saya Vilona dari BerkahKarya. Kami baru saja melihat bisnis Anda "
            f"dan punya beberapa ide menarik tentang bagaimana AI automation bisa "
            f"membantu meningkatkan operasional Anda.\n\n"
            f"Apakah ada waktu untuk ngobrol sebentar minggu ini? 😊"
        )

    # Send via WhatsApp session
    chat_id = _phone_to_chat_id(contact_phone)
    send_typing_indicator(wa_number_id, chat_id, typing=True)
    time.sleep(2)
    sent = send_whatsapp_session(contact_phone, message, wa_number_id)
    send_typing_indicator(wa_number_id, chat_id, typing=False)

    if sent:
        add_message(conv_id, "out", message)
        if lead_id:
            try:
                add_event_log(lead_id, "warmcall_started", f"conv={conv_id}")
            except Exception:
                pass
        return {
            "conversation_id": conv_id,
            "status": "started",
            "message_sent": True,
            "error": None,
        }
    else:
        return {
            "conversation_id": conv_id,
            "status": "send_failed",
            "message_sent": False,
            "error": "WhatsApp send failed",
        }


def process_reply(conversation_id: int, message_text: str) -> dict:
    """Classify incoming reply intent and generate contextual follow-up.

    Args:
        conversation_id: Active warmcall conversation ID
        message_text: The prospect's reply text

    Returns:
        dict with keys: intent, response_sent, action, error
    """
    from state_manager import get_conversation

    conv = get_conversation(conversation_id)
    if not conv:
        return {
            "intent": None,
            "response_sent": False,
            "action": "error",
            "error": f"Conversation {conversation_id} not found",
        }

    if conv.get("status") != "active":
        return {
            "intent": None,
            "response_sent": False,
            "action": "skipped",
            "error": f"Conversation is {conv.get('status')}, not active",
        }

    if conv.get("engine_mode") != "warmcall":
        return {
            "intent": None,
            "response_sent": False,
            "action": "skipped",
            "error": f"Conversation mode is {conv.get('engine_mode')}, not warmcall",
        }

    # Record inbound message
    add_message(conversation_id, "in", message_text)

    # Classify intent
    contact_name = conv.get("contact_name") or "Prospect"
    intent = classify_intent(message_text, contact_name)
    print(f"[warmcall] Conv {conversation_id}: intent={intent}")

    lead_id = conv.get("lead_id")

    # ---- BUY intent → trigger converter flow ----
    if intent == "BUY":
        # Send acknowledgement
        ack_msg = _generate_message(
            "Write a very short (2-3 sentences) excited WhatsApp reply in Indonesian.\n"
            "Context: The prospect just said they want to proceed/buy.\n"
            "Thank them and say you'll send the meeting/payment link shortly.\n"
            "Output: Just the message text."
        )
        if not ack_msg:
            ack_msg = (
                f"Terima kasih banyak {contact_name}! 🙏🎉\n"
                f"Senang sekali mendengarnya! Saya akan segera kirimkan detail selanjutnya."
            )

        wa_number_id = conv.get("wa_number_id", "default")
        chat_id = _phone_to_chat_id(conv.get("contact_phone", ""))
        send_typing_indicator(wa_number_id, chat_id, typing=True)
        time.sleep(1)
        sent = send_whatsapp_session(
            conv.get("contact_phone", ""), ack_msg, wa_number_id
        )
        send_typing_indicator(wa_number_id, chat_id, typing=False)

        if sent:
            add_message(conversation_id, "out", ack_msg)

        # Trigger converter flow if lead_id exists
        if lead_id:
            try:
                update_lead_status(lead_id, "replied")
                add_event_log(lead_id, "warmcall_buy", f"conv={conversation_id}")
                # Import converter to trigger meeting booking
                from converter import process_replied_leads

                process_replied_leads()
            except Exception as e:
                print(f"[warmcall] Converter trigger failed: {e}", file=sys.stderr)

        update_status(conversation_id, "resolved")
        return {
            "intent": "BUY",
            "response_sent": sent,
            "action": "converter_triggered",
            "error": None,
        }

    # ---- REJECT intent → mark cold ----
    if intent == "REJECT":
        # Send polite close
        close_msg = _generate_message(
            "Write a very short (2 sentences) polite WhatsApp closing message in Indonesian.\n"
            "Context: The prospect declined the offer.\n"
            "Be gracious, thank them for their time, leave the door open.\n"
            "Output: Just the message text."
        )
        if not close_msg:
            close_msg = (
                f"Terima kasih atas waktunya {contact_name} 🙏\n"
                f"Jika suatu saat butuh bantuan, jangan ragu untuk menghubungi kami."
            )

        wa_number_id = conv.get("wa_number_id", "default")
        chat_id = _phone_to_chat_id(conv.get("contact_phone", ""))
        sent = send_whatsapp_session(
            conv.get("contact_phone", ""), close_msg, wa_number_id
        )
        if sent:
            add_message(conversation_id, "out", close_msg)

        update_status(conversation_id, "cold")
        if lead_id:
            try:
                update_lead_status(lead_id, "lost")
                add_event_log(lead_id, "warmcall_reject", f"conv={conversation_id}")
            except Exception:
                pass

        return {
            "intent": "REJECT",
            "response_sent": sent,
            "action": "marked_cold",
            "error": None,
        }

    # ---- INFO / UNCLEAR → generate contextual follow-up ----
    conversation_context = get_conversation_context(conversation_id, max_messages=10)
    research = _load_research_brief(lead_id)

    prompt = (
        "Write a short WhatsApp follow-up reply (3-5 sentences) in Indonesian.\n"
        "You are Vilona from BerkahKarya (AI automation & digital marketing agency).\n\n"
        f"Prospect: {contact_name}\n"
        f"Their latest message: {message_text}\n\n"
        f"Conversation so far:\n{conversation_context}\n\n"
    )
    if research:
        prompt += f"Research about their business:\n{research[:1000]}\n\n"
    if intent == "INFO":
        prompt += (
            "They want more information. Answer their question helpfully.\n"
            "Reference BerkahKarya's AI automation, digital marketing, and software dev capabilities.\n"
            "Include a soft CTA (suggest a quick call or send a case study).\n"
        )
    else:
        prompt += (
            "Their intent is unclear. Be helpful and try to understand what they need.\n"
            "Ask a clarifying question to move the conversation forward.\n"
        )
    prompt += "Output: Just the WhatsApp message text, nothing else."

    reply_msg = _generate_message(prompt)
    if not reply_msg:
        reply_msg = (
            f"Terima kasih atas balasannya {contact_name}! 🙏\n\n"
            f"Boleh saya tahu lebih detail tentang kebutuhan Anda? "
            f"Kami bisa atur panggilan singkat 15 menit untuk diskusi lebih lanjut."
        )

    # Check max turns before sending
    turns = _outbound_turn_count(conversation_id) + 1  # +1 for this reply
    if turns >= WARMCALL_MAX_TURNS:
        # Send the reply but mark cold after
        pass

    wa_number_id = conv.get("wa_number_id", "default")
    chat_id = _phone_to_chat_id(conv.get("contact_phone", ""))
    send_typing_indicator(wa_number_id, chat_id, typing=True)
    time.sleep(2)
    sent = send_whatsapp_session(conv.get("contact_phone", ""), reply_msg, wa_number_id)
    send_typing_indicator(wa_number_id, chat_id, typing=False)

    if sent:
        add_message(conversation_id, "out", reply_msg)

    # After max turns, mark cold
    if turns >= WARMCALL_MAX_TURNS:
        update_status(conversation_id, "cold")
        if lead_id:
            try:
                update_lead_status(lead_id, "cold")
                add_event_log(
                    lead_id,
                    "warmcall_max_turns",
                    f"conv={conversation_id} turns={turns}",
                )
            except Exception:
                pass
        return {
            "intent": intent,
            "response_sent": sent,
            "action": "max_turns_cold",
            "error": None,
        }

    if lead_id:
        try:
            add_event_log(
                lead_id,
                "warmcall_reply",
                f"conv={conversation_id} intent={intent}",
            )
        except Exception:
            pass

    return {
        "intent": intent,
        "response_sent": sent,
        "action": "replied",
        "error": None,
    }


def send_scheduled_followup(conversation_id: int) -> dict:
    """Send the next follow-up message for a conversation based on interval config.

    Args:
        conversation_id: Active warmcall conversation ID

    Returns:
        dict with keys: sent, turn, message, error
    """
    from state_manager import get_conversation

    conv = get_conversation(conversation_id)
    if not conv:
        return {
            "sent": False,
            "turn": 0,
            "message": "",
            "error": "Conversation not found",
        }

    if conv.get("status") != "active":
        return {
            "sent": False,
            "turn": 0,
            "message": "",
            "error": f"Conversation is {conv.get('status')}, not active",
        }

    turns = _outbound_turn_count(conversation_id)

    # Max turns check
    if turns >= WARMCALL_MAX_TURNS:
        update_status(conversation_id, "cold")
        lead_id = conv.get("lead_id")
        if lead_id:
            try:
                update_lead_status(lead_id, "cold")
                add_event_log(
                    lead_id,
                    "warmcall_max_turns",
                    f"conv={conversation_id} turns={turns}",
                )
            except Exception:
                pass
        return {
            "sent": False,
            "turn": turns,
            "message": "",
            "error": "Max turns reached — marked cold",
        }

    # Check timing — has enough time elapsed since our last outbound?
    last_ts = _last_outbound_timestamp(conversation_id)
    if last_ts:
        elapsed = _days_since(last_ts)
        required = _followup_interval(turns - 1)  # turn index is 0-based from prev turn
        if elapsed < required:
            return {
                "sent": False,
                "turn": turns,
                "message": "",
                "error": f"Too early: {elapsed:.1f} days elapsed, need {required:.0f}",
            }

    contact_name = conv.get("contact_name") or "Prospect"
    lead_id = conv.get("lead_id")
    research = _load_research_brief(lead_id)
    conversation_context = get_conversation_context(conversation_id, max_messages=10)

    # Generate follow-up based on turn number
    turn_label = f"follow-up #{turns + 1}" if turns > 0 else "first message"
    urgency = "gentle" if turns < 2 else ("moderate" if turns < 3 else "final")

    prompt = (
        f"Write a short WhatsApp {turn_label} message (3-4 sentences) in Indonesian.\n"
        f"You are Vilona from BerkahKarya (AI automation & digital marketing agency).\n\n"
        f"Prospect: {contact_name}\n"
        f"This is {turn_label} — urgency level: {urgency}.\n"
    )
    if conversation_context:
        prompt += f"\nConversation history:\n{conversation_context}\n"
    if research:
        prompt += f"\nResearch about their business:\n{research[:1000]}\n"
    if urgency == "final":
        prompt += (
            "\nThis is the final follow-up. Be gracious, leave the door open.\n"
            "Mention you won't bother them again unless they reach out.\n"
        )
    else:
        prompt += (
            "\nProvide new value — share a relevant insight, case study reference, or offer.\n"
            "Do NOT repeat the same message as before. Be creative.\n"
            "Include a soft CTA.\n"
        )
    prompt += "Output: Just the WhatsApp message text, nothing else."

    message = _generate_message(prompt)
    if not message:
        if urgency == "final":
            message = (
                f"Halo {contact_name}, ini pesan terakhir dari saya 🙏\n"
                f"Jika suatu saat butuh bantuan AI automation atau digital marketing, "
                f"kami selalu siap membantu. Sukses selalu!"
            )
        else:
            message = (
                f"Halo {contact_name}! 👋\n"
                f"Saya ingin follow-up tentang tawaran kami sebelumnya. "
                f"Apakah ada waktu untuk ngobrol singkat? 😊"
            )

    wa_number_id = conv.get("wa_number_id", "default")
    chat_id = _phone_to_chat_id(conv.get("contact_phone", ""))
    send_typing_indicator(wa_number_id, chat_id, typing=True)
    time.sleep(2)
    sent = send_whatsapp_session(conv.get("contact_phone", ""), message, wa_number_id)
    send_typing_indicator(wa_number_id, chat_id, typing=False)

    if sent:
        add_message(conversation_id, "out", message)
        if lead_id:
            try:
                add_event_log(
                    lead_id,
                    "warmcall_followup",
                    f"conv={conversation_id} turn={turns + 1}",
                )
            except Exception:
                pass

    return {
        "sent": sent,
        "turn": turns + 1,
        "message": message if sent else "",
        "error": None if sent else "WhatsApp send failed",
    }


def get_due_followups() -> list[dict]:
    """Return warmcall conversations that are due for a follow-up.

    A conversation is due when:
      - engine_mode = "warmcall"
      - status = "active"
      - No inbound message more recent than our last outbound (prospect didn't reply)
      - Enough days have elapsed since our last outbound (per interval config)
      - We haven't exceeded WARMCALL_MAX_TURNS

    Returns:
        List of dicts with: conversation_id, contact_name, contact_phone,
        turns_sent, days_since_last, required_interval, lead_id
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM conversations "
            "WHERE engine_mode = 'warmcall' AND status = 'active' "
            "ORDER BY last_message_at ASC"
        ).fetchall()
    finally:
        conn.close()

    due = []
    for row in rows:
        conv = dict(row)
        conv_id = conv["id"]
        turns = _outbound_turn_count(conv_id)

        # Skip if no messages sent yet (shouldn't happen for started sequences)
        if turns == 0:
            continue

        # Skip if max turns reached
        if turns >= WARMCALL_MAX_TURNS:
            continue

        # Check if prospect replied after our last outbound (don't follow up if they did)
        messages = get_messages(conv_id, limit=200)
        last_outbound_idx = -1
        last_inbound_after = False
        for i, m in enumerate(messages):
            if m.get("direction") == "out":
                last_outbound_idx = i
        if last_outbound_idx >= 0:
            for m in messages[last_outbound_idx + 1 :]:
                if m.get("direction") == "in":
                    last_inbound_after = True
                    break

        # If prospect replied, skip (process_reply should handle it)
        if last_inbound_after:
            continue

        # Check elapsed time
        last_ts = _last_outbound_timestamp(conv_id)
        if not last_ts:
            continue
        elapsed = _days_since(last_ts)
        required = _followup_interval(turns - 1)

        if elapsed >= required:
            due.append(
                {
                    "conversation_id": conv_id,
                    "contact_name": conv.get("contact_name", ""),
                    "contact_phone": conv.get("contact_phone", ""),
                    "turns_sent": turns,
                    "days_since_last": round(elapsed, 1),
                    "required_interval": required,
                    "lead_id": conv.get("lead_id"),
                }
            )

    return due


def process_all_due() -> dict:
    """Main loop entry — process all warmcall conversations due for follow-up.

    Returns:
        dict with keys: total_due, sent, failed, cold_marked, errors
    """
    due = get_due_followups()
    if not due:
        print("[warmcall] No follow-ups due.")
        return {
            "total_due": 0,
            "sent": 0,
            "failed": 0,
            "cold_marked": 0,
            "errors": [],
        }

    print(f"[warmcall] Processing {len(due)} due follow-ups...")
    sent = 0
    failed = 0
    cold_marked = 0
    errors = []

    for item in due:
        conv_id = item["conversation_id"]
        name = item["contact_name"] or item["contact_phone"]
        turns = item["turns_sent"]

        print(
            f"  [{conv_id}] {name} — turn {turns + 1}, "
            f"{item['days_since_last']}d since last"
        )

        result = send_scheduled_followup(conv_id)
        if result.get("sent"):
            sent += 1
            print(f"    ✅ Follow-up #{result['turn']} sent")
        elif "Max turns" in str(result.get("error", "")):
            cold_marked += 1
            print(f"    ❄️ Max turns reached — marked cold")
        else:
            failed += 1
            err = result.get("error", "unknown")
            errors.append(f"conv={conv_id}: {err}")
            print(f"    ❌ Failed: {err}")

    summary = {
        "total_due": len(due),
        "sent": sent,
        "failed": failed,
        "cold_marked": cold_marked,
        "errors": errors,
    }
    print(
        f"\n[warmcall] Done: {sent} sent, {cold_marked} cold, {failed} failed "
        f"out of {len(due)} due"
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_test() -> None:
    """Simulate a 3-turn warmcall sequence without sending real messages."""
    print("[warmcall] Running test mode...")
    init_db()

    # Monkey-patch via globals() so __main__ module sees the patches
    # (avoids the classic __main__ vs module dual-import problem)
    _g = globals()

    _send_log: list[str] = []

    def _mock_send(phone, message, session):
        _send_log.append(f"→ {phone}: {message[:80]}...")
        return True

    def _mock_typing(*a, **kw):
        return True

    _orig_send = _g.get("send_whatsapp_session")
    _orig_typing = _g.get("send_typing_indicator")
    _orig_generate = _g.get("_generate_message")
    _orig_classify = _g.get("classify_intent")

    _g["send_whatsapp_session"] = _mock_send
    _g["send_typing_indicator"] = _mock_typing

    # Patch _generate_message to avoid real Claude calls
    _turn_messages = [
        "Halo Test! Saya Vilona dari BerkahKarya. Kami punya solusi AI menarik. Ada waktu ngobrol? 😊",
        "Terima kasih atas minatnya! Kami bisa bantu optimasi proses bisnis dengan AI automation. Mau jadwalkan panggilan?",
        "Halo lagi! Ini follow-up terakhir. Jika butuh bantuan, kami selalu siap. Sukses selalu! 🙏",
    ]
    _turn_counter = {"n": 0}

    def _mock_generate(prompt):
        idx = min(_turn_counter["n"], len(_turn_messages) - 1)
        _turn_counter["n"] += 1
        return _turn_messages[idx]

    _g["_generate_message"] = _mock_generate

    # Patch classify_intent to use heuristic only (no Claude call)
    _g["classify_intent"] = lambda text, name: _classify_heuristic(text)

    # Also patch time.sleep to not actually sleep
    original_sleep = time.sleep
    time.sleep = lambda *a: None

    try:
        # Turn 1: Start sequence
        print("\n--- Turn 1: Start sequence ---")
        result = start_sequence(
            wa_number_id="test_session",
            contact_phone="628111222333",
            contact_name="Test Company",
            context="Digital Agency in Jakarta — needs AI automation",
        )
        print(f"  Result: {result}")
        assert result["status"] == "started", (
            f"Expected 'started', got {result['status']}"
        )
        conv_id = result["conversation_id"]

        # Turn 2: Simulate prospect reply (INFO intent)
        print("\n--- Turn 2: Process INFO reply ---")
        result2 = process_reply(conv_id, "Bisa ceritakan lebih detail tentang jasanya?")
        print(f"  Result: {result2}")
        assert result2["intent"] == "INFO", f"Expected INFO, got {result2['intent']}"
        assert result2["response_sent"], "Expected response to be sent"

        # Turn 3: Simulate another reply (UNCLEAR → follow-up)
        print("\n--- Turn 3: Process UNCLEAR reply ---")
        result3 = process_reply(conv_id, "Ok")
        print(f"  Result: {result3}")
        assert result3["response_sent"], "Expected response to be sent"

        # Verify due follow-ups (should be empty since we just replied)
        print("\n--- Check due follow-ups ---")
        due = get_due_followups()
        print(f"  Due: {len(due)} conversations")

        print(f"\n[warmcall] Test passed ✓ (sent {len(_send_log)} messages)")
        for log in _send_log:
            print(f"  {log}")

    finally:
        time.sleep = original_sleep
        # Restore originals
        if _orig_send:
            _g["send_whatsapp_session"] = _orig_send
        if _orig_typing:
            _g["send_typing_indicator"] = _orig_typing
        if _orig_generate:
            _g["_generate_message"] = _orig_generate
        if _orig_classify:
            _g["classify_intent"] = _orig_classify


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Warmcall engine — multi-turn follow-up sequences with intent routing"
    )
    parser.add_argument(
        "--start", action="store_true", help="Start a new warmcall sequence"
    )
    parser.add_argument("--phone", type=str, help="Contact phone number (for --start)")
    parser.add_argument("--name", type=str, help="Contact name (for --start)")
    parser.add_argument("--context", type=str, help="Business context (for --start)")
    parser.add_argument(
        "--session",
        type=str,
        default="default",
        help="WAHA session name (default: default)",
    )
    parser.add_argument("--lead-id", type=str, default=None, help="Link to lead ID")
    parser.add_argument(
        "--process-due",
        action="store_true",
        help="Process all due warmcall follow-ups",
    )
    parser.add_argument("--test", action="store_true", help="Run simulated 3-turn test")
    args = parser.parse_args()

    if args.test:
        _run_test()
        return

    init_db()

    if args.start:
        if not args.phone or not args.name:
            parser.error("--start requires --phone and --name")
        result = start_sequence(
            wa_number_id=args.session,
            contact_phone=args.phone,
            contact_name=args.name,
            context=args.context or "",
            lead_id=args.lead_id,
        )
        print(f"Result: {result}")

    elif args.process_due:
        result = process_all_due()
        print(f"Summary: {result}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
