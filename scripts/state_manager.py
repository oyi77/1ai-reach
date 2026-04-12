"""SQLite state management for leads pipeline — raw sqlite3, no ORM."""

import sqlite3
from datetime import datetime

from config import DB_FILE

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    displayName TEXT,
    formattedAddress TEXT,
    internationalPhoneNumber TEXT,
    phone TEXT,
    websiteUri TEXT,
    primaryType TEXT,
    type TEXT,
    source TEXT,
    status TEXT DEFAULT 'new',
    contacted_at TEXT,
    email TEXT,
    linkedin TEXT,
    followup_at TEXT,
    replied_at TEXT,
    research TEXT,
    review_score TEXT,
    review_issues TEXT,
    reply_text TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details TEXT,
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_event_log_lead ON event_log(lead_id);

CREATE TABLE IF NOT EXISTS control_jobs (
    job_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    pid INTEGER,
    command TEXT NOT NULL,
    status TEXT NOT NULL,
    log_path TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT,
    exit_code INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS control_locks (
    name TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    acquired_at TEXT DEFAULT (datetime('now')),
    heartbeat_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    action TEXT NOT NULL,
    payload TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_control_jobs_stage ON control_jobs(stage);
CREATE INDEX IF NOT EXISTS idx_control_jobs_status ON control_jobs(status);
CREATE INDEX IF NOT EXISTS idx_tool_audit_tool ON tool_audit(tool_name);
"""

_LEAD_COLUMNS = [
    "id",
    "displayName",
    "formattedAddress",
    "internationalPhoneNumber",
    "phone",
    "websiteUri",
    "primaryType",
    "type",
    "source",
    "status",
    "contacted_at",
    "email",
    "linkedin",
    "followup_at",
    "replied_at",
    "research",
    "review_score",
    "review_issues",
    "reply_text",
    "created_at",
    "updated_at",
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.executescript(_SCHEMA_SQL)
    finally:
        conn.close()


def upsert_lead(lead: dict) -> None:
    cols = [c for c in _LEAD_COLUMNS if c in lead]
    if "id" not in cols:
        return
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    updates = ", ".join(
        f"{c} = excluded.{c}" for c in cols if c not in ("id", "created_at")
    )
    sql = (
        f"INSERT INTO leads ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}, "
        f"updated_at = datetime('now')"
    )
    values = [lead.get(c) for c in cols]
    for i, v in enumerate(values):
        if isinstance(v, float) and str(v) == "nan":
            values[i] = None
        elif isinstance(v, str) and v.strip().lower() in ("nan", "none", ""):
            values[i] = None

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(sql, values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_leads_by_status(status) -> list[dict]:
    conn = _connect()
    try:
        if isinstance(status, (list, tuple)):
            placeholders = ", ".join(["?"] * len(status))
            rows = conn.execute(
                f"SELECT * FROM leads WHERE status IN ({placeholders})", list(status)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM leads WHERE status = ?", (status,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_lead_by_id(lead_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_lead(lead_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [lead_id]
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"UPDATE leads SET {set_clause} WHERE id = ?", values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_lead_status(lead_id: str, status: str) -> None:
    update_lead(lead_id, status=status)


def add_event_log(lead_id: str, event_type: str, details: str = "") -> None:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO event_log (lead_id, event_type, details) VALUES (?, ?, ?)",
            (lead_id, event_type, details),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_by_status() -> dict[str, int]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM leads GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}
    finally:
        conn.close()


def get_all_leads() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM leads").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_event_logs(lead_id: str | None = None, limit: int = 100) -> list[dict]:
    conn = _connect()
    try:
        if lead_id:
            rows = conn.execute(
                """
                SELECT * FROM event_log
                WHERE lead_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (lead_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM event_log ORDER BY timestamp DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_control_job(
    job_id: str,
    stage: str,
    command: str,
    *,
    pid: int | None = None,
    status: str = "created",
    log_path: str = "",
) -> None:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT OR REPLACE INTO control_jobs (
                job_id, stage, pid, command, status, log_path, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (job_id, stage, pid, command, status, log_path),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_control_job(job_id: str, **fields) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"UPDATE control_jobs SET {set_clause} WHERE job_id = ?", values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_control_job(job_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM control_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_control_jobs(limit: int = 100) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM control_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def acquire_control_lock(name: str, owner: str) -> bool:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT owner FROM control_locks WHERE name = ?", (name,)
        ).fetchone()
        if existing and existing["owner"] != owner:
            conn.rollback()
            return False
        conn.execute(
            """
            INSERT INTO control_locks (name, owner, acquired_at, heartbeat_at)
            VALUES (?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(name) DO UPDATE SET
                owner = excluded.owner,
                heartbeat_at = datetime('now')
            """,
            (name, owner),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def release_control_lock(name: str, owner: str) -> None:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM control_locks WHERE name = ? AND owner = ?", (name, owner)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_tool_audit(tool_name: str, action: str, payload: str = "") -> None:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO tool_audit (tool_name, action, payload) VALUES (?, ?, ?)",
            (tool_name, action, payload),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_tool_audit(limit: int = 100) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM tool_audit ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
