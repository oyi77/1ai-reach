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
