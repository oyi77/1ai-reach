"""Voice configuration API endpoints."""

from fastapi import APIRouter, HTTPException, Request

from oneai_reach.infrastructure.legacy.voice_config import get_voice_config
from oneai_reach.infrastructure.legacy.state_manager import update_voice_config

router = APIRouter(tags=["voice-config"])


@router.get("/{session_name}")
async def api_voice_config_get(session_name: str):
    config = get_voice_config(session_name)
    if config is None:
        config = {
            "voice_enabled": False,
            "voice_reply_mode": "auto",
            "voice_language": "ms",
        }
    return {"status": "success", "data": config}


@router.post("/{session_name}")
async def api_voice_config_update(session_name: str, request: Request):
    data = await request.json()
    voice_enabled = data.get("voice_enabled")
    voice_reply_mode = data.get("voice_reply_mode")
    voice_language = data.get("voice_language")

    ok = update_voice_config(
        session_name,
        voice_enabled=voice_enabled,
        voice_reply_mode=voice_reply_mode,
        voice_language=voice_language,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="update_failed")
    return {"status": "success", "data": {"ok": True}}