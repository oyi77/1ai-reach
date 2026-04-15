"""
Audio Utilities — Audio format conversion for voice note processing.

Uses ffmpeg subprocess for audio conversion (lightweight, no heavy ML libs).
"""

import base64
import io
import os
import subprocess
import tempfile

# Get ffmpeg path (system-installed)
FFMPEG_CMD = os.getenv("FFMPEG_CMD", "ffmpeg")
FFPROBE_CMD = os.getenv("FFPROBE_CMD", "ffprobe")

# Import config for WAHA credentials
from config import WAHA_URL, WAHA_API_KEY, WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY


def download_media(url: str, timeout: int = 30) -> bytes:
    """Download audio from WAHA media URL with API key auth."""
    if "waha.aitradepulse.com" in url:
        base_url, api_key = WAHA_URL, WAHA_API_KEY
    else:
        base_url, api_key = WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY
    
    filename = url.split("/")[-1]
    cmd = ["curl", "-s", "--fail", "-H", f"X-Api-Key: {api_key}", f"{base_url}/api/files/{filename}"]
    result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        raise Exception(f"Download failed: {result.stderr.decode()}")
    return result.stdout


def convert_to_wav(input_bytes: bytes, input_format: str = "ogg") -> tuple[int, bytes]:
    """Convert any audio format to WAV (for STT input)."""
    cmd = [FFMPEG_CMD, "-i", "pipe:0", "-f", "wav", "-ar", "16000", "-ac", "1", "-", "-y"]
    result = subprocess.run(cmd, input=input_bytes, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise Exception(f"WAV conversion failed: {result.stderr.decode()}")
    
    probe_cmd = [FFPROBE_CMD, "-i", "pipe:0", "-show_entries", "stream=sample_rate", "-of", "csv=p=0", "-"]
    probe = subprocess.run(probe_cmd, input=input_bytes, capture_output=True, timeout=10)
    try:
        sample_rate = int(probe.stdout.decode().strip())
    except:
        sample_rate = 16000
    return sample_rate, result.stdout


def convert_to_ogg(wav_bytes: bytes, sample_rate: int = 24000, bitrate: str = "32k") -> bytes:
    """Convert WAV to OGG/OPUS (for WhatsApp)."""
    with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_out:
        tmp_path = tmp_out.name
    
    try:
        cmd = [FFMPEG_CMD, "-i", "pipe:0", "-c:a", "libopus", "-b:a", bitrate, "-ar", str(sample_rate), "-y", tmp_path]
        result = subprocess.run(cmd, input=wav_bytes, capture_output=True, timeout=30)
        if result.returncode != 0:
            raise Exception(f"OGG conversion failed: {result.stderr.decode()}")
        
        with open(tmp_path, 'rb') as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def wav_to_base64(wav_bytes: bytes) -> str:
    """Base64 encode WAV audio for WAHA API."""
    return base64.b64encode(wav_bytes).decode()


def ogg_to_base64(ogg_bytes: bytes) -> str:
    """Base64 encode OGG audio for WAHA API."""
    return base64.b64encode(ogg_bytes).decode()


def get_audio_duration(audio_bytes: bytes, format: str = "ogg") -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [FFPROBE_CMD, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", "pipe:0"]
    result = subprocess.run(cmd, input=audio_bytes, capture_output=True, timeout=10)
    if result.returncode == 0:
        try:
            return float(result.stdout.decode().strip())
        except:
            pass
    return 0.0


def concatenate_wav_chunks(chunks: list[tuple[int, bytes]], silence_ms: int = 250) -> tuple[int, bytes]:
    """Concatenate WAV audio chunks with silence gaps."""
    if not chunks:
        return 0, b""
    if len(chunks) == 1:
        return chunks[0]
    
    sample_rate = chunks[0][0]
    silence_samples = int(sample_rate * silence_ms / 1000)
    silence = b"\x00" * (silence_samples * 2)
    
    result = io.BytesIO()
    for i, (sr, chunk) in enumerate(chunks):
        result.write(chunk)
        if i < len(chunks) - 1:
            result.write(silence)
    return sample_rate, result.getvalue()


def is_audio_valid(audio_bytes: bytes, max_duration: float = 60.0) -> tuple[bool, str]:
    """Validate audio for processing."""
    if len(audio_bytes) < 100:
        return False, "Audio too small"
    duration = get_audio_duration(audio_bytes)
    if duration > max_duration:
        return False, f"Audio too long: {duration:.1f}s > {max_duration}s"
    return True, ""
