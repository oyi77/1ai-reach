"""
CS Engine — Inbound auto-reply with knowledge base context.

Receives inbound WhatsApp messages, searches the KB for relevant answers,
generates AI-powered responses via Claude, tracks conversations in DB,
and escalates when the KB has no answers.

Cross-contamination guard: skips contacts in the cold-call funnel.

CLI test mode:
  python3 scripts/cs_engine.py --test --phone "628xxx@c.us" --message "Hello"
"""

import argparse
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from config import (
    CS_DEFAULT_PERSONA,
    CS_ESCALATION_TELEGRAM,
    CS_MAX_REPLIES_PER_MINUTE,
    CS_REPLY_DELAY_SECONDS,
    GENERATOR_MODEL,
)
from conversation_tracker import (
    _is_cold_lead,
    add_message,
    escalate,
    get_conversation_context,
    get_or_create_conversation,
)
from conversation_guard import run_all_checks
import re as _re

from kb_manager import search as _kb_search_raw, search_with_outcome_weighting
from senders import send_typing_indicator, send_whatsapp_session
from state_manager import init_db, add_event_log
import capi_tracker

from n8n_client import (
    notify_conversation_started,
    notify_escalation,
    notify_hot_lead,
    notify_purchase_signal,
)

from cs_outcomes import (
    init_outcomes_db,
    record_conversation_start,
    record_response_sent,
    record_user_reply,
    record_journey_step,
    record_final_outcome,
)
from cs_playbook import (
    get_playbook,
    AdaptiveContext,
)  # kept for future adaptive context features


def _is_purchase_signal(text: str) -> bool:
    """Return True if message looks like a payment confirmation."""
    markers = [
        "transfer",
        "tf",
        "bukti",
        "lunas",
        "bayar",
        "udah dikirim",
        "sudah dikirim",
    ]
    return any(m in text.lower() for m in markers)


def _is_shipping_complaint(text: str) -> bool:
    """Return True if message contains shipping cost complaints."""
    markers = ["ongkir mahal", "kemahalan", "jauh", "luar jawa", "pengiriman mahal"]
    return any(m in text.lower() for m in markers)


def _detect_user_type(text: str, conversation_id: int) -> str:
    """Detect user mindset based on behavior and message content."""
    text = text.lower()

    # 1. Bulk / Grosir
    if any(
        k in text
        for k in [
            "banyak",
            "grosir",
            "reseller",
            "partai",
        ]
    ):
        return "bulk"

    # 2. Urgent / Fast Response
    if any(
        k in text
        for k in ["sekarang", "cepat", "buru-buru", "hari ini", "kapan sampai", "besok"]
    ):
        return "urgent"

    # 3. Price Sensitive
    if any(
        k in text
        for k in ["mahal", "diskon", "kurangin", "nego", "murah mana", "turun harga"]
    ):
        return "price_sensitive"

    # 4. Friction / Skeptical
    if any(
        k in text
        for k in ["ragu", "takut tipu", "cod", "shopee aja", "bisa percaya", "aman gak"]
    ):
        return "friction"

    return "normal"


_FTS_UNSAFE = _re.compile(r"[^\w\s]", _re.UNICODE)


def _sanitize_fts_query(text: str) -> str:
    """Strip FTS5-unsafe chars (?, *, quotes, parens, etc.)."""
    return _FTS_UNSAFE.sub(" ", text).strip()


def kb_search(wa_number_id: str, query: str, limit: int = 5) -> list[dict]:
    clean = _sanitize_fts_query(query)
    if not clean:
        return []
    try:
        return _kb_search_raw(wa_number_id, clean, limit)
    except Exception as e:
        print(f"[cs_engine] KB search failed: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Rate limiter — in-memory, per session
# ---------------------------------------------------------------------------

# { session_name: [timestamp, timestamp, ...] }
_rate_log: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(session_name: str) -> bool:
    """Return True if we are OVER the rate limit for this session."""
    now = time.time()
    window = _rate_log[session_name]
    # Purge entries older than 60 seconds
    _rate_log[session_name] = [t for t in window if now - t < 60]
    return len(_rate_log[session_name]) >= CS_MAX_REPLIES_PER_MINUTE


def _record_reply(session_name: str) -> None:
    """Record a reply timestamp for rate limiting."""
    _rate_log[session_name].append(time.time())


# ---------------------------------------------------------------------------
# Language detection — simple heuristic
# ---------------------------------------------------------------------------

_INDONESIAN_MARKERS = frozenset(
    {
        # Core question words
        "apa",
        "apakah",
        "bagaimana",
        "berapa",
        "bisa",
        "boleh",
        "cara",
        "gimana",
        "kok",
        # Common words
        "dan",
        "dari",
        "dengan",
        "di",
        "harga",
        "ini",
        "itu",
        "jasa",
        "ke",
        "mau",
        "minta",
        "mohon",
        "nya",
        "saya",
        "selamat",
        "sudah",
        "untuk",
        "yang",
        # Sentence-final / colloquial particles
        "ga",
        "gak",
        "nggak",
        "dong",
        "deh",
        "si",
        "aja",
        "tuh",
        "nih",
        "lho",
        "loh",
        # Informal pronouns
        "gue",
        "gua",
        "aneh",
    }
)


def _detect_language(text: str) -> str:
    words = set(text.lower().split())
    matches = words & _INDONESIAN_MARKERS
    if len(matches) >= 1:
        return "id"
    return "en"


# ---------------------------------------------------------------------------
# Cross-contamination guard
# ---------------------------------------------------------------------------


def should_skip(contact_phone: str, wa_number_id: str) -> bool:
    """Return True if this contact is a cold-call lead — do NOT auto-reply."""
    return _is_cold_lead(contact_phone)


# ---------------------------------------------------------------------------
# Escalation logic
# ---------------------------------------------------------------------------


def should_escalate(message: str, kb_results: list[dict], conversation: dict) -> bool:
    """Escalate if no KB results AND 3+ consecutive unclear intents.

    We detect "unclear" by checking if the last 3 outbound messages in this
    conversation contained the escalation disclaimer (i.e., the agent could
    not confidently answer from the KB).
    """
    if kb_results:
        return False

    # Check recent conversation context for consecutive unclear turns
    conv_id = conversation.get("id")
    if not conv_id:
        return False

    ctx = get_conversation_context(conv_id, max_messages=10)
    if not ctx:
        return False

    # Count consecutive agent messages that had no confident KB answer
    # We'll use a simple signal: if the last N agent lines contain the
    # "I'll connect you" / escalation language, escalate now.
    agent_lines = [line for line in ctx.split("\n") if line.startswith("Agent:")]
    if len(agent_lines) < 2:
        return False

    # If last 2 agent replies had no KB match (indicated by empty kb_results
    # for current turn + checking message history), escalate.
    # Simple heuristic: if there are 3+ agent turns already and STILL no KB
    # match for the current message, escalate.
    if len(agent_lines) >= 3 and not kb_results:
        return True

    return False


# ---------------------------------------------------------------------------
# AI response generation
# ---------------------------------------------------------------------------


import llm_client


def generate_cs_response(
    conversation_context: str,
    kb_results: list[dict],
    persona: str,
    message: str,
    stage_context: str = "",
    user_type: str = "normal",
) -> str:
    """Generate a customer service response.

    Tries claude CLI, opencode CLI, Ollama, Groq in order.
    Falls back to KB answer or polite deferral if all fail.
    """
    lang = _detect_language(message)
    lang_instruction = (
        "Respond ENTIRELY in Bahasa Indonesia."
        if lang == "id"
        else "Respond in English."
    )

    # Adaptive Strategy Mapping
    strategies = {
        "normal": "Use soft closing. Guide the user gently to purchase.",
        "price_sensitive": "Emphasize value & suggest bundling / paket hemat for better price.",
        "urgent": "Fast closing mode. Minimal explanation, get payment info out quickly.",
        "bulk": "Offer cargo solution (KALOG) and emphasize pricing for volume.",
        "friction": "Address doubts briefly, offer marketplace link as a safe fallback solution.",
    }
    strategy_instruction = strategies.get(user_type, strategies["normal"])

    kb_context = ""
    if kb_results:
        kb_parts = []
        for i, r in enumerate(kb_results, 1):
            q = r.get("question", "")
            a = r.get("answer", "")
            kb_parts.append(f"[{i}] Q: {q}\n    A: {a}")
        kb_context = "\n".join(kb_parts)

    prompt_parts = [
        f"[SYSTEM]\n{persona}\n",
        "## RESPONSE STYLE (CRITICAL)\n"
        "- You are a REAL human CS agent chatting on WhatsApp. Sound natural and casual, NOT like a bot or AI.\n"
        "- Use informal Bahasa Indonesia: 'Kak', 'nih', 'ya', 'banget', 'dong', 'sih' — like chatting with a friend.\n"
        "- Keep it SHORT. 1-3 sentences max. Real people don't write essays on WhatsApp.\n"
        "- NO bullet points, NO numbered lists, NO emoji spam (max 1-2 per message).\n"
        "- NO markdown formatting whatsoever (no **, no ##, no *).\n"
        "- NEVER say 'Sebagai AI' or 'Saya adalah asisten' — you are a human agent.\n"
        "- Sound warm, friendly, and genuinely helpful — not salesy or pushy.\n\n",
        "## CONVERSATION APPROACH\n"
        "- Prioritize direct WhatsApp order. Only suggest marketplace if user complains about shipping.\n"
        "- Include a natural soft CTA when appropriate (e.g., 'Mau dicoba Kak?', 'Bisa kirim hari ini nih').\n"
        "- If user hesitates → suggest trying a smaller package first, don't push.\n"
        "- If user asks about price → be transparent, don't dodge the question.\n\n",
        f"## ADAPTIVE STRATEGY: {user_type.upper()}\n"
        f"Instruction: {strategy_instruction}\n",
        f"Language instruction: {lang_instruction}\n",
    ]

    if stage_context:
        prompt_parts.append(f"{stage_context}\n")

    if kb_context:
        prompt_parts.append(
            f"Knowledge base results (use these to ground your answer):\n{kb_context}\n"
        )
    else:
        prompt_parts.append(
            "No knowledge base results found for this question. "
            "If you cannot answer confidently, say you will check with the team "
            "and get back to them shortly.\n"
        )

    if conversation_context:
        prompt_parts.append(f"Conversation history:\n{conversation_context}\n")

    prompt_parts.append(
        f"[USER]\nCustomer's latest message: {message}\n\n"
        "Reply as a real human CS agent would on WhatsApp. Be concise, warm, and natural. "
        "If the KB has a relevant answer, use the information but rephrase in your own casual words. "
        "Output ONLY the reply text — no labels, no meta-commentary."
    )

    full_prompt = "\n".join(prompt_parts)

    # Try multi-provider LLM chain (claude → opencode → ollama → groq → openai)
    response = llm_client.generate(full_prompt)
    if response:
        return response

    # Fallback — use KB answer or polite deferral
    if kb_results:
        return kb_results[0].get("answer", "")

    if lang == "id":
        return "Oke Kak, makasih pertanyaannya! Saya cek dulu ya, bentar saja 👍"
    return "Hey, good question! Let me check on that and get back to you real quick."


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_inbound_message(
    wa_number_id: str,
    contact_phone: str,
    message_text: str,
    session_name: str = "default",
    voice_reply: bool = False,
    skip_send: bool = False,
) -> dict:
    """Process an inbound WhatsApp message and auto-reply.

    Returns a dict with keys: action, response, conversation_id, reason.
    """
    # 1. Cross-contamination guard
    from state_manager import get_wa_number_by_session

    wa_num_rec = get_wa_number_by_session(session_name)
    if wa_num_rec:
        own_phone = "".join(filter(str.isdigit, str(wa_num_rec.get("phone") or "")))
        clean_contact = "".join(filter(str.isdigit, str(contact_phone)))
        if own_phone and clean_contact == own_phone:
            return {
                "action": "skipped",
                "response": "",
                "conversation_id": 0,
                "reason": "Self-loop guard: contact is the bot itself",
            }

    if should_skip(contact_phone, wa_number_id):
        return {
            "action": "skipped",
            "response": "",
            "conversation_id": 0,
            "reason": "Contact is in cold-call funnel",
        }

    # 2. Rate limit check
    if _check_rate_limit(session_name):
        return {
            "action": "skipped",
            "response": "",
            "conversation_id": 0,
            "reason": f"Rate limit exceeded ({CS_MAX_REPLIES_PER_MINUTE}/min) for session {session_name}",
        }

    conv = get_or_create_conversation(wa_number_id, contact_phone, engine_mode="cs")
    conv_id = conv["id"]

    # Conversation guard - prevent infinite loops and agent-to-agent chatting
    should_skip, guard_reason = run_all_checks(
        conversation_id=conv_id,
        contact_phone=contact_phone,
        wa_number_id=wa_number_id,
        session_name=session_name,
        message_direction="in",
        message_text=message_text,
    )

    if should_skip:
        return {
            "action": "skipped",
            "response": "",
            "conversation_id": conv_id,
            "reason": f"Guard: {guard_reason}",
        }

    if conv.get("message_count", 0) <= 1:
        notify_conversation_started(contact_phone, session_name, wa_number_id)

    add_message(conv_id, direction="in", message_text=message_text)

    current_msg_count = conv.get("message_count", 0) + 1
    if current_msg_count >= 3:
        notify_hot_lead(contact_phone, current_msg_count, conv_id)

    # 4b. Track Meta CAPI - Lead (every new message is a fresh lead interaction)
    capi_tracker.track_lead(contact_phone)

    # 4c. Track Meta CAPI - Purchase (detect payment signals)
    if _is_purchase_signal(message_text):
        capi_tracker.track_purchase(contact_phone)
        notify_purchase_signal(contact_phone, message_text, conv_id)

    # 4d. Track Meta CAPI - AddToCart (detect shipping complaints -> likely shopee redirect)
    if _is_shipping_complaint(message_text):
        capi_tracker.track_atc(contact_phone)

    # 5. Search KB
    kb_results = kb_search(wa_number_id, message_text, limit=5)

    # 6. Check escalation
    if should_escalate(message_text, kb_results, conv):
        reason = "No KB match + repeated unclear turns"
        escalate(conv_id, reason=reason)

        notify_escalation(contact_phone, reason, conv_id)

        lang = _detect_language(message_text)
        if lang == "id":
            esc_msg = (
                "Bentar ya Kak, saya mau konfirmasi ke tim dulu biar jawabannya "
                "lebih pas. Tunggu sebentar ya! 😊"
            )
        else:
            esc_msg = (
                "Hey, let me check with our team to give you the best answer. "
                "Just a moment!"
            )

        # Send escalation message
        send_typing_indicator(session_name, contact_phone, typing=True)
        time.sleep(CS_REPLY_DELAY_SECONDS)
        send_whatsapp_session(contact_phone, esc_msg, session_name)
        send_typing_indicator(session_name, contact_phone, typing=False)

        add_message(conv_id, direction="out", message_text=esc_msg)

        return {
            "action": "escalated",
            "response": esc_msg,
            "conversation_id": conv_id,
            "reason": reason,
        }

    # 6b. Fetch session-specific persona
    from state_manager import get_wa_number_by_session

    wa_num = get_wa_number_by_session(session_name)
    persona = wa_num.get("persona") if wa_num else None
    if not persona:
        persona = CS_DEFAULT_PERSONA

    # 7. Advance sales stage
    from conversation_tracker import advance_stage, get_stage_context

    advance_stage(conv_id, message_text, kb_results)
    stage_context = get_stage_context(conv_id)

    # 7b. Detect User Type (Hybrid Adaptive Mode)
    user_type = _detect_user_type(message_text, conv_id)

    # 8. Generate response
    response_text = ""
    conversation_context = get_conversation_context(conv_id, max_messages=10)

    response_text = generate_cs_response(
        conversation_context,
        kb_results,
        persona,
        message_text,
        stage_context,
        user_type,
    )

    if not response_text:
        response_text = "Oke Kak, ditunggu ya! Saya bantu sekarang."

    # 9. Send reply with typing indicator
    if not skip_send:
        send_typing_indicator(session_name, contact_phone, typing=True)
        time.sleep(CS_REPLY_DELAY_SECONDS)

        # Voice reply mode
        if voice_reply:
            try:
                from voice_pipeline import generate_voice_reply

                voice_sent = generate_voice_reply(
                    response_text, session_name, contact_phone
                )
                if not voice_sent:
                    # Fallback to text
                    send_whatsapp_session(contact_phone, response_text, session_name)
            except Exception as e:
                print(f"Voice reply failed: {e}, falling back to text")
                send_whatsapp_session(contact_phone, response_text, session_name)
        else:
            send_whatsapp_session(contact_phone, response_text, session_name)

        send_typing_indicator(session_name, contact_phone, typing=False)

    # 10. Record outbound message
    add_message(conv_id, direction="out", message_text=response_text)

    # 11. Record for rate limiting
    _record_reply(session_name)

    return {
        "action": "replied",
        "response": response_text,
        "conversation_id": conv_id,
        "reason": "",
    }


# ---------------------------------------------------------------------------
# CLI test mode
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CS Engine — inbound auto-reply with KB context"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode (don't actually send WA)",
    )
    parser.add_argument(
        "--phone",
        default="628999888777@c.us",
        help="Contact phone (default: 628999888777@c.us)",
    )
    parser.add_argument(
        "--message",
        default="Berapa harga jasa pembuatan website?",
        help="Test message text",
    )
    parser.add_argument(
        "--session",
        default="default",
        help="WA session name (default: default)",
    )
    args = parser.parse_args()

    init_db()

    if args.test:
        # Monkey-patch senders to avoid real WA calls
        import senders as _senders

        _senders.send_whatsapp_session = lambda phone, msg, sess: (
            print(
                f"  [TEST] Would send WA to {phone} via session '{sess}':\n    {msg[:120]}..."
            ),
            True,
        )[1]
        _senders.send_typing_indicator = lambda sess, chat, typing=True: True

        # Also patch our module-level references
        import cs_engine as _self

        _self.send_whatsapp_session = _senders.send_whatsapp_session
        _self.send_typing_indicator = _senders.send_typing_indicator

    print(f"[cs_engine] Processing: phone={args.phone}, session={args.session}")
    print(f"[cs_engine] Message: {args.message}")
    print()

    result = handle_inbound_message(
        wa_number_id=args.session,
        contact_phone=args.phone,
        message_text=args.message,
        session_name=args.session,
    )

    print(f"[cs_engine] Result:")
    print(f"  action:          {result['action']}")
    print(f"  conversation_id: {result['conversation_id']}")
    print(f"  reason:          {result['reason']}")
    if result["response"]:
        print(f"  response:        {result['response'][:200]}")
    print()
    print("[cs_engine] Done.")
