import time
from datetime import datetime, timezone

from oneai_reach.infrastructure.legacy import brain_client
from oneai_reach.infrastructure.legacy import llm_client
from oneai_reach.infrastructure.legacy.closer_agent import classify_intent
from oneai_reach.infrastructure.legacy.conversation_tracker import (
    _is_cold_lead,
    add_message,
    get_conversation_context,
    get_messages,
    get_or_create_conversation,
    update_status,
)
from oneai_reach.infrastructure.legacy.senders import send_typing_indicator, send_whatsapp_session
from oneai_reach.infrastructure.legacy.state_manager import (
    _connect,
    add_event_log,
    get_conversation,
    get_lead_by_id,
    update_lead_status,
)
from oneai_reach.infrastructure.legacy.utils import safe_filename

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class WarmcallService:
    def __init__(self, config: Settings):
        self.config = config
        self.followup_intervals = config.warmcall.followup_intervals
        self.max_turns = config.warmcall.max_turns
        self.research_dir = Path(config.paths.research_dir)

    def _days_since(self, iso_str: str) -> float:
        try:
            dt = datetime.fromisoformat(str(iso_str)).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        except Exception:
            return 0

    def _outbound_turn_count(self, conversation_id: int) -> int:
        messages = get_messages(conversation_id, limit=200)
        return sum(1 for m in messages if m.get("direction") == "out")

    def _last_outbound_timestamp(self, conversation_id: int) -> str | None:
        messages = get_messages(conversation_id, limit=200)
        for m in reversed(messages):
            if m.get("direction") == "out":
                return m.get("timestamp")
        return None

    def _followup_interval(self, turn: int) -> float:
        intervals = self.followup_intervals
        if turn < len(intervals):
            return float(intervals[turn])
        return float(intervals[-1]) if intervals else 14.0

    def _load_research_brief(self, lead_id: str | None) -> str:
        if not lead_id:
            return ""
        lead = get_lead_by_id(lead_id)
        if not lead:
            return ""
        name = lead.get("displayName") or lead.get("name") or ""
        if not name:
            return ""
        path = self.research_dir / f"{lead_id}_{safe_filename(name)}.txt"
        if path.exists():
            try:
                return path.read_text().strip()
            except Exception:
                pass
        return ""

    def _phone_to_chat_id(self, phone: str) -> str:
        clean = "".join(ch for ch in str(phone) if ch.isdigit())
        if not clean.startswith("62"):
            clean = "62" + clean.lstrip("0")
        if not clean.endswith("@c.us"):
            return f"{clean}@c.us"
        return clean

    def _generate_message(self, prompt: str) -> str:
        result = llm_client.generate(prompt)
        if result:
            return result
        logger.warning("All LLM providers failed for warmcall message generation")
        return ""

    def start_warmcall(
        self,
        phone: str,
        name: str,
        context: str,
        session: str = "default",
        lead_id: str | None = None,
    ) -> dict:
        if _is_cold_lead(phone):
            return {
                "conversation_id": None,
                "status": "blocked",
                "message_sent": False,
                "error": "Contact is in cold-call funnel",
            }

        conv = get_or_create_conversation(
            session,
            phone,
            engine_mode="warmcall",
            contact_name=name,
            lead_id=lead_id,
        )
        conv_id = conv["id"]

        turns = self._outbound_turn_count(conv_id)
        if turns > 0:
            return {
                "conversation_id": conv_id,
                "status": "already_started",
                "message_sent": False,
                "error": f"Sequence already has {turns} outbound messages",
            }

        research = self._load_research_brief(lead_id)

        prompt = (
            "Write a short, casual WhatsApp follow-up message (3-5 sentences) in Indonesian.\n"
            "You are Vilona from BerkahKarya — an AI automation and digital marketing agency.\n\n"
            f"Prospect: {name}\n"
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

        message = self._generate_message(prompt)
        if not message:
            message = (
                f"Halo {name}! 👋 Saya Vilona dari BerkahKarya.\n\n"
                f"Saya baru aja lihat bisnis Kakak, dan jujur ada beberapa ide yang menarik "
                f"nih soal AI automation yang bisa bantu bikin operasional Kakak jadi lebih lancar.\n\n"
                f"Dari pada lama mikir, mending ngobrol sebentar aja? Bisa via WhatsApp atau Zoom, Kakak tentuin aja waktunya 😊"
            )

        chat_id = self._phone_to_chat_id(phone)
        send_typing_indicator(session, chat_id, typing=True)
        time.sleep(2)
        sent = send_whatsapp_session(phone, message, session)
        send_typing_indicator(session, chat_id, typing=False)

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

    def process_reply(self, conversation_id: int, message_text: str) -> dict:
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

        add_message(conversation_id, "in", message_text)

        contact_name = conv.get("contact_name") or "Prospect"
        intent = classify_intent(message_text, contact_name)
        logger.info(f"Warmcall conv {conversation_id}: intent={intent}")

        lead_id = conv.get("lead_id")

        if intent == "BUY":
            ack_msg = self._generate_message(
                "Write a very short (2-3 sentences) excited WhatsApp reply in Indonesian.\n"
                "Context: The prospect just said they want to proceed/buy.\n"
                "Thank them and say you'll send the meeting/payment link shortly.\n"
                "Output: Just the message text."
            )
            if not ack_msg:
                ack_msg = (
                    f"Wah senang banget Kak {contact_name}! 🙏🎉\n"
                    f"Oke saya langsung siapin detailnya ya, bentar aja!"
                )

            wa_number_id = conv.get("wa_number_id", "default")
            chat_id = self._phone_to_chat_id(conv.get("contact_phone", ""))
            send_typing_indicator(wa_number_id, chat_id, typing=True)
            time.sleep(1)
            sent = send_whatsapp_session(
                conv.get("contact_phone", ""), ack_msg, wa_number_id
            )
            send_typing_indicator(wa_number_id, chat_id, typing=False)

            if sent:
                add_message(conversation_id, "out", ack_msg)

            if lead_id:
                try:
                    update_lead_status(lead_id, "replied")
                    add_event_log(lead_id, "warmcall_buy", f"conv={conversation_id}")
                    from converter import process_replied_leads

                    process_replied_leads()
                except Exception as e:
                    logger.error(f"Converter trigger failed: {e}")

            update_status(conversation_id, "resolved")
            return {
                "intent": "BUY",
                "response_sent": sent,
                "action": "converter_triggered",
                "error": None,
            }

        if intent == "REJECT":
            close_msg = self._generate_message(
                "Write a very short (2 sentences) polite WhatsApp closing message in Indonesian.\n"
                "Context: The prospect declined the offer.\n"
                "Be gracious, thank them for their time, leave the door open.\n"
                "Output: Just the message text."
            )
            if not close_msg:
                close_msg = (
                    f"Siap Kak {contact_name}, makasih banyak ya udah mau ngobrol 🙏\n"
                    f"Kalau nanti butuh bantuan, kami selalu ada kok. Sukses terus buat bisnisnya!"
                )

            wa_number_id = conv.get("wa_number_id", "default")
            chat_id = self._phone_to_chat_id(conv.get("contact_phone", ""))
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

        conversation_context = get_conversation_context(
            conversation_id, max_messages=10
        )
        research = self._load_research_brief(lead_id)

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

        reply_msg = self._generate_message(prompt)
        if not reply_msg:
            reply_msg = (
                f"Makasih balasannya Kak {contact_name}! 🙏\n\n"
                f"Boleh ceritain lebih detail nggak kebutuhannya? Biar saya bisa bantuin "
                f"lebih tepat sasaran. Atau kalau mau, kita bisa panggilan singkat 15 menit aja, "
                f"biar lebih jelas."
            )

        turns = self._outbound_turn_count(conversation_id) + 1

        wa_number_id = conv.get("wa_number_id", "default")
        chat_id = self._phone_to_chat_id(conv.get("contact_phone", ""))
        send_typing_indicator(wa_number_id, chat_id, typing=True)
        time.sleep(2)
        sent = send_whatsapp_session(
            conv.get("contact_phone", ""), reply_msg, wa_number_id
        )
        send_typing_indicator(wa_number_id, chat_id, typing=False)

        if sent:
            add_message(conversation_id, "out", reply_msg)

        if turns >= self.max_turns:
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

    def get_due_followups(self) -> list[dict]:
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
            turns = self._outbound_turn_count(conv_id)

            if turns == 0 or turns >= self.max_turns:
                continue

            messages = get_messages(conv_id, limit=200)
            last_outbound_idx = -1
            for i, m in enumerate(messages):
                if m.get("direction") == "out":
                    last_outbound_idx = i

            if last_outbound_idx >= 0:
                for m in messages[last_outbound_idx + 1 :]:
                    if m.get("direction") == "in":
                        last_outbound_idx = -1
                        break

            if last_outbound_idx == -1:
                continue

            last_ts = self._last_outbound_timestamp(conv_id)
            if not last_ts:
                continue
            elapsed = self._days_since(last_ts)
            required = self._followup_interval(turns - 1)

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

    def send_scheduled_followup(self, conversation_id: int) -> dict:
        """Send the next follow-up message for a conversation."""
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

        turns = self._outbound_turn_count(conversation_id)

        if turns >= self.max_turns:
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

        last_ts = self._last_outbound_timestamp(conversation_id)
        if last_ts:
            elapsed = self._days_since(last_ts)
            required = self._followup_interval(turns - 1)
            if elapsed < required:
                return {
                    "sent": False,
                    "turn": turns,
                    "message": "",
                    "error": f"Too early: {elapsed:.1f} days elapsed, need {required:.0f}",
                }

        contact_name = conv.get("contact_name") or "Prospect"
        lead_id = conv.get("lead_id")
        research = self._load_research_brief(lead_id)
        conversation_context = get_conversation_context(
            conversation_id, max_messages=10
        )

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

        message = self._generate_message(prompt)
        if not message:
            if urgency == "final":
                message = (
                    f"Halo Kak {contact_name}, ini pesan terakhir dari saya ya 🙏\n"
                    f"Kalau suatu hari butuh bantuan AI automation atau digital marketing, "
                    f"kami selalu siap kok. Semoga bisnisnya makin sukses!"
                )
            else:
                message = (
                    f"Halo Kak {contact_name}! 👋\n"
                    f"Niat follow-up soal tawaran kami sebelumnya nih. "
                    f"Kalau Kakak berubah pikiran atau mau tanya-tanya, langsung balas aja ya, saya selalu cek 😊"
                )

        wa_number_id = conv.get("wa_number_id", "default")
        chat_id = self._phone_to_chat_id(conv.get("contact_phone", ""))
        send_typing_indicator(wa_number_id, chat_id, typing=True)
        time.sleep(2)
        sent = send_whatsapp_session(
            conv.get("contact_phone", ""), message, wa_number_id
        )
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

    def process_due_warmcalls(self) -> dict:
        """Process all warmcall conversations due for follow-up."""
        due = self.get_due_followups()
        if not due:
            logger.info("No warmcall follow-ups due")
            return {
                "total_due": 0,
                "sent": 0,
                "failed": 0,
                "cold_marked": 0,
                "errors": [],
            }

        logger.info(f"Processing {len(due)} due warmcall follow-ups")
        sent = 0
        failed = 0
        cold_marked = 0
        errors = []

        for item in due:
            conv_id = item["conversation_id"]
            name = item["contact_name"] or item["contact_phone"]
            turns = item["turns_sent"]

            logger.info(
                f"  [{conv_id}] {name} — turn {turns + 1}, "
                f"{item['days_since_last']}d since last"
            )

            result = self.send_scheduled_followup(conv_id)
            if result.get("sent"):
                sent += 1
                logger.info(f"    ✅ Follow-up #{result['turn']} sent")
            elif "Max turns" in str(result.get("error", "")):
                cold_marked += 1
                logger.info(f"    ❄️ Max turns reached — marked cold")
            else:
                failed += 1
                err = result.get("error", "unknown")
                errors.append(f"conv={conv_id}: {err}")
                logger.error(f"    ❌ Failed: {err}")

        summary = {
            "total_due": len(due),
            "sent": sent,
            "failed": failed,
            "cold_marked": cold_marked,
            "errors": errors,
        }
        logger.info(
            f"Done: {sent} sent, {cold_marked} cold, {failed} failed "
            f"out of {len(due)} due"
        )
        return summary

    def classify_intent(self, reply_text: str, lead_name: str) -> str:
        """Classify incoming reply intent using closer_agent."""
        return classify_intent(reply_text, lead_name)

    def generate_followup_message(
        self, conversation_id: int, turn: int, contact_name: str, lead_id: str | None
    ) -> str:
        """Generate personalized follow-up message based on turn number."""
        research = self._load_research_brief(lead_id)
        conversation_context = get_conversation_context(
            conversation_id, max_messages=10
        )

        turn_label = f"follow-up #{turn}" if turn > 1 else "first message"
        urgency = "gentle" if turn < 3 else ("moderate" if turn < 4 else "final")

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

        message = self._generate_message(prompt)
        if not message:
            if urgency == "final":
                message = (
                    f"Halo Kak {contact_name}, ini pesan terakhir dari saya ya 🙏\n"
                    f"Kalau suatu hari butuh bantuan AI automation atau digital marketing, "
                    f"kami selalu siap kok. Semoga bisnisnya makin sukses!"
                )
            else:
                message = (
                    f"Halo Kak {contact_name}! 👋\n"
                    f"Niat follow-up soal tawaran kami sebelumnya nih. "
                    f"Kalau Kakak berubah pikiran atau mau tanya-tanya, langsung balas aja ya, saya selalu cek 😊"
                )
        return message
