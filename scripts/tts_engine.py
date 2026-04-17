"""
TTS Engine — Text-to-Speech using ChatterBox Multilingual.

DEPRECATED: Thin wrapper for backward compatibility.
Use oneai_reach.application.voice.TTSService instead.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from oneai_reach.application.voice import TTSService, get_tts_service
from oneai_reach.config.settings import get_settings

_instance = None


class TTSEngine:
    """Text-to-Speech engine using ChatterBox Multilingual (backward compatibility wrapper)."""

    def __init__(self, device: str = None, language_id: str = None):
        """Initialize TTS engine (lazy-loads model on first use)."""
        self._service = get_tts_service(get_settings())
        self.sr = 24000

    def _load_model(self):
        """Lazy-load ChatterBox model with CPU fallback."""
        self._service._load_model()
        self.sr = self._service.sr

    def synthesize(
        self,
        text: str,
        audio_prompt_path: str = None,
        exaggeration: float = None,
        cfg_weight: float = None,
    ) -> tuple[int, bytes]:
        """Generate audio from text."""
        return self._service.synthesize(
            text, audio_prompt_path, exaggeration, cfg_weight
        )

    def synthesize_long_form(
        self,
        text: str,
        audio_prompt_path: str = None,
        exaggeration: float = None,
        cfg_weight: float = None,
    ) -> tuple[int, bytes]:
        """Synthesize long text by splitting into sentences."""
        return self._service.synthesize_long_form(
            text, audio_prompt_path, exaggeration, cfg_weight
        )


def get_tts_engine() -> TTSEngine:
    """Get or create singleton TTS engine."""
    global _instance
    if _instance is None:
        _instance = TTSEngine()
    return _instance
