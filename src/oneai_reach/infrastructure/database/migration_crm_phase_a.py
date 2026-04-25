"""CRM Phase A migration — adds conversation_tags, quick_reply_templates,
contact_jid_map, presence_status, and media_messages tables.
Idempotent — safe to run multiple times."""

import sqlite3

from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TEMPLATES = [
    {
        "name": "Greeting",
        "content": "Halo, terima kasih sudah menghubungi kami! Ada yang bisa kami bantu?",
        "category": "greeting",
    },
    {
        "name": "Business Hours",
        "content": "Jam operasional kami: Senin-Sabtu 08:00-17:00 WIB. Di luar jam kerja, kami akan membalas pesan Anda secepatnya.",
        "category": "hours",
    },
    {
        "name": "Pricing Info",
        "content": "Untuk informasi harga produk kami, silakan kunjungi katalog di website atau tanya langsung ya!",
        "category": "pricing",
    },
    {
        "name": "Thank You",
        "content": "Terima kasih sudah berbelanja! Jika ada pertanyaan, jangan ragu untuk menghubungi kami lagi.",
        "category": "thanks",
    },
    {
        "name": "Follow Up",
        "content": "Halo! Kami ingin menindaklanjuti percakapan kita sebelumnya. Apakah ada yang bisa kami bantu?",
        "category": "follow-up",
    },
]


def run_crm_migration(db_path: str) -> None:
    """Run CRM Phase A migration. Creates tables and seeds default templates.

    Args:
        db_path: Path to SQLite database file (e.g. 'data/leads.db')
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        _create_tables(conn)
        _seed_templates(conn)
        conn.commit()
        logger.info("CRM Phase A migration complete")
    except Exception as e:
        conn.rollback()
        logger.error(f"CRM Phase A migration failed: {e}")
        raise
    finally:
        conn.close()


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create all CRM Phase A tables if they don't exist."""
    # conversation_tags — tags on conversations (flexible, unlimited)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            UNIQUE(conversation_id, tag)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conv_tags_conv ON conversation_tags(conversation_id)"
    )

    # quick_reply_templates — reusable message templates
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quick_reply_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_number_id TEXT,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id) ON DELETE SET NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_templates_wa ON quick_reply_templates(wa_number_id)"
    )

    # contact_jid_map — maps @lid contacts to @c.us phone numbers
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_jid_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_number_id TEXT NOT NULL,
            lid TEXT NOT NULL,
            c_us_phone TEXT NOT NULL,
            push_name TEXT,
            confidence TEXT DEFAULT 'auto',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id) ON DELETE CASCADE,
            UNIQUE(wa_number_id, lid)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jid_map_lid ON contact_jid_map(lid)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jid_map_phone ON contact_jid_map(c_us_phone)"
    )

    # presence_status — online/offline/composing status per contact per session
    conn.execute("""
        CREATE TABLE IF NOT EXISTS presence_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_number_id TEXT NOT NULL,
            contact_phone TEXT NOT NULL,
            status TEXT DEFAULT 'offline',
            last_seen_at TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id) ON DELETE CASCADE,
            UNIQUE(wa_number_id, contact_phone)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_presence_wa ON presence_status(wa_number_id)"
    )

    # media_messages — tracks media files sent/received in conversations
    conn.execute("""
        CREATE TABLE IF NOT EXISTS media_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            message_id INTEGER,
            media_type TEXT NOT NULL,
            file_url TEXT,
            file_name TEXT,
            file_size INTEGER,
            caption TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (message_id) REFERENCES conversation_messages(id) ON DELETE SET NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_conv ON media_messages(conversation_id)"
    )

    conn.commit()
    logger.info("CRM Phase A tables created/verified")


def _seed_templates(conn: sqlite3.Connection) -> None:
    """Seed default quick reply templates if table is empty."""
    cur = conn.execute("SELECT COUNT(*) as cnt FROM quick_reply_templates")
    if cur.fetchone()["cnt"] > 0:
        return  # Already seeded

    for t in DEFAULT_TEMPLATES:
        conn.execute(
            "INSERT INTO quick_reply_templates (name, content, category) VALUES (?, ?, ?)",
            (t["name"], t["content"], t["category"]),
        )
    conn.commit()
    logger.info(f"Seeded {len(DEFAULT_TEMPLATES)} default quick reply templates")