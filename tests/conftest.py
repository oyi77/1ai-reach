import sys
import tempfile
from pathlib import Path

import pytest

_root = Path(__file__).parent.parent

sys.path.insert(0, str(_root / "src"))
sys.path.insert(0, str(_root / "scripts"))


@pytest.fixture(scope="function")
def fresh_db(request):
    if "integration/application" in str(request.fspath):
        yield None
        return

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    import config

    original_db = config.DB_FILE
    config.DB_FILE = Path(db_path)

    stale = [
        m
        for m in sys.modules
        if m.startswith("cs_")
        or m in ("kb_manager", "state_manager", "conversation_tracker")
    ]
    for m in stale:
        del sys.modules[m]

    from state_manager import init_db

    init_db()

    from cs_outcomes import init_outcomes_db

    init_outcomes_db()

    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            rating TEXT NOT NULL,
            note TEXT DEFAULT '',
            corrected_response TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    conn.close()

    yield db_path

    config.DB_FILE = original_db
    Path(db_path).unlink(missing_ok=True)
