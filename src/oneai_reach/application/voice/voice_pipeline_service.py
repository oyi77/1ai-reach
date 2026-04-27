"""Voice pipeline orchestration service.

Coordinates STT, LLM, and TTS for end-to-end voice processing.
"""

import os
from typing import Dict, Optional

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class VoicePipelineService:
    """Voice processing pipeline orchestrator.

    Handles: download → STT → cs_engine → TTS → send
    """

    def __init__(self, config: Settings):
        """Initialize voice pipeline service.

        Args:
            config: Application settings
        """
        self.config = config
        self.timeout = int(os.getenv("VOICE_TIMEOUT_SECONDS", "30"))
        self.max_duration = int(os.getenv("VOICE_MAX_AUDIO_DURATION", "60"))

    def get_voice_config(self, session_name: str) -> Dict[str, any]:
        """Get voice configuration for a specific WAHA session.

        Args:
            session_name: WAHA session name

        Returns:
            Voice configuration dictionary
        """
        try:
            from oneai_reach.infrastructure.legacy.state_manager import get_voice_config as get_db_voice_config

            db_config = get_db_voice_config(session_name)

            return {
                "voice_enabled": db_config.get("voice_enabled", False),
                "voice_reply_mode": db_config.get("voice_reply_mode", "auto"),
                "voice_language": db_config.get("voice_language", "ms"),
                "reply_mode": db_config.get("voice_reply_mode", "auto"),
                "max_duration": self.max_duration,
                "timeout": self.timeout,
            }
        except Exception as e:
            logger.warning(f"Failed to load voice config from DB: {e}")
            return {
                "voice_enabled": os.getenv("VOICE_ENABLED", "true").lower() == "true",
                "voice_reply_mode": os.getenv("VOICE_REPLY_MODE", "auto"),
                "voice_language": os.getenv("VOICE_TTS_LANGUAGE_ID", "ms"),
                "reply_mode": os.getenv("VOICE_REPLY_MODE", "auto"),
                "max_duration": self.max_duration,
                "timeout": self.timeout,
            }

    def process_inbound_voice(
        self,
        media_url: str,
        wa_number_id: str,
        contact_phone: str,
        session_name: str,
        msg_type: str = "ptt",
    ) -> Dict[str, any]:
        """Process inbound voice note end-to-end.

        Args:
            media_url: WAHA media URL
            wa_number_id: WA number ID
            contact_phone: Customer phone
            session_name: WAHA session name
            msg_type: Message type (ptt or audio)

        Returns:
            Dictionary with action, transcription, response, voice_sent
        """
        config = self.get_voice_config(session_name)

        if not config.get("voice_enabled"):
            return {"action": "skipped", "reason": "voice_disabled"}

        try:
            from oneai_reach.application.voice.audio_service import AudioService
            from oneai_reach.application.voice.stt_service import get_stt_service
            from oneai_reach.application.voice.tts_service import get_tts_service

            audio_service = AudioService(self.config)
            stt_service = get_stt_service(self.config)
            tts_service = get_tts_service(self.config)

            logger.info(f"Processing voice from {contact_phone}")
            audio_bytes = audio_service.download_media(media_url)

            valid, error = audio_service.is_audio_valid(
                audio_bytes, config["max_duration"]
            )
            if not valid:
                logger.warning(f"Audio invalid: {error}")
                return {"action": "error", "reason": error}

            logger.info("Transcribing audio...")
            stt_result = stt_service.transcribe(audio_bytes, "ogg")

            if not stt_result.get("text"):
                logger.warning(f"STT failed: {stt_result.get('error', 'empty')}")
                return {
                    "action": "text_fallback",
                    "reason": "stt_failed",
                    "transcription": "",
                }

            transcription = stt_result["text"]
            logger.info(f"Transcribed: {transcription[:100]}")

            logger.info("Generating response via cs_engine...")
            from oneai_reach.infrastructure.legacy.cs_engine import handle_inbound_message
            from oneai_reach.infrastructure.legacy.senders import send_typing_indicator

            send_typing_indicator(session_name, contact_phone, typing=True)

            cs_result = handle_inbound_message(
                wa_number_id=wa_number_id,
                contact_phone=contact_phone,
                message_text=transcription,
                session_name=session_name,
                skip_send=True,
            )

            response_text = cs_result.get("response", "")
            if not response_text:
                send_typing_indicator(session_name, contact_phone, typing=False)
                logger.warning("CS engine returned empty response")
                return {
                    "action": "text_fallback",
                    "reason": "cs_empty",
                    "transcription": transcription,
                    "response": "",
                }

            logger.info(f"Response: {response_text[:100]}")

            reply_mode = config.get("reply_mode", "auto")
            if reply_mode == "never":
                return {
                    "action": "text_replied",
                    "transcription": transcription,
                    "response": response_text,
                    "voice_sent": False,
                }

            logger.info("Synthesizing response to audio...")
            sr, wav_bytes = tts_service.synthesize_long_form(response_text)

            if not wav_bytes:
                logger.warning("TTS failed, falling back to text")
                return {
                    "action": "text_fallback",
                    "reason": "tts_failed",
                    "transcription": transcription,
                    "response": response_text,
                }

            logger.info("Converting to OGG...")
            ogg_bytes = audio_service.convert_to_ogg(wav_bytes, sr)

            logger.info("Sending voice note...")
            from oneai_reach.infrastructure.legacy.senders import send_voice_note

            sent = send_voice_note(contact_phone, ogg_bytes, session_name)

            send_typing_indicator(session_name, contact_phone, typing=False)

            return {
                "action": "voice_replied",
                "transcription": transcription,
                "response": response_text,
                "voice_sent": sent,
            }

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            try:
                from oneai_reach.infrastructure.legacy.senders import send_typing_indicator

                send_typing_indicator(session_name, contact_phone, typing=False)
            except Exception as e:
                logger.error(f"Failed to send typing indicator: {e}")
            return {
                "action": "error",
                "reason": str(e),
            }

    def generate_voice_reply(
        self, text: str, session_name: str, contact_phone: str
    ) -> bool:
        """Generate and send voice reply for given text.

        Args:
            text: Response text
            session_name: WAHA session
            contact_phone: Customer phone

        Returns:
            True if voice sent, False if fallback to text
        """
        try:
            config = self.get_voice_config(session_name)
            if not config.get("voice_enabled"):
                return False

            from oneai_reach.application.voice.audio_service import AudioService
            from oneai_reach.application.voice.tts_service import get_tts_service

            audio_service = AudioService(self.config)
            tts_service = get_tts_service(self.config)

            sr, wav_bytes = tts_service.synthesize_long_form(text)

            if not wav_bytes:
                return False

            ogg_bytes = audio_service.convert_to_ogg(wav_bytes, sr)

            from oneai_reach.infrastructure.legacy.senders import send_voice_note

            return send_voice_note(contact_phone, ogg_bytes, session_name)

        except Exception as e:
            logger.error(f"generate_voice_reply error: {e}")
            return False
