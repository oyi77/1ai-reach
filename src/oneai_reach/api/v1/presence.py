"""Presence tracking endpoints — online/offline/composing status per contact."""

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from oneai_reach.api.dependencies import verify_api_key
from oneai_reach.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/presence",
    tags=["presence"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/{session}")
async def api_get_presence(session: str):
    """Get presence status for all contacts in a session."""
    settings = get_settings()
    db_path = settings.database.db_file

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT contact_phone, status, last_seen_at, updated_at FROM presence_status WHERE wa_number_id = ?",
            (session,),
        ).fetchall()
        return {"status": "success", "data": {"presences": [dict(r) for r in rows]}}
    finally:
        conn.close()


@router.post("/{session}/subscribe")
async def api_subscribe_presence(session: str, request: Request):
    """Subscribe to presence updates for a session via WAHA."""
    import httpx

    settings = get_settings()
    waha_url = settings.waha.url.rstrip("/")
    waha_key = settings.waha.api_key

    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{waha_url}/api/{session}/presence",
                headers={"X-Api-Key": waha_key, "Content-Type": "application/json"},
                content=body if body else b"{}",
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail={"error": "Session not found", "session": session})
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail={"error": "WAHA service unavailable"})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)