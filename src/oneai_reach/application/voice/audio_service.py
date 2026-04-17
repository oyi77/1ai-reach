"""Audio format conversion and processing utilities.

Uses ffmpeg subprocess for lightweight audio conversion without heavy ML dependencies.
"""

import base64
import io
import os
import subprocess
import tempfile
from typing import List, Tuple

from oneai_reach.config.settings import Settings
from oneai_reach.domain.exceptions import ExternalAPIError
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class AudioService:
    """Audio format conversion and processing service.

    Handles WAV/OGG conversion, audio validation, and media downloads.
    Uses ffmpeg for all audio operations.
    """

    def __init__(self, config: Settings):
        """Initialize audio service.

        Args:
            config: Application settings
        """
        self.config = config
        self.ffmpeg_cmd = os.getenv("FFMPEG_CMD", "ffmpeg")
        self.ffprobe_cmd = os.getenv("FFPROBE_CMD", "ffprobe")

    def download_media(self, url: str, timeout: int = 30) -> bytes:
        """Download audio from WAHA media URL with API key auth.

        Args:
            url: WAHA media URL
            timeout: Request timeout in seconds

        Returns:
            Audio bytes

        Raises:
            ExternalAPIError: If download fails
        """
        if not url:
            raise ExternalAPIError(
                service="waha",
                endpoint="/download",
                status_code=0,
                reason="Empty media URL",
            )

        if not url.startswith("http"):
            raise ExternalAPIError(
                service="waha",
                endpoint="/download",
                status_code=0,
                reason=f"Invalid media URL: {url}",
            )

        if "waha.aitradepulse.com" in url:
            base_url = self.config.waha.url
            api_key = self.config.waha.api_key
        else:
            base_url = self.config.waha.direct_url
            api_key = self.config.waha.direct_api_key

        filename = url.split("/")[-1]
        if not filename:
            raise ExternalAPIError(
                service="waha",
                endpoint="/download",
                status_code=0,
                reason=f"Cannot extract filename from URL: {url}",
            )

        cmd = [
            "curl",
            "-s",
            "--fail",
            "-H",
            f"X-Api-Key: {api_key}",
            f"{base_url}/api/files/{filename}",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if result.returncode != 0:
                raise ExternalAPIError(
                    service="waha",
                    endpoint="/download",
                    status_code=result.returncode,
                    reason=result.stderr.decode(),
                )

            if len(result.stdout) < 100:
                raise ExternalAPIError(
                    service="waha",
                    endpoint="/download",
                    status_code=0,
                    reason=f"Downloaded file too small: {len(result.stdout)} bytes",
                )

            logger.info(f"Downloaded media: {len(result.stdout)} bytes")
            return result.stdout

        except subprocess.TimeoutExpired:
            raise ExternalAPIError(
                service="waha",
                endpoint="/download",
                status_code=0,
                reason=f"Download timeout after {timeout}s",
            )

    def convert_to_wav(
        self, input_bytes: bytes, input_format: str = "ogg"
    ) -> Tuple[int, bytes]:
        """Convert any audio format to WAV (for STT input).

        Args:
            input_bytes: Input audio bytes
            input_format: Input format (ogg, mp3, etc.)

        Returns:
            Tuple of (sample_rate, wav_bytes)

        Raises:
            ExternalAPIError: If conversion fails
        """
        cmd = [
            self.ffmpeg_cmd,
            "-i",
            "pipe:0",
            "-f",
            "wav",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-",
            "-y",
        ]

        try:
            result = subprocess.run(
                cmd, input=input_bytes, capture_output=True, timeout=30
            )
            if result.returncode != 0:
                raise ExternalAPIError(
                    service="ffmpeg",
                    endpoint="/convert_wav",
                    status_code=result.returncode,
                    reason=result.stderr.decode(),
                )

            probe_cmd = [
                self.ffprobe_cmd,
                "-i",
                "pipe:0",
                "-show_entries",
                "stream=sample_rate",
                "-of",
                "csv=p=0",
                "-",
            ]
            probe = subprocess.run(
                probe_cmd, input=input_bytes, capture_output=True, timeout=10
            )
            try:
                sample_rate = int(probe.stdout.decode().strip())
            except:
                sample_rate = 16000

            logger.debug(
                f"Converted to WAV: {len(result.stdout)} bytes, {sample_rate}Hz"
            )
            return sample_rate, result.stdout

        except subprocess.TimeoutExpired:
            raise ExternalAPIError(
                service="ffmpeg",
                endpoint="/convert_wav",
                status_code=0,
                reason="Conversion timeout",
            )

    def convert_to_ogg(
        self, wav_bytes: bytes, sample_rate: int = 24000, bitrate: str = "32k"
    ) -> bytes:
        """Convert WAV to OGG/OPUS (for WhatsApp).

        Args:
            wav_bytes: WAV audio bytes
            sample_rate: Target sample rate
            bitrate: Target bitrate

        Returns:
            OGG audio bytes

        Raises:
            ExternalAPIError: If conversion fails
        """
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_out:
            tmp_path = tmp_out.name

        try:
            cmd = [
                self.ffmpeg_cmd,
                "-i",
                "pipe:0",
                "-c:a",
                "libopus",
                "-b:a",
                bitrate,
                "-ar",
                str(sample_rate),
                "-y",
                tmp_path,
            ]
            result = subprocess.run(
                cmd, input=wav_bytes, capture_output=True, timeout=30
            )
            if result.returncode != 0:
                raise ExternalAPIError(
                    service="ffmpeg",
                    endpoint="/convert_ogg",
                    status_code=result.returncode,
                    reason=result.stderr.decode(),
                )

            with open(tmp_path, "rb") as f:
                ogg_bytes = f.read()

            logger.debug(f"Converted to OGG: {len(ogg_bytes)} bytes")
            return ogg_bytes

        except subprocess.TimeoutExpired:
            raise ExternalAPIError(
                service="ffmpeg",
                endpoint="/convert_ogg",
                status_code=0,
                reason="Conversion timeout",
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def wav_to_base64(self, wav_bytes: bytes) -> str:
        """Base64 encode WAV audio for WAHA API.

        Args:
            wav_bytes: WAV audio bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(wav_bytes).decode()

    def ogg_to_base64(self, ogg_bytes: bytes) -> str:
        """Base64 encode OGG audio for WAHA API.

        Args:
            ogg_bytes: OGG audio bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(ogg_bytes).decode()

    def get_audio_duration(self, audio_bytes: bytes, format: str = "ogg") -> float:
        """Get audio duration in seconds using ffprobe.

        Args:
            audio_bytes: Audio bytes
            format: Audio format

        Returns:
            Duration in seconds (0.0 if probe fails)
        """
        cmd = [
            self.ffprobe_cmd,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            "pipe:0",
        ]
        result = subprocess.run(cmd, input=audio_bytes, capture_output=True, timeout=10)
        if result.returncode == 0:
            try:
                duration = float(result.stdout.decode().strip())
                logger.debug(f"Audio duration: {duration:.1f}s")
                return duration
            except:
                pass
        return 0.0

    def concatenate_wav_chunks(
        self, chunks: List[Tuple[int, bytes]], silence_ms: int = 250
    ) -> Tuple[int, bytes]:
        """Concatenate WAV audio chunks with silence gaps.

        Args:
            chunks: List of (sample_rate, wav_bytes) tuples
            silence_ms: Silence duration between chunks in milliseconds

        Returns:
            Tuple of (sample_rate, concatenated_wav_bytes)
        """
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

        concatenated = result.getvalue()
        logger.debug(f"Concatenated {len(chunks)} chunks: {len(concatenated)} bytes")
        return sample_rate, concatenated

    def is_audio_valid(
        self, audio_bytes: bytes, max_duration: float = 60.0
    ) -> Tuple[bool, str]:
        """Validate audio for processing.

        Args:
            audio_bytes: Audio bytes to validate
            max_duration: Maximum allowed duration in seconds

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(audio_bytes) < 100:
            return False, "Audio too small"

        duration = self.get_audio_duration(audio_bytes)
        if duration > max_duration:
            return False, f"Audio too long: {duration:.1f}s > {max_duration}s"

        return True, ""
