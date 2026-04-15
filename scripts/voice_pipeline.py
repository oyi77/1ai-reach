"""
Voice Pipeline — Orchestration between STT, LLM, and TTS.

Handles: download → STT → cs_engine → TTS → send
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from voice_config import get_voice_config, VOICE_TIMEOUT_SECONDS, VOICE_MAX_AUDIO_DURATION
from audio_utils import download_media, convert_to_wav, convert_to_ogg, ogg_to_base64, get_audio_duration, is_audio_valid
from stt_engine import get_stt_engine
from tts_engine import get_tts_engine


def process_inbound_voice(media_url: str, wa_number_id: str, contact_phone: str, session_name: str, msg_type: str = "ptt") -> dict:
    """Process inbound voice note end-to-end.
    
    Args:
        media_url: WAHA media URL
        wa_number_id: WA number ID
        contact_phone: Customer phone
        session_name: WAHA session name
        msg_type: Message type (ptt or audio)
    
    Returns:
        dict with action, transcription, response, voice_sent
    """
    config = get_voice_config(session_name)
    
    if not config.get("enabled"):
        return {"action": "skipped", "reason": "voice_disabled"}
    
    try:
        # 1. Download audio
        print(f"[voice] Downloading media from {media_url[:50]}...")
        audio_bytes = download_media(media_url)
        
        # 2. Validate audio
        valid, error = is_audio_valid(audio_bytes, config["max_duration"])
        if not valid:
            print(f"[voice] Audio invalid: {error}")
            return {"action": "error", "reason": error}
        
        # 3. STT: Transcribe
        print(f"[voice] Transcribing audio...")
        stt = get_stt_engine()
        stt_result = stt.transcribe(audio_bytes, "ogg")
        
        if not stt_result.get("text"):
            print(f"[voice] STT failed: {stt_result.get('error', 'empty')}")
            return {
                "action": "text_fallback",
                "reason": "stt_failed",
                "transcription": "",
            }
        
        transcription = stt_result["text"]
        print(f"[voice] Transcribed: {transcription[:100]}")
        
        # 4. LLM: Generate response (via cs_engine)
        print(f"[voice] Generating response via cs_engine...")
        from cs_engine import handle_inbound_message
        cs_result = handle_inbound_message(
            wa_number_id=wa_number_id,
            contact_phone=contact_phone,
            message_text=transcription,
            session_name=session_name,
        )
        
        response_text = cs_result.get("response", "")
        if not response_text:
            print(f"[voice] CS engine returned empty response")
            return {
                "action": "text_fallback",
                "reason": "cs_empty",
                "transcription": transcription,
                "response": "",
            }
        
        print(f"[voice] Response: {response_text[:100]}")
        
        # 5. Determine reply mode
        reply_mode = config.get("reply_mode", "auto")
        if reply_mode == "never":
            return {
                "action": "text_replied",
                "transcription": transcription,
                "response": response_text,
                "voice_sent": False,
            }
        
        # 6. TTS: Synthesize response
        print(f"[voice] Synthesizing response to audio...")
        tts = get_tts_engine()
        sr, wav_bytes = tts.synthesize_long_form(response_text)
        
        if not wav_bytes:
            print(f"[voice] TTS failed, falling back to text")
            return {
                "action": "text_fallback",
                "reason": "tts_failed",
                "transcription": transcription,
                "response": response_text,
            }
        
        # 7. Convert to OGG
        print(f"[voice] Converting to OGG...")
        ogg_bytes = convert_to_ogg(wav_bytes, sr)
        
        # 8. Send voice note
        print(f"[voice] Sending voice note...")
        from senders import send_voice_note
        sent = send_voice_note(contact_phone, ogg_bytes, session_name)
        
        return {
            "action": "voice_replied",
            "transcription": transcription,
            "response": response_text,
            "voice_sent": sent,
        }
    
    except Exception as e:
        print(f"[voice] Pipeline error: {e}")
        return {
            "action": "error",
            "reason": str(e),
        }


def generate_voice_reply(text: str, session_name: str, contact_phone: str) -> bool:
    """Generate and send voice reply for given text.
    
    Args:
        text: Response text
        session_name: WAHA session
        contact_phone: Customer phone
    
    Returns:
        True if voice sent, False if fallback to text
    """
    try:
        config = get_voice_config(session_name)
        if not config.get("enabled"):
            return False
        
        tts = get_tts_engine()
        sr, wav_bytes = tts.synthesize_long_form(text)
        
        if not wav_bytes:
            return False
        
        ogg_bytes = convert_to_ogg(wav_bytes, sr)
        from senders import send_voice_note
        return send_voice_note(contact_phone, ogg_bytes, session_name)
    
    except Exception as e:
        print(f"[voice] generate_voice_reply error: {e}")
        return False
