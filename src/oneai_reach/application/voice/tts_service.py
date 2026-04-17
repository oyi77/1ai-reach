"""Text-to-Speech service using ChatterBox Multilingual.

Provides lazy-loaded TTS engine with CPU fallback for OOM scenarios.
"""

import os
import struct
from typing import Optional, Tuple

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError, MissingConfigurationError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class TTSService:
    """Text-to-Speech service using ChatterBox Multilingual.

    Lazy-loads the ChatterBox model on first use with automatic CPU fallback.
    Supports voice cloning via audio prompts and emotion/pacing controls.
    """

    def __init__(self, config: Settings):
        """Initialize TTS service.

        Args:
            config: Application settings containing voice configuration
        """
        self.config = config
        self.device = os.getenv("VOICE_TTS_DEVICE", "cuda")
        self.language_id = os.getenv("VOICE_TTS_LANGUAGE_ID", "ms")
        self.model = None
        self.sr = 24000

    def _load_model(self) -> None:
        """Lazy-load ChatterBox model with CPU fallback.

        Raises:
            ExternalAPIError: If model loading fails on all devices
        """
        if self.model is not None:
            return

        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            logger.info(f"Loading ChatterBox Multilingual on {self.device}")
            self.model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
            self.sr = self.model.sr
            logger.info(f"TTS model loaded successfully (sr={self.sr})")
        except ImportError:
            raise MissingConfigurationError(
                config_key="chatterbox", reason="chatterbox package not installed"
            )
        except Exception as e:
            logger.error(f"Failed to load TTS on {self.device}: {e}")

            if self.device != "cpu":
                logger.info("Attempting CPU fallback...")
                try:
                    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

                    self.model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
                    self.sr = self.model.sr
                    self.device = "cpu"
                    logger.info("CPU fallback successful")
                except Exception as e2:
                    logger.error(f"CPU fallback failed: {e2}")
                    raise ExternalAPIError(
                        service="chatterbox",
                        endpoint="/load_model",
                        status_code=0,
                        reason=f"Model loading failed on all devices: {str(e2)}",
                    )
            else:
                raise ExternalAPIError(
                    service="chatterbox",
                    endpoint="/load_model",
                    status_code=0,
                    reason=f"Model loading failed: {str(e)}",
                )

    def synthesize(
        self,
        text: str,
        audio_prompt_path: Optional[str] = None,
        exaggeration: Optional[float] = None,
        cfg_weight: Optional[float] = None,
        language_id: Optional[str] = None,
    ) -> Tuple[int, bytes]:
        """Generate audio from text.

        Args:
            text: Text to synthesize
            audio_prompt_path: Path to reference audio for voice cloning (optional)
            exaggeration: Emotion control 0.0-1.0 (default from env)
            cfg_weight: Pacing control 0.0-1.0 (default from env)
            language_id: Language ID (default from config)

        Returns:
            Tuple of (sample_rate, wav_bytes)

        Raises:
            ExternalAPIError: If synthesis fails critically
        """
        self._load_model()

        exag = (
            exaggeration
            if exaggeration is not None
            else float(os.getenv("VOICE_TTS_EXAGGERATION", "0.5"))
        )
        cfg = (
            cfg_weight
            if cfg_weight is not None
            else float(os.getenv("VOICE_TTS_CFG_WEIGHT", "0.5"))
        )
        lang = language_id or self.language_id

        try:
            import torch

            logger.debug(f"Synthesizing text: {text[:50]}... (lang={lang})")

            wav = self.model.generate(
                text,
                language_id=lang,
                audio_prompt_path=audio_prompt_path,
                exaggeration=exag,
                cfg_weight=cfg,
            )

            wav_np = wav.squeeze().cpu().numpy()
            wav_bytes = struct.pack(
                "<" + "h" * len(wav_np), *[int(x * 32767) for x in wav_np]
            )

            logger.info(f"Synthesis successful: {len(wav_bytes)} bytes")
            return self.sr, wav_bytes

        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            return self.sr, b""

    def synthesize_long_form(
        self,
        text: str,
        audio_prompt_path: Optional[str] = None,
        exaggeration: Optional[float] = None,
        cfg_weight: Optional[float] = None,
        language_id: Optional[str] = None,
    ) -> Tuple[int, bytes]:
        """Synthesize long text by splitting into sentences.

        Args:
            text: Long text to synthesize
            audio_prompt_path: Path to reference audio for voice cloning
            exaggeration: Emotion control
            cfg_weight: Pacing control
            language_id: Language ID

        Returns:
            Tuple of (sample_rate, concatenated_wav_bytes)
        """
        try:
            import nltk

            sentences = nltk.sent_tokenize(text)
        except:
            sentences = [s.strip() for s in text.split(".") if s.strip()]

        if not sentences:
            return self.sr, b""

        from oneai_reach.application.voice.audio_service import AudioService

        audio_service = AudioService(self.config)

        chunks = []
        for sent in sentences:
            sr, wav = self.synthesize(
                sent, audio_prompt_path, exaggeration, cfg_weight, language_id
            )
            if wav:
                chunks.append((sr, wav))

        if not chunks:
            return self.sr, b""

        return audio_service.concatenate_wav_chunks(chunks, silence_ms=250)


_instance: Optional[TTSService] = None


def get_tts_service(config: Optional[Settings] = None) -> TTSService:
    """Get or create singleton TTS service instance.

    Args:
        config: Application settings (uses get_settings() if not provided)

    Returns:
        TTSService instance
    """
    global _instance
    if _instance is None:
        if config is None:
            from oneai_reach.config.settings import get_settings

            config = get_settings()
        _instance = TTSService(config)
    return _instance
