from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import sqlite3
import os
import httpx

from oneai_reach.api.dependencies import verify_api_key

router = APIRouter(
    prefix="/api/v1",
    tags=["settings"],
    dependencies=[Depends(verify_api_key)],
)


class WAHAServer(BaseModel):
    id: int = 0
    label: str
    url: str
    api_key: str
    is_default: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WAHAServerCreate(BaseModel):
    label: str
    url: str
    api_key: str
    is_default: int = 0


class WAHAServerUpdate(BaseModel):
    label: Optional[str] = None
    url: Optional[str] = None
    api_key: Optional[str] = None
    is_default: Optional[int] = None


class WAHAServersResponse(BaseModel):
    servers: List[WAHAServer]


class WAHAServerResponse(BaseModel):
    server: WAHAServer


class TestResult(BaseModel):
    success: bool
    message: str
    sessions_count: int = 0


def _get_db():
    from oneai_reach.config.settings import get_settings
    settings = get_settings()
    return settings.database.db_file


def _init_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waha_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _seed_default(conn: sqlite3.Connection):
    row = conn.execute("SELECT COUNT(*) FROM waha_servers").fetchone()
    if row[0] == 0:
        waha_url = os.environ.get("WAHA_URL", "https://waha.aitradepulse.com")
        waha_key = os.environ.get("WAHA_API_KEY", "199c96bcb87e45a39f6cde9e5677ed09")
        conn.execute(
            "INSERT INTO waha_servers (label, url, api_key, is_default) VALUES (?, ?, ?, 1)",
            ("Default", waha_url, waha_key),
        )
        conn.commit()


def _row_to_server(row) -> WAHAServer:
    return WAHAServer(
        id=row[0],
        label=row[1],
        url=row[2],
        api_key=row[3],
        is_default=row[4],
        created_at=row[5],
        updated_at=row[6],
    )


@router.get("/settings/waha-servers", response_model=WAHAServersResponse)
def list_waha_servers():
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    try:
        _init_table(conn)
        _seed_default(conn)
        rows = conn.execute("SELECT * FROM waha_servers ORDER BY is_default DESC, id ASC").fetchall()
        return WAHAServersResponse(servers=[_row_to_server(r) for r in rows])
    finally:
        conn.close()


@router.post("/settings/waha-servers", response_model=WAHAServerResponse)
def create_waha_server(server: WAHAServerCreate):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    try:
        _init_table(conn)
        if server.is_default == 1:
            conn.execute("UPDATE waha_servers SET is_default = 0")
        cursor = conn.execute(
            "INSERT INTO waha_servers (label, url, api_key, is_default) VALUES (?, ?, ?, ?)",
            (server.label, server.url, server.api_key, server.is_default),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM waha_servers WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return WAHAServerResponse(server=_row_to_server(row))
    finally:
        conn.close()


@router.put("/settings/waha-servers/{server_id}", response_model=WAHAServerResponse)
def update_waha_server(server_id: int, updates: WAHAServerUpdate):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    try:
        _init_table(conn)
        row = conn.execute("SELECT * FROM waha_servers WHERE id = ?", (server_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Server not found")
        current = _row_to_server(row)
        label = updates.label if updates.label is not None else current.label
        url = updates.url if updates.url is not None else current.url
        api_key = updates.api_key if updates.api_key is not None else current.api_key
        is_default = updates.is_default if updates.is_default is not None else current.is_default
        if is_default == 1:
            conn.execute("UPDATE waha_servers SET is_default = 0")
        conn.execute(
            "UPDATE waha_servers SET label=?, url=?, api_key=?, is_default=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (label, url, api_key, is_default, server_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM waha_servers WHERE id = ?", (server_id,)).fetchone()
        return WAHAServerResponse(server=_row_to_server(row))
    finally:
        conn.close()


@router.delete("/settings/waha-servers/{server_id}")
def delete_waha_server(server_id: int):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT is_default FROM waha_servers WHERE id = ?", (server_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Server not found")
        conn.execute("DELETE FROM waha_servers WHERE id = ?", (server_id,))
        conn.commit()
        return {"status": "success", "message": f"Server {server_id} deleted"}
    finally:
        conn.close()


@router.post("/settings/waha-servers/{server_id}/test", response_model=TestResult)
def test_waha_connection(server_id: int):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT * FROM waha_servers WHERE id = ?", (server_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Server not found")
        server = _row_to_server(row)
    finally:
        conn.close()

    try:
        resp = httpx.get(
            f"{server.url.rstrip('/')}/api/sessions",
            headers={"X-Api-Key": server.api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            sessions = resp.json()
            return TestResult(
                success=True,
                message=f"Connected — {len(sessions)} session(s) found",
                sessions_count=len(sessions),
            )
        return TestResult(
            success=False,
            message=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as e:
        return TestResult(success=False, message=str(e)[:200])