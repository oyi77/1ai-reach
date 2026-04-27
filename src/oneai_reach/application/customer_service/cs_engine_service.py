"""CS Engine service - main customer service response engine."""

import re
import time
from collections import defaultdict
from collections.abc import Iterable

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


def _normalize_kb_results(kb_results: object) -> list[dict]:
    if not isinstance(kb_results, Iterable) or isinstance(kb_results, (str, bytes)):
        return []

    normalized = []
    for result in kb_results:
        if isinstance(result, dict):
            normalized.append(result)
    return normalized

# Response throttling to prevent rapid back-and-forth conversation loops
_LAST_RESPONSE_TIME: dict[str, float] = {}
_THROTTLE_SECONDS = 2
_THROTTLE_MAX_ENTRIES = 500

_FTS_UNSAFE = re.compile(r"[^\w\s]", re.UNICODE)

_INDONESIAN_MARKERS = frozenset(
    {
        "apa",
        "apakah",
        "bagaimana",
        "berapa",
        "bisa",
        "boleh",
        "cara",
        "gimana",
        "kok",
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
        "gue",
        "gua",
        "aneh",
    }
)


def _should_throttle_response(conv_key: str) -> bool:
    """Check if response should be throttled (less than 2 seconds since last response)."""
    if len(_LAST_RESPONSE_TIME) > _THROTTLE_MAX_ENTRIES:
        _LAST_RESPONSE_TIME.clear()

    if conv_key not in _LAST_RESPONSE_TIME:
        _LAST_RESPONSE_TIME[conv_key] = time.time()
        return False

    elapsed = time.time() - _LAST_RESPONSE_TIME[conv_key]
    if elapsed < _THROTTLE_SECONDS:
        return True

    _LAST_RESPONSE_TIME[conv_key] = time.time()
    return False


class CSEngineService:
    """Main customer service response engine with KB context and AI generation."""

    def __init__(
        self,
        config: Settings,
        conversation_service,
        outcomes_service,
        playbook_service,
        product_search_service=None,
    ):
        self.config = config
        self.conversation_service = conversation_service
        self.outcomes_service = outcomes_service
        self.playbook_service = playbook_service
        self.product_search_service = product_search_service
        self._rate_log: dict[str, list[float]] = defaultdict(list)

    def _sanitize_fts_query(self, text: str) -> str:
        return _FTS_UNSAFE.sub(" ", text).strip()

    def kb_search(self, wa_number_id: str, query: str, limit: int = 5) -> list[dict]:
        clean = self._sanitize_fts_query(query)
        if not clean:
            return []
        try:
            from oneai_reach.infrastructure.legacy.state_manager import search_kb

            return search_kb(wa_number_id, clean, limit)
        except Exception as e:
            logger.error(f"KB search failed: {e}")
            return []

    def _check_rate_limit(self, session_name: str) -> bool:
        now = time.time()
        window = self._rate_log[session_name]
        self._rate_log[session_name] = [t for t in window if now - t < 60]
        return (
            len(self._rate_log[session_name]) >= self.config.cs.max_replies_per_minute
        )

    def _record_reply(self, session_name: str) -> None:
        self._rate_log[session_name].append(time.time())

    def _detect_language(self, text: str) -> str:
        words = set(text.lower().split())
        matches = words & _INDONESIAN_MARKERS
        if len(matches) >= 1:
            return "id"
        return "en"

    def _is_purchase_signal(self, text: str) -> bool:
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

    def _is_shipping_complaint(self, text: str) -> bool:
        markers = ["ongkir mahal", "kemahalan", "jauh", "luar jawa", "pengiriman mahal"]
        return any(m in text.lower() for m in markers)

    def _detect_user_type(self, text: str, conversation_id: int) -> str:
        text = text.lower()

        if any(k in text for k in ["banyak", "grosir", "reseller", "partai"]):
            return "bulk"

        if any(
            k in text
            for k in [
                "sekarang",
                "cepat",
                "buru-buru",
                "hari ini",
                "kapan sampai",
                "besok",
            ]
        ):
            return "urgent"

        if any(
            k in text
            for k in [
                "mahal",
                "diskon",
                "kurangin",
                "nego",
                "murah mana",
                "turun harga",
            ]
        ):
            return "price_sensitive"

        if any(
            k in text
            for k in [
                "ragu",
                "takut tipu",
                "cod",
                "shopee aja",
                "bisa percaya",
                "aman gak",
            ]
        ):
            return "friction"

        return "normal"

    def should_skip(self, contact_phone: str, wa_number_id: str) -> bool:
        return self.conversation_service.is_cold_lead(contact_phone)

    def should_escalate(
        self, message: str, kb_results: list[dict], conversation: dict
    ) -> bool:
        kb_results = _normalize_kb_results(kb_results)
        if kb_results:
            return False

        conv_id = conversation.get("id")
        if not conv_id:
            return False

        ctx = self.conversation_service.get_conversation_context(
            conv_id, max_messages=10
        )
        if not ctx:
            return False

        agent_lines = [line for line in ctx.split("\n") if line.startswith("Agent:")]
        if len(agent_lines) < 2:
            return False

        if len(agent_lines) >= 3 and not kb_results:
            return True

        return False

    def generate_cs_response(
        self,
        conversation_context: str,
        kb_results: list[dict],
        persona: str,
        message: str,
        stage_context: str = "",
        user_type: str = "normal",
        product_results: list = None,
    ) -> str:
        kb_results = _normalize_kb_results(kb_results)
        lang = self._detect_language(message)
        lang_instruction = (
            "Respond ENTIRELY in Bahasa Indonesia."
            if lang == "id"
            else "Respond in English."
        )

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

        product_context = ""
        if product_results and self.product_search_service:
            product_context = self.product_search_service.format_products_for_llm(
                product_results
            )

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

        if product_context:
            prompt_parts.append(
                f"Available products (mention these naturally if relevant):\n{product_context}\n"
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

        from oneai_reach.infrastructure.legacy import llm_client

        response = llm_client.generate(full_prompt)
        if response:
            return response

        if kb_results:
            return kb_results[0].get("answer", "")

        if lang == "id":
            return "Oke Kak, makasih pertanyaannya! Saya cek dulu ya, bentar saja 👍"
        return (
            "Hey, good question! Let me check on that and get back to you real quick."
        )

    def handle_inbound_message(
        self,
        wa_number_id: str,
        contact_phone: str,
        message_text: str,
        session_name: str = "default",
        voice_reply: bool = False,
        skip_send: bool = False,
        source_channel: str = "whatsapp",
        channel_id: str = None,
    ) -> dict:
        from oneai_reach.api.v1.admin import get_pause_flag

        if get_pause_flag():
            return {
                "action": "paused",
                "response": "",
                "conversation_id": 0,
                "reason": "CS engine paused by admin",
            }

        from oneai_reach.infrastructure.legacy.state_manager import get_wa_number_by_session

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

        if self.should_skip(contact_phone, wa_number_id):
            return {
                "action": "skipped",
                "response": "",
                "conversation_id": 0,
                "reason": "Contact is in cold-call funnel",
            }

        if self._check_rate_limit(session_name):
            return {
                "action": "skipped",
                "response": "",
                "conversation_id": 0,
                "reason": f"Rate limit exceeded ({self.config.cs.max_replies_per_minute}/min) for session {session_name}",
            }

        # Check response throttling to prevent rapid back-and-forth loops
        conv_key = f"{wa_number_id}:{contact_phone}"
        if _should_throttle_response(conv_key):
            return {
                "action": "throttled",
                "response": "",
                "conversation_id": 0,
                "reason": f"Response throttled: minimum {_THROTTLE_SECONDS}s delay between responses",
            }

        conv = self.conversation_service.get_or_create_conversation(
            wa_number_id, contact_phone, engine_mode="cs"
        )
        conv_id = conv["id"]

        if conv.get("message_count", 0) <= 1:
            from oneai_reach.infrastructure.legacy.n8n_client import notify_conversation_started

            notify_conversation_started(contact_phone, session_name, wa_number_id)

        self.conversation_service.add_message(
            conv_id, direction="in", message_text=message_text
        )

        current_msg_count = conv.get("message_count", 0) + 1
        if current_msg_count >= 3:
            from oneai_reach.infrastructure.legacy.n8n_client import notify_hot_lead

            notify_hot_lead(contact_phone, current_msg_count, conv_id)

        from oneai_reach.infrastructure.legacy import capi_tracker

        capi_tracker.track_lead(contact_phone)

        if self._is_purchase_signal(message_text):
            capi_tracker.track_purchase(contact_phone)
            from oneai_reach.infrastructure.legacy.n8n_client import notify_purchase_signal

            notify_purchase_signal(contact_phone, message_text, conv_id)

        if self._is_shipping_complaint(message_text):
            capi_tracker.track_atc(contact_phone)

        kb_results = _normalize_kb_results(
            self.kb_search(wa_number_id, message_text, limit=5)
        )

        product_results = []
        is_product_inquiry = self.product_search_service and self.product_search_service.detect_product_inquiry(message_text)
        if is_product_inquiry:
            product_results = self.product_search_service.search_products(
                wa_number_id, message_text, limit=5, is_product_inquiry=True
            )

        if self.should_escalate(message_text, kb_results, conv):
            reason = "No KB match + repeated unclear turns"
            self.conversation_service.escalate(conv_id, reason=reason)

            from oneai_reach.infrastructure.legacy.n8n_client import notify_escalation

            notify_escalation(contact_phone, reason, conv_id)

            lang = self._detect_language(message_text)
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

            if source_channel == "whatsapp":
                from oneai_reach.infrastructure.legacy.senders import send_typing_indicator, send_whatsapp_session

                send_typing_indicator(session_name, contact_phone, typing=True)
                time.sleep(self.config.cs.reply_delay_seconds)
                send_whatsapp_session(contact_phone, esc_msg, session_name)
                send_typing_indicator(session_name, contact_phone, typing=False)
            elif source_channel == "instagram":
                from oneai_reach.infrastructure.messaging.channels.instagram_sender import InstagramSender
                InstagramSender(wa_number_id).send(contact_phone, esc_msg)
            elif source_channel == "twitter":
                from oneai_reach.infrastructure.messaging.channels.twitter_sender import TwitterSender
                TwitterSender(wa_number_id).send(contact_phone, esc_msg)
            elif source_channel in ("telegram", "email"):
                from oneai_reach.infrastructure.messaging.channel_service import ChannelService
                from oneai_reach.config.settings import get_settings
                svc = ChannelService(get_settings().database.db_file)
                ch_id = channel_id
                if ch_id:
                    svc.send_message(ch_id, contact_phone, esc_msg)

            self.conversation_service.add_message(
                conv_id, direction="out", message_text=esc_msg
            )

            return {
                "action": "escalated",
                "response": esc_msg,
                "conversation_id": conv_id,
                "reason": reason,
            }

        # Resolve persona: V2 channel assignment > old wa_numbers > config default
        if channel_id:
            from oneai_reach.infrastructure.messaging.persona_service import PersonaService
            from oneai_reach.config.settings import get_settings as _get_settings
            _settings = _get_settings()
            _persona_svc = PersonaService(_settings.database.db_file)
            persona = _persona_svc.resolve_persona(channel_id, "cs")
        else:
            wa_num = get_wa_number_by_session(session_name)
            persona = wa_num.get("persona") if wa_num else None
            if not persona:
                persona = self.config.cs.default_persona

        self.conversation_service.advance_stage(conv_id, message_text, kb_results)
        stage_context = self.conversation_service.get_stage_context(conv_id)

        user_type = self._detect_user_type(message_text, conv_id)

        conversation_context = self.conversation_service.get_conversation_context(
            conv_id, max_messages=10
        )

        response_text = self.generate_cs_response(
            conversation_context,
            kb_results,
            persona,
            message_text,
            stage_context,
            user_type,
            product_results,
        )

        if not response_text:
            response_text = "Oke Kak, ditunggu ya! Saya bantu sekarang."

        if not skip_send:
            if source_channel == "whatsapp":
                from oneai_reach.infrastructure.legacy.senders import send_typing_indicator, send_whatsapp_session

                send_typing_indicator(session_name, contact_phone, typing=True)
                time.sleep(self.config.cs.reply_delay_seconds)

                if voice_reply:
                    try:
                        from oneai_reach.infrastructure.legacy.voice_pipeline import generate_voice_reply

                        voice_sent = generate_voice_reply(
                            response_text, session_name, contact_phone
                        )
                        if not voice_sent:
                            send_whatsapp_session(
                                contact_phone, response_text, session_name
                            )
                    except Exception as e:
                        logger.error(f"Voice reply failed: {e}, falling back to text")
                        send_whatsapp_session(contact_phone, response_text, session_name)
                else:
                    send_whatsapp_session(contact_phone, response_text, session_name)

                if is_product_inquiry and product_results:
                    self._send_product_image(
                        session_name, contact_phone, product_results
                    )

                send_typing_indicator(session_name, contact_phone, typing=False)

            elif source_channel == "instagram":
                from oneai_reach.infrastructure.messaging.channels.instagram_sender import InstagramSender
                sender = InstagramSender(wa_number_id)
                sender.send(contact_phone, response_text)

            elif source_channel == "twitter":
                from oneai_reach.infrastructure.messaging.channels.twitter_sender import TwitterSender
                sender = TwitterSender(wa_number_id)
                sender.send(contact_phone, response_text)

            elif source_channel in ("telegram", "email"):
                from oneai_reach.infrastructure.messaging.channel_service import ChannelService
                from oneai_reach.config.settings import get_settings
                svc = ChannelService(get_settings().database.db_file)
                ch_id = channel_id
                if ch_id:
                    svc.send_message(ch_id, contact_phone, response_text)

        self.conversation_service.add_message(
            conv_id, direction="out", message_text=response_text
        )

        self._record_reply(session_name)

        return {
            "action": "replied",
            "response": response_text,
            "conversation_id": conv_id,
            "reason": "",
        }

    def _send_product_image(
        self, session_name: str, contact_phone: str, product_results: list
    ) -> None:
        from oneai_reach.config.settings import get_settings
        from oneai_reach.infrastructure.database.sqlite_product_repository import SQLiteProductRepository
        from oneai_reach.infrastructure.external.waha_client import WAHAClient

        settings = get_settings()
        repo = SQLiteProductRepository(db_path=settings.database.db_file)
        waha = WAHAClient(settings)

        chat_id = f"{''.join(filter(str.isdigit, str(contact_phone)))}@c.us"

        for product in product_results[:1]:
            if not product.id:
                continue
            try:
                conn = repo._connect()
                row = conn.execute(
                    "SELECT image_url FROM product_images WHERE product_id = ? AND is_primary = 1 LIMIT 1",
                    (product.id,),
                ).fetchone()
                conn.close()
                if row and row[0]:
                    waha.send_image(
                        session_name=session_name,
                        chat_id=chat_id,
                        image_url=row[0],
                        caption=product.name,
                    )
                    logger.info(f"Sent product image for {product.name} to {contact_phone}")
            except Exception as e:
                logger.error(f"Failed to send product image: {e}")
