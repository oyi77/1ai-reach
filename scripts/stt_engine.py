"""
STT Engine — Speech-to-Text using faster-whisper.

DEPRECATED: Thin wrapper for backward compatibility.
Use oneai_reach.application.voice.STTService instead.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from oneai_reach.application.voice import STTService, get_stt_service
from oneai_reach.config.settings import get_settings

_instance = None


class STTEngine:
    """Speech-to-Text engine using faster-whisper (backward compatibility wrapper)."""

    def __init__(
        self, model_size: str = None, device: str = None, language: str = None
    ):
        """Initialize STT engine (lazy-loads model on first use)."""
        self._service = get_stt_service(get_settings())

    def _load_model(self):
        """Lazy-load faster-whisper model."""
        self._service._load_model()

    def transcribe(self, audio_bytes: bytes, audio_format: str = "wav") -> dict:
        """Transcribe audio to text."""
        return self._service.transcribe(audio_bytes, audio_format)

    def transcribe_file(self, file_path: str) -> dict:
        """Transcribe audio file."""
        return self._service.transcribe_file(file_path)


def get_stt_engine() -> STTEngine:
    """Get or create singleton STT engine."""
    global _instance
    if _instance is None:
        _instance = STTEngine()
    return _instance
