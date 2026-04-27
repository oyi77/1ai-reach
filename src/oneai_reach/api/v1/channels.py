"""Channels V2 API — workspace and channel management endpoints.

CRUD for workspaces and channels, connection testing, messaging, and polling.
Maintains backward compatibility with old /{wa_number_id} routes.
"""

import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from oneai_reach.api.dependencies import verify_api_key
from oneai_reach.config.settings import get_settings
from oneai_reach.infrastructure.messaging.channel_service import (
    SUPPORTED_PLATFORMS,
    VALID_MODES,
    ChannelService,
)
from oneai_reach.infrastructure.messaging.channels.channel_config import ChannelConfig

router = APIRouter(
    prefix="/api/v1/channels",
    tags=["channels"],
    dependencies=[Depends(verify_api_key)],
)

SUPPORTED_CHANNELS = {
    "instagram": "Instagram (covers Threads DMs)",
    "twitter": "Twitter / X",
}


def _get_service() -> ChannelService:
    settings = get_settings()
    return ChannelService(settings.database.db_file)


class ChannelStatusResponse(BaseModel):
    channels: Dict[str, Dict[str, Any]]


class ChannelCookiesRequest(BaseModel):
    cookies: Dict[str, str] = Field(..., description="Platform-specific cookies")


class ChannelEnableRequest(BaseModel):
    enabled: bool


class ChannelTestResponse(BaseModel):
    success: bool
    username: str = ""
    error: str = ""


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class CreateChannelRequest(BaseModel):
    workspace_id: str
    platform: str
    label: str = Field(..., min_length=1, max_length=100)
    mode: str = Field(default="cs")
    config: Optional[Dict[str, Any]] = None
    username: str = Field(default="")
    phone: str = Field(default="")


class UpdateChannelRequest(BaseModel):
    label: Optional[str] = None
    mode: Optional[str] = None
    enabled: Optional[bool] = None
    connected: Optional[bool] = None
    username: Optional[str] = None
    phone: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    session_data: Optional[Dict[str, Any]] = None


class SendMessageRequest(BaseModel):
    recipient: str
    message: str
    subject: Optional[str] = None


# ── Workspace Endpoints ─────────────────────────────────────────────

@router.get("/workspaces")
async def list_workspaces():
    svc = _get_service()
    return {"workspaces": svc.list_workspaces()}


@router.post("/workspaces")
async def create_workspace(body: CreateWorkspaceRequest):
    svc = _get_service()
    ws = svc.create_workspace(body.name, body.description)
    return {"status": "success", "data": ws}


@router.get("/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str):
    svc = _get_service()
    ws = svc.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(404, f"Workspace not found: {workspace_id}")
    channels = svc.list_channels(workspace_id=workspace_id)
    return {"status": "success", "data": {**ws, "channels": channels}}


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    svc = _get_service()
    deleted = svc.delete_workspace(workspace_id)
    if not deleted:
        raise HTTPException(404, f"Workspace not found: {workspace_id}")
    return {"status": "success", "deleted": True}


# ── Channel Endpoints ───────────────────────────────────────────────

@router.get("/channels")
async def list_channels(
    workspace_id: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
):
    svc = _get_service()
    channels = svc.list_channels(workspace_id=workspace_id, mode=mode, platform=platform)
    return {"channels": channels}


@router.post("/channels")
async def create_channel(body: CreateChannelRequest):
    if body.platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(400, f"Unsupported platform: {body.platform}. Supported: {SUPPORTED_PLATFORMS}")
    if body.mode not in VALID_MODES:
        raise HTTPException(400, f"Invalid mode: {body.mode}. Valid: {VALID_MODES}")

    svc = _get_service()
    try:
        ch = svc.create_channel(
            workspace_id=body.workspace_id,
            platform=body.platform,
            label=body.label,
            mode=body.mode,
            config=body.config,
            username=body.username,
            phone=body.phone,
        )
        return {"status": "success", "data": ch}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/channels/{channel_id}")
async def get_channel(channel_id: str):
    svc = _get_service()
    ch = svc.get_channel(channel_id)
    if not ch:
        raise HTTPException(404, f"Channel not found: {channel_id}")
    return {"status": "success", "data": ch}


@router.patch("/channels/{channel_id}")
async def update_channel(channel_id: str, body: UpdateChannelRequest):
    if body.mode is not None and body.mode not in VALID_MODES:
        raise HTTPException(400, f"Invalid mode: {body.mode}. Valid: {VALID_MODES}")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    svc = _get_service()
    ch = svc.update_channel(channel_id, **updates)
    if not ch:
        raise HTTPException(404, f"Channel not found: {channel_id}")

    if body.enabled is not None and ch.get("platform") == "whatsapp":
        settings = get_settings()
        conn = sqlite3.connect(settings.database.db_file)
        try:
            phone = ch.get("phone") or ""
            label = ch.get("label") or ""
            wa_row = conn.execute(
                "SELECT id FROM wa_numbers WHERE phone = ? OR session_name = ? OR label = ? LIMIT 1",
                (phone, phone, label),
            ).fetchone()
            if wa_row:
                conn.execute(
                    "UPDATE wa_numbers SET auto_reply = ? WHERE id = ?",
                    (1 if body.enabled else 0, wa_row[0]),
                )
                conn.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to sync auto_reply for channel {channel_id}: {e}")
        finally:
            conn.close()

    return {"status": "success", "data": ch}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str):
    svc = _get_service()
    deleted = svc.delete_channel(channel_id)
    if not deleted:
        raise HTTPException(404, f"Channel not found: {channel_id}")
    return {"status": "success", "deleted": True}


# ── Channel Operations ──────────────────────────────────────────────

@router.post("/channels/{channel_id}/test")
async def test_connection(channel_id: str):
    svc = _get_service()
    result = svc.test_connection(channel_id)
    return {"status": "success", "data": result}


@router.post("/channels/{channel_id}/send")
async def send_message(channel_id: str, body: SendMessageRequest):
    svc = _get_service()
    ok = svc.send_message(channel_id, body.recipient, body.message, body.subject)
    if ok:
        return {"status": "success", "sent": True, "channel_id": channel_id, "recipient": body.recipient}
    raise HTTPException(500, f"Failed to send message via channel {channel_id}")


@router.get("/channels/{channel_id}/threads")
async def get_threads(channel_id: str, limit: int = Query(20, ge=1, le=100)):
    svc = _get_service()
    threads = svc.get_threads(channel_id, limit)
    return {"threads": threads}


@router.get("/poll-cs")
async def poll_cs_channels():
    svc = _get_service()
    messages = svc.poll_all_cs()
    return {"new_count": len(messages), "messages": messages[:50]}


@router.get("/poll-coldcall")
async def poll_coldcall_channels():
    svc = _get_service()
    messages = svc.poll_all_coldcall()
    return {"new_count": len(messages), "messages": messages[:50]}


# ── Legacy Routes (backward compat) ────────────────────────────────

@router.get("/{wa_number_id}", response_model=ChannelStatusResponse)
async def get_channel_status(wa_number_id: str) -> ChannelStatusResponse:
    channels = {}
    for ch_name, ch_label in SUPPORTED_CHANNELS.items():
        cfg = ChannelConfig(ch_name, wa_number_id)
        channels[ch_name] = {**cfg.get_status(), "label": ch_label}
    return ChannelStatusResponse(channels=channels)


@router.post("/{wa_number_id}/{channel}/cookies")
async def set_channel_cookies(
    wa_number_id: str,
    channel: str,
    body: ChannelCookiesRequest,
):
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(400, f"Unsupported channel: {channel}")
    cfg = ChannelConfig(channel, wa_number_id)
    cfg.set_cookies(body.cookies)
    return {"status": "saved", "channel": channel}


@router.patch("/{wa_number_id}/{channel}/enable")
async def toggle_channel(
    wa_number_id: str,
    channel: str,
    body: ChannelEnableRequest,
):
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(400, f"Unsupported channel: {channel}")
    cfg = ChannelConfig(channel, wa_number_id)
    cfg.set_enabled(body.enabled)
    return {"status": "updated", "channel": channel, "enabled": body.enabled}


@router.post("/{wa_number_id}/{channel}/test", response_model=ChannelTestResponse)
async def test_channel_connection(
    wa_number_id: str,
    channel: str,
):
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(400, f"Unsupported channel: {channel}")

    cfg = ChannelConfig(channel, wa_number_id)
    cookies = cfg.get_cookies()

    if channel == "instagram":
        from oneai_reach.infrastructure.messaging.channels.instagram_sender import InstagramSender
        sessionid = cookies.get("sessionid", "")
        if not sessionid:
            return ChannelTestResponse(success=False, error="No sessionid cookie provided")
        sender = InstagramSender(wa_number_id)
        result = sender.test_connection(sessionid)
        return ChannelTestResponse(**result)

    elif channel == "twitter":
        from oneai_reach.infrastructure.messaging.channels.twitter_sender import TwitterSender
        auth_token = cookies.get("auth_token", "")
        if not auth_token:
            return ChannelTestResponse(success=False, error="No auth_token cookie provided")
        sender = TwitterSender(wa_number_id)
        result = sender.test_connection(
            auth_token=auth_token,
            ct0=cookies.get("ct0", ""),
            twid=cookies.get("twid", ""),
        )
        return ChannelTestResponse(**result)

    return ChannelTestResponse(success=False, error="Unknown channel")


@router.post("/{wa_number_id}/{channel}/send")
async def send_channel_dm(
    wa_number_id: str,
    channel: str,
    body: Dict[str, str],
):
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(400, f"Unsupported channel: {channel}")

    username = body.get("username", "")
    message = body.get("message", "")
    if not username or not message:
        raise HTTPException(400, "username and message required")

    if channel == "instagram":
        from oneai_reach.infrastructure.messaging.channels.instagram_sender import InstagramSender
        sender = InstagramSender(wa_number_id)
        ok = sender.send(username, message)
    elif channel == "twitter":
        from oneai_reach.infrastructure.messaging.channels.twitter_sender import TwitterSender
        sender = TwitterSender(wa_number_id)
        ok = sender.send(username, message)
    else:
        ok = False

    if ok:
        return {"status": "sent", "channel": channel, "username": username}
    raise HTTPException(500, f"Failed to send {channel} DM to {username}")


@router.get("/{wa_number_id}/{channel}/threads")
async def get_channel_threads(
    wa_number_id: str,
    channel: str,
    limit: int = 20,
):
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(400, f"Unsupported channel: {channel}")

    if channel == "instagram":
        from oneai_reach.infrastructure.messaging.channels.instagram_sender import InstagramSender
        sender = InstagramSender(wa_number_id)
        return {"threads": sender.get_threads(limit)}
    elif channel == "twitter":
        from oneai_reach.infrastructure.messaging.channels.twitter_sender import TwitterSender
        sender = TwitterSender(wa_number_id)
        return {"threads": sender.get_dm_threads(limit)}

    return {"threads": []}


@router.get("/{wa_number_id}/poll")
async def poll_dms(wa_number_id: str):
    from oneai_reach.infrastructure.messaging.channels.dm_poller import poll_instagram, poll_twitter
    ig_new = poll_instagram(wa_number_id)
    tw_new = poll_twitter(wa_number_id)
    return {
        "wa_number_id": wa_number_id,
        "instagram": {"new_count": len(ig_new), "messages": ig_new[:10]},
        "twitter": {"new_count": len(tw_new), "messages": tw_new[:10]},
    }


@router.post("/poll-all")
async def poll_all_dms():
    from oneai_reach.infrastructure.legacy.state_manager import get_wa_numbers
    numbers = get_wa_numbers()
    wa_ids = [n.get("id", "") or n.get("session_name", "") for n in numbers]
    from oneai_reach.infrastructure.messaging.channels.dm_poller import poll_all
    new_messages = poll_all(wa_ids)
    return {
        "polled_count": len(wa_ids),
        "new_count": len(new_messages),
        "messages": new_messages[:20],
    }
