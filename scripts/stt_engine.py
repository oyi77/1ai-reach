"""
STT Engine — Speech-to-Text using faster-whisper.

Lazy-loads model on first use. Singleton pattern.
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from voice_config import VOICE_STT_MODEL_SIZE, VOICE_STT_DEVICE, VOICE_STT_LANGUAGE

_instance = None


class STTEngine:
    """Speech-to-Text engine using faster-whisper."""
    
    def __init__(self, model_size: str = VOICE_STT_MODEL_SIZE, device: str = VOICE_STT_DEVICE, language: str = VOICE_STT_LANGUAGE):
        """Initialize STT engine (lazy-loads model on first use)."""
        self.model_size = model_size
        self.device = device
        self.language = language
        self.model = None
    
    def _load_model(self):
        """Lazy-load faster-whisper model."""
        if self.model is not None:
            return
        
        try:
            from faster_whisper import WhisperModel
            print(f"Loading faster-whisper {self.model_size} model on {self.device}...")
            self.model = WhisperModel(self.model_size, device=self.device, compute_type="int8_float16")
            print("Model loaded")
        except Exception as e:
            print(f"ERROR loading STT model: {e}")
            raise
    
    def transcribe(self, audio_bytes: bytes, audio_format: str = "wav") -> dict:
        """Transcribe audio to text.
        
        Args:
            audio_bytes: Raw audio data
            audio_format: Audio format (wav, ogg, mp3, etc.)
        
        Returns:
            dict with keys: text, language, confidence, duration
        """
        self._load_model()
        
        try:
            # Write to temp file (faster-whisper needs file path)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=f'.{audio_format}', delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            
            try:
                # Transcribe
                segments, info = self.model.transcribe(tmp_path, language=self.language, beam_size=5)
                text = " ".join([seg.text for seg in segments])
                
                return {
                    "text": text,
                    "language": info.language,
                    "confidence": info.language_probability,
                    "duration": info.duration,
                }
            finally:
                import os
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        
        except Exception as e:
            print(f"STT error: {e}")
            return {
                "text": "",
                "language": "",
                "confidence": 0.0,
                "duration": 0.0,
                "error": str(e),
            }
    
    def transcribe_file(self, file_path: str) -> dict:
        """Transcribe audio file."""
        with open(file_path, 'rb') as f:
            return self.transcribe(f.read())


def get_stt_engine() -> STTEngine:
    """Get or create singleton STT engine."""
    global _instance
    if _instance is None:
        _instance = STTEngine()
    return _instance
