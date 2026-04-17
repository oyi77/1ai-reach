"""Speech-to-Text service using faster-whisper.

Provides lazy-loaded STT engine with singleton pattern for efficient model reuse.
"""

import os
import tempfile
from typing import Dict, Optional

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError, MissingConfigurationError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class STTService:
    """Speech-to-Text service using faster-whisper.

    Lazy-loads the Whisper model on first use to avoid startup overhead.
    Supports multiple model sizes (tiny, base, small, medium, large-v3).
    """

    def __init__(self, config: Settings):
        """Initialize STT service.

        Args:
            config: Application settings containing voice configuration
        """
        self.config = config
        self.model_size = os.getenv("VOICE_STT_MODEL_SIZE", "medium")
        self.device = os.getenv("VOICE_STT_DEVICE", "cuda")
        self.language = os.getenv("VOICE_STT_LANGUAGE", "id")
        self.model = None

    def _load_model(self) -> None:
        """Lazy-load faster-whisper model.

        Raises:
            ExternalAPIError: If model loading fails
        """
        if self.model is not None:
            return

        try:
            from faster_whisper import WhisperModel

            logger.info(
                f"Loading faster-whisper {self.model_size} model on {self.device}"
            )
            self.model = WhisperModel(
                self.model_size, device=self.device, compute_type="int8_float16"
            )
            logger.info("STT model loaded successfully")
        except ImportError as e:
            raise MissingConfigurationError(
                config_key="faster_whisper",
                reason="faster-whisper package not installed",
            )
        except Exception as e:
            logger.error(f"Failed to load STT model: {e}")
            raise ExternalAPIError(
                service="faster_whisper",
                endpoint="/load_model",
                status_code=0,
                reason=f"Model loading failed: {str(e)}",
            )

    def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        language: Optional[str] = None,
    ) -> Dict[str, any]:
        """Transcribe audio to text.

        Args:
            audio_bytes: Raw audio data
            audio_format: Audio format (wav, ogg, mp3, etc.)
            language: Language code (defaults to configured language)

        Returns:
            Dictionary with keys:
                - text: Transcribed text
                - language: Detected/specified language
                - confidence: Language probability (0.0-1.0)
                - duration: Audio duration in seconds
                - error: Error message (if transcription failed)

        Raises:
            ExternalAPIError: If transcription fails critically
        """
        self._load_model()

        lang = language or self.language
        tmp_path = None

        try:
            # Write to temp file (faster-whisper requires file path)
            with tempfile.NamedTemporaryFile(
                suffix=f".{audio_format}", delete=False
            ) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            logger.debug(
                f"Transcribing audio ({len(audio_bytes)} bytes, format={audio_format})"
            )

            # Transcribe with beam search
            segments, info = self.model.transcribe(tmp_path, language=lang, beam_size=5)

            # Collect all segments
            text = " ".join([seg.text for seg in segments])

            result = {
                "text": text,
                "language": info.language,
                "confidence": info.language_probability,
                "duration": info.duration,
            }

            logger.info(
                f"Transcription successful: {len(text)} chars, {info.duration:.1f}s"
            )
            return result

        except Exception as e:
            logger.error(f"STT transcription error: {e}")
            return {
                "text": "",
                "language": "",
                "confidence": 0.0,
                "duration": 0.0,
                "error": str(e),
            }

        finally:
            # Clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {tmp_path}: {e}")

    def transcribe_file(
        self, file_path: str, language: Optional[str] = None
    ) -> Dict[str, any]:
        """Transcribe audio file.

        Args:
            file_path: Path to audio file
            language: Language code (optional)

        Returns:
            Transcription result dictionary

        Raises:
            FileNotFoundError: If file does not exist
            ExternalAPIError: If transcription fails
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        with open(file_path, "rb") as f:
            audio_bytes = f.read()

        # Infer format from extension
        audio_format = os.path.splitext(file_path)[1].lstrip(".")

        return self.transcribe(audio_bytes, audio_format, language)


# Singleton instance for backward compatibility
_instance: Optional[STTService] = None


def get_stt_service(config: Optional[Settings] = None) -> STTService:
    """Get or create singleton STT service instance.

    Args:
        config: Application settings (uses get_settings() if not provided)

    Returns:
        STTService instance
    """
    global _instance
    if _instance is None:
        if config is None:
            from oneai_reach.config.settings import get_settings

            config = get_settings()
        _instance = STTService(config)
    return _instance
