"""
Audio Utilities — Audio format conversion for voice note processing.

DEPRECATED: Thin wrapper for backward compatibility.
Use oneai_reach.application.voice.AudioService instead.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from oneai_reach.application.voice import AudioService
from oneai_reach.config.settings import get_settings

_service = AudioService(get_settings())


def download_media(url: str, timeout: int = 30) -> bytes:
    """Download audio from WAHA media URL with API key auth."""
    return _service.download_media(url, timeout)


def convert_to_wav(input_bytes: bytes, input_format: str = "ogg") -> tuple[int, bytes]:
    """Convert any audio format to WAV (for STT input)."""
    return _service.convert_to_wav(input_bytes, input_format)


def convert_to_ogg(
    wav_bytes: bytes, sample_rate: int = 24000, bitrate: str = "32k"
) -> bytes:
    """Convert WAV to OGG/OPUS (for WhatsApp)."""
    return _service.convert_to_ogg(wav_bytes, sample_rate, bitrate)


def wav_to_base64(wav_bytes: bytes) -> str:
    """Base64 encode WAV audio for WAHA API."""
    return _service.wav_to_base64(wav_bytes)


def ogg_to_base64(ogg_bytes: bytes) -> str:
    """Base64 encode OGG audio for WAHA API."""
    return _service.ogg_to_base64(ogg_bytes)


def get_audio_duration(audio_bytes: bytes, format: str = "ogg") -> float:
    """Get audio duration in seconds using ffprobe."""
    return _service.get_audio_duration(audio_bytes, format)


def concatenate_wav_chunks(
    chunks: list[tuple[int, bytes]], silence_ms: int = 250
) -> tuple[int, bytes]:
    """Concatenate WAV audio chunks with silence gaps."""
    return _service.concatenate_wav_chunks(chunks, silence_ms)


def is_audio_valid(audio_bytes: bytes, max_duration: float = 60.0) -> tuple[bool, str]:
    """Validate audio for processing."""
    return _service.is_audio_valid(audio_bytes, max_duration)
