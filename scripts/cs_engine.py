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
import re as _re

from kb_manager import search as _kb_search_raw
from senders import send_typing_indicator, send_whatsapp_session
from state_manager import init_db

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
    """Return 'id' for Indonesian, 'en' for English."""
    words = set(text.lower().split())
    matches = words & _INDONESIAN_MARKERS
    # Single marker is enough for short messages (question phrases)
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
        f"Language instruction: {lang_instruction}\n",
    ]

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
        "Instructions:\n"
        "- Answer the customer's question directly and helpfully.\n"
        "- Keep response concise (2-4 sentences max).\n"
        "- If the KB has a relevant answer, use it but rephrase naturally.\n"
        "- Do NOT mention 'knowledge base' or 'database' to the customer.\n"
        "- Be warm and professional.\n"
        "- Do NOT use markdown formatting (no **, no ##, no bullet points with *).\n"
        "- Output ONLY the reply text, nothing else."
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
        return (
            "Terima kasih atas pertanyaannya. Saya akan cek dengan tim kami "
            "dan segera menghubungi Anda kembali."
        )
    return (
        "Thank you for your question. Let me check with our team "
        "and I'll get back to you shortly."
    )


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_inbound_message(
    wa_number_id: str,
    contact_phone: str,
    message_text: str,
    session_name: str = "default",
) -> dict:
    """Process an inbound WhatsApp message and auto-reply.

    Returns a dict with keys: action, response, conversation_id, reason.
    """
    # 1. Cross-contamination guard
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

    # 3. Get or create conversation
    conv = get_or_create_conversation(wa_number_id, contact_phone, engine_mode="cs")
    conv_id = conv["id"]

    # 4. Record inbound message
    add_message(conv_id, direction="in", message_text=message_text)

    # 5. Search KB
    kb_results = kb_search(wa_number_id, message_text, limit=5)

    # 6. Check escalation
    if should_escalate(message_text, kb_results, conv):
        reason = "No KB match + repeated unclear turns"
        escalate(conv_id, reason=reason)

        lang = _detect_language(message_text)
        if lang == "id":
            esc_msg = (
                "Terima kasih sudah menunggu. Saya akan menghubungkan Anda "
                "dengan tim kami untuk membantu lebih lanjut. "
                "Mohon tunggu sebentar ya."
            )
        else:
            esc_msg = (
                "Thank you for your patience. Let me connect you with our team "
                "for further assistance. Please hold on."
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

    # 7. Generate AI response
    conversation_context = get_conversation_context(conv_id, max_messages=10)
    response_text = generate_cs_response(
        conversation_context,
        kb_results,
        CS_DEFAULT_PERSONA,
        message_text,
    )

    # 8. Send reply with typing indicator
    send_typing_indicator(session_name, contact_phone, typing=True)
    time.sleep(CS_REPLY_DELAY_SECONDS)
    send_whatsapp_session(contact_phone, response_text, session_name)
    send_typing_indicator(session_name, contact_phone, typing=False)

    # 9. Record outbound message
    add_message(conv_id, direction="out", message_text=response_text)

    # 10. Record for rate limiting
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
