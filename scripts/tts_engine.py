"""
TTS Engine — Text-to-Speech using ChatterBox Multilingual.

Lazy-loads model on first use. Singleton pattern with CPU fallback.
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from voice_config import (
    VOICE_TTS_LANGUAGE_ID,
    VOICE_TTS_EXAGGERATION,
    VOICE_TTS_CFG_WEIGHT,
    VOICE_TTS_DEVICE,
)

_instance = None


class TTSEngine:
    """Text-to-Speech engine using ChatterBox Multilingual."""
    
    def __init__(self, device: str = VOICE_TTS_DEVICE, language_id: str = VOICE_TTS_LANGUAGE_ID):
        """Initialize TTS engine (lazy-loads model on first use)."""
        self.device = device
        self.language_id = language_id
        self.model = None
        self.sr = 24000  # Default sample rate
    
    def _load_model(self):
        """Lazy-load ChatterBox model with CPU fallback."""
        if self.model is not None:
            return
        
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            print(f"Loading ChatterBox Multilingual on {self.device}...")
            self.model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
            self.sr = self.model.sr
            print(f"Model loaded (sr={self.sr})")
        except Exception as e:
            print(f"ERROR loading TTS on {self.device}: {e}")
            if self.device != "cpu":
                print("Falling back to CPU...")
                try:
                    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
                    self.model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
                    self.sr = self.model.sr
                    self.device = "cpu"
                    print("CPU fallback successful")
                except Exception as e2:
                    print(f"CPU fallback failed: {e2}")
                    raise
            else:
                raise
    
    def synthesize(self, text: str, audio_prompt_path: str = None, exaggeration: float = VOICE_TTS_EXAGGERATION, cfg_weight: float = VOICE_TTS_CFG_WEIGHT) -> tuple[int, bytes]:
        """Generate audio from text.
        
        Args:
            text: Text to synthesize
            audio_prompt_path: Path to reference audio for voice cloning (optional)
            exaggeration: Emotion control 0.0-1.0
            cfg_weight: Pacing control 0.0-1.0
        
        Returns:
            Tuple of (sample_rate, wav_bytes)
        """
        self._load_model()
        
        try:
            import torch
            wav = self.model.generate(
                text,
                language_id=self.language_id,
                audio_prompt_path=audio_prompt_path,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
            )
            
            # Convert torch tensor to numpy bytes
            wav_np = wav.squeeze().cpu().numpy()
            import struct
            wav_bytes = struct.pack('<' + 'h' * len(wav_np), *[int(x * 32767) for x in wav_np])
            
            return self.sr, wav_bytes
        
        except Exception as e:
            print(f"TTS error: {e}")
            return self.sr, b""
    
    def synthesize_long_form(self, text: str, audio_prompt_path: str = None, exaggeration: float = VOICE_TTS_EXAGGERATION, cfg_weight: float = VOICE_TTS_CFG_WEIGHT) -> tuple[int, bytes]:
        """Synthesize long text by splitting into sentences.
        
        Args:
            text: Long text to synthesize
            audio_prompt_path: Path to reference audio for voice cloning
            exaggeration: Emotion control
            cfg_weight: Pacing control
        
        Returns:
            Tuple of (sample_rate, concatenated_wav_bytes)
        """
        import nltk
        try:
            sentences = nltk.sent_tokenize(text)
        except:
            # Fallback: simple split on periods
            sentences = [s.strip() for s in text.split('.') if s.strip()]
        
        if not sentences:
            return self.sr, b""
        
        # Synthesize each sentence
        from audio_utils import concatenate_wav_chunks
        chunks = []
        for sent in sentences:
            sr, wav = self.synthesize(sent, audio_prompt_path, exaggeration, cfg_weight)
            if wav:
                chunks.append((sr, wav))
        
        if not chunks:
            return self.sr, b""
        
        # Concatenate with silence
        return concatenate_wav_chunks(chunks, silence_ms=250)


def get_tts_engine() -> TTSEngine:
    """Get or create singleton TTS engine."""
    global _instance
    if _instance is None:
        _instance = TTSEngine()
    return _instance
