"""
Voice Pipeline — Orchestration between STT, LLM, and TTS.

DEPRECATED: Thin wrapper for backward compatibility.
Use oneai_reach.application.voice.VoicePipelineService instead.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from oneai_reach.application.voice import VoicePipelineService
from oneai_reach.config.settings import get_settings

_service = VoicePipelineService(get_settings())


def process_inbound_voice(
    media_url: str,
    wa_number_id: str,
    contact_phone: str,
    session_name: str,
    msg_type: str = "ptt",
) -> dict:
    """Process inbound voice note end-to-end."""
    return _service.process_inbound_voice(
        media_url, wa_number_id, contact_phone, session_name, msg_type
    )


def generate_voice_reply(text: str, session_name: str, contact_phone: str) -> bool:
    """Generate and send voice reply for given text."""
    return _service.generate_voice_reply(text, session_name, contact_phone)
