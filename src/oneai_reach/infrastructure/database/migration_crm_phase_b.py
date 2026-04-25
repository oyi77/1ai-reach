"""CRM Phase B migration — adds contact_profiles, proposals, email_events, and waha_labels tables.

This migration builds on Phase A to enable full CRM functionality:
- Contact profiles with extended details
- Proposals management (create, track status)
- Email tracking per conversation
- WAHA labels sync

Idempotent — safe to run multiple times."""

import sqlite3
from typing import Optional

from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

# Default WAHA label colors (standard WhatsApp colors)
DEFAULT_WAHA_LABELS = [
    {"name": "New Lead", "color": "#00C853"},      # Green
    {"name": "Hot", "color": "#FF1744"},          # Red
    {"name": "Warm", "color": "#FF9100"},         # Orange
    {"name": "Cold", "color": "#2979FF"},          # Blue
    {"name": "Follow Up", "color": "#D500F9"},    # Purple
    {"name": "Closed Won", "color": "#00BFA5"},   # Teal
    {"name": "Closed Lost", "color": "#78909C"},  # Gray
    {"name": "VIP", "color": "#FFD600"},          # Yellow
]


def run_crm_migration(db_path: str) -> None:
    """Run CRM Phase B migration.

    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        _create_tables(conn)
        _seed_waha_labels(conn)
        conn.commit()
        logger.info("CRM Phase B migration complete")
    except Exception as e:
        conn.rollback()
        logger.error(f"CRM Phase B migration failed: {e}")
        raise
    finally:
        conn.close()


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create all CRM Phase B tables if they don't exist."""

    # contact_profiles — extended contact information per WA number
    # Links to existing contacts table but adds CRM-specific fields
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            wa_number_id TEXT NOT NULL,
            profile_photo_url TEXT,
            status TEXT,  -- Custom status message (e.g., "Available", "Busy")
            is_business INTEGER DEFAULT 0,
            business_name TEXT,
            business_description TEXT,
            address TEXT,
            website TEXT,
            birthday TEXT,
            custom_fields TEXT,  -- JSON for flexible custom data
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id) ON DELETE CASCADE,
            UNIQUE(contact_id, wa_number_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_contact_profiles_contact ON contact_profiles(contact_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_contact_profiles_wa ON contact_profiles(wa_number_id)"
    )

    # proposals — proposals linked to contacts and conversations
    conn.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            conversation_id INTEGER,
            wa_number_id TEXT,
            lead_id TEXT,  -- Optional link to legacy leads table
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'draft',  -- draft, sent, accepted, rejected, expired
            score REAL,
            reviewed INTEGER DEFAULT 0,
            reviewed_at TEXT,
            review_notes TEXT,
            sent_at TEXT,
            accepted_at TEXT,
            rejected_at TEXT,
            expires_at TEXT,
            sent_count INTEGER DEFAULT 0,
            opened_count INTEGER DEFAULT 0,
            clicked_count INTEGER DEFAULT 0,
            value_cents INTEGER,  -- Proposal value in cents for tracking
            currency TEXT DEFAULT 'IDR',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
            FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id) ON DELETE SET NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposals_contact ON proposals(contact_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposals_conv ON proposals(conversation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposals_wa ON proposals(wa_number_id)"
    )

    # email_events — detailed email tracking per conversation/contact
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER,
            conversation_id INTEGER,
            lead_id TEXT,
            wa_number_id TEXT,
            event_type TEXT NOT NULL,  -- sent, delivered, opened, clicked, bounced, spam, unsubscribed
            email TEXT NOT NULL,
            subject TEXT,
            message_id TEXT,
            provider TEXT DEFAULT 'brevo',  -- brevo, sendgrid, etc.
            provider_event_id TEXT,
            ip_address TEXT,
            user_agent TEXT,
            link_clicked TEXT,  -- URL if event is clicked
            bounce_reason TEXT,
            timestamp TEXT DEFAULT (datetime('now')),
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL,
            FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id) ON DELETE SET NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_events_contact ON email_events(contact_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_events_conv ON email_events(conversation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_events_type ON email_events(event_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_events_email ON email_events(email)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_events_timestamp ON email_events(timestamp)"
    )

    # waha_labels — sync WAHA labels from WhatsApp API
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waha_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_number_id TEXT NOT NULL,
            waha_label_id TEXT NOT NULL,  -- WAHA's internal label ID
            name TEXT NOT NULL,
            color TEXT,
            is_predefined INTEGER DEFAULT 0,  -- WAHA built-in label
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id) ON DELETE CASCADE,
            UNIQUE(wa_number_id, waha_label_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_waha_labels_wa ON waha_labels(wa_number_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_waha_labels_id ON waha_labels(waha_label_id)"
    )

    # waha_label_assignments — which labels are assigned to which conversations
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waha_label_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            waha_label_id INTEGER NOT NULL,
            assigned_at TEXT DEFAULT (datetime('now')),
            assigned_by TEXT,  -- user or system
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (waha_label_id) REFERENCES waha_labels(id) ON DELETE CASCADE,
            UNIQUE(conversation_id, waha_label_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_waha_label_assign_conv ON waha_label_assignments(conversation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_waha_label_assign_label ON waha_label_assignments(waha_label_id)"
    )

    conn.commit()
    logger.info("CRM Phase B tables created/verified")


def _seed_waha_labels(conn: sqlite3.Connection) -> None:
    """Seed default WAHA labels if table is empty."""
    cur = conn.execute("SELECT COUNT(*) as cnt FROM waha_labels WHERE is_predefined = 1")
    if cur.fetchone()["cnt"] > 0:
        return  # Already seeded

    # Seed default labels (not tied to any specific WA number - global defaults)
    for label in DEFAULT_WAHA_LABELS:
        conn.execute(
            """
            INSERT INTO waha_labels (wa_number_id, waha_label_id, name, color, is_predefined)
            VALUES (?, ?, ?, ?, 1)
            """,
            ("default", label["name"].lower().replace(" ", "_"), label["name"], label["color"]),
        )
    conn.commit()
    logger.info(f"Seeded {len(DEFAULT_WAHA_LABELS)} default WAHA labels")


if __name__ == "__main__":
    import sys
    from oneai_reach.config.settings import get_settings

    settings = get_settings()
    run_crm_migration(settings.database.db_file)
    print(f"CRM Phase B migration complete: {settings.database.db_file}")
