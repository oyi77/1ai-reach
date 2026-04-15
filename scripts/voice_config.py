"""
Voice Configuration — Voice note support constants.

All paths are absolute via config.py imports. No ML libraries imported at module level.
"""

import os
from pathlib import Path

# Import base paths from config
_SCRIPTS_DIR = Path(__file__).parent
_ROOT = _SCRIPTS_DIR.parent

# Import WAHA configuration from config
from config import (
    WAHA_URL,
    WAHA_API_KEY,
    WAHA_DIRECT_URL,
    WAHA_DIRECT_API_KEY,
)

# ---------------------------------------------------------------------------
# Voice Feature Toggle
# ---------------------------------------------------------------------------
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() == "true"

# ---------------------------------------------------------------------------
# STT (Speech-to-Text) Configuration
# ---------------------------------------------------------------------------
VOICE_STT_MODEL_SIZE = os.getenv("VOICE_STT_MODEL_SIZE", "medium")  # tiny, base, small, medium, large-v3
VOICE_STT_DEVICE = os.getenv("VOICE_STT_DEVICE", "cuda")  # cuda or cpu (fallback to cpu if gpu unavailable)
VOICE_STT_LANGUAGE = os.getenv("VOICE_STT_LANGUAGE", "id")  # Indonesian

# ---------------------------------------------------------------------------
# TTS (Text-to-Speech) Configuration
# ---------------------------------------------------------------------------
VOICE_TTS_ENGINE = os.getenv("VOICE_TTS_ENGINE", "chatterbox")  # chatterbox or edge-tts (fallback)
VOICE_TTS_LANGUAGE_ID = os.getenv("VOICE_TTS_LANGUAGE_ID", "ms")  # Malay (closest to Indonesian)
VOICE_TTS_EXAGGERATION = float(os.getenv("VOICE_TTS_EXAGGERATION", "0.5"))  # Emotion control 0.0-1.0
VOICE_TTS_CFG_WEIGHT = float(os.getenv("VOICE_TTS_CFG_WEIGHT", "0.5"))  # Pacing control 0.0-1.0
VOICE_TTS_DEVICE = os.getenv("VOICE_TTS_DEVICE", "cuda")  # cuda or cpu (fallback for OOM)

# ---------------------------------------------------------------------------
# Voice Reply Mode
# ---------------------------------------------------------------------------
# "auto" = reply voice to voice, text to text
# "always" = always reply with voice
# "never" = always reply with text
VOICE_REPLY_MODE = os.getenv("VOICE_REPLY_MODE", "auto")

# ---------------------------------------------------------------------------
# Audio Processing Limits
# ---------------------------------------------------------------------------
VOICE_MAX_AUDIO_DURATION = int(os.getenv("VOICE_MAX_AUDIO_DURATION", "60"))  # Max 60 seconds
VOICE_MAX_RESPONSE_LENGTH = int(os.getenv("VOICE_MAX_RESPONSE_LENGTH", "500"))  # Max chars for TTS
VOICE_TIMEOUT_SECONDS = int(os.getenv("VOICE_TIMEOUT_SECONDS", "30"))  # Max processing time before fallback

# ---------------------------------------------------------------------------
# WAHA Voice API Configuration
# ---------------------------------------------------------------------------
WAHA_SEND_VOICE_ENDPOINT = "/api/sendVoice"
WAHA_MEDIA_DOWNLOAD_BASE = "/api/files"

# Audio format for WhatsApp
VOICE_FORMAT = os.getenv("VOICE_FORMAT", "ogg")  # WhatsApp native format
VOICE_CODEC = os.getenv("VOICE_CODEC", "libopus")
VOICE_BITRATE = os.getenv("VOICE_BITRATE", "32k")
VOICE_SAMPLE_RATE = int(os.getenv("VOICE_SAMPLE_RATE", "24000"))  # ChatterBox output sample rate

# ---------------------------------------------------------------------------
# Per-Session Voice Configuration Lookup
# ---------------------------------------------------------------------------
def get_voice_config(session_name: str) -> dict:
    """Get voice configuration for a specific WAHA session."""
    return {
        "enabled": VOICE_ENABLED,
        "stt_model_size": VOICE_STT_MODEL_SIZE,
        "stt_device": VOICE_STT_DEVICE,
        "stt_language": VOICE_STT_LANGUAGE,
        "tts_engine": VOICE_TTS_ENGINE,
        "tts_language_id": VOICE_TTS_LANGUAGE_ID,
        "tts_exaggeration": VOICE_TTS_EXAGGERATION,
        "tts_cfg_weight": VOICE_TTS_CFG_WEIGHT,
        "tts_device": VOICE_TTS_DEVICE,
        "reply_mode": VOICE_REPLY_MODE,
        "max_duration": VOICE_MAX_AUDIO_DURATION,
        "max_response_length": VOICE_MAX_RESPONSE_LENGTH,
        "timeout": VOICE_TIMEOUT_SECONDS,
    }

def validate_config() -> list[str]:
    """Validate voice configuration."""
    warnings = []
    if VOICE_STT_MODEL_SIZE not in ("tiny", "base", "small", "medium", "large-v3"):
        warnings.append(f"Invalid VOICE_STT_MODEL_SIZE: {VOICE_STT_MODEL_SIZE}")
    if VOICE_REPLY_MODE not in ("auto", "always", "never"):
        warnings.append(f"Invalid VOICE_REPLY_MODE: {VOICE_REPLY_MODE}")
    return warnings
