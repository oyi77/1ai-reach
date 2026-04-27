"""Conversation cleanup — mark stale conversations as cold."""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from state_manager import _connect, init_db


def cleanup_stale_conversations(hours: int = 48) -> dict:
    """Mark conversations inactive for >hours as cold."""
    conn = _connect()
    try:
        # Find active conversations with last_message_at older than threshold
        result = conn.execute(
            """
            UPDATE conversations 
            SET status = 'cold'
            WHERE status = 'active' 
            AND last_message_at < datetime('now', ?)
        """,
            (f"-{hours} hours",),
        )
        count = result.rowcount
        conn.commit()
        return {"cleaned": count}
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    result = cleanup_stale_conversations()
    print(
        f"[conversation_cleanup] Marked {result['cleaned']} stale conversations as cold"
    )
