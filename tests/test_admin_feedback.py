"""Unit tests for cs_self_improve admin feedback integration."""

import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = str(Path(__file__).parent.parent / "scripts")
sys.path.insert(0, SCRIPTS_DIR)


@pytest.mark.filterwarnings("ignore:scripts/cs_self_improve.py is deprecated:DeprecationWarning")


def _seed_feedback(db_path, conv_id, message_id, rating, corrected=""):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO admin_feedback (conversation_id, message_id, rating, note, corrected_response) VALUES (?, ?, ?, ?, ?)",
        (conv_id, message_id, rating, "test", corrected),
    )
    conn.commit()
    conn.close()


class TestAdminFeedbackSummary:
    def test_summary_counts_ratings(self, fresh_db):
        from cs_self_improve import SelfImprovementEngine

        _seed_feedback(fresh_db, 1, 1, "good", "")
        _seed_feedback(fresh_db, 2, 2, "bad", "Ini yang lebih baik")

        engine = SelfImprovementEngine("test")
        summary = engine._get_admin_feedback_summary()
        assert summary["good_ratings"] == 1
        assert summary["bad_ratings"] == 1
        assert summary["corrected_responses"] == 1

    def test_summary_empty_when_no_feedback(self, fresh_db):
        from cs_self_improve import SelfImprovementEngine

        engine = SelfImprovementEngine("test")
        summary = engine._get_admin_feedback_summary()
        assert summary["good_ratings"] == 0
        assert summary["bad_ratings"] == 0
        assert summary["corrected_responses"] == 0

    def test_winning_patterns_includes_corrections(self, fresh_db):
        from cs_self_improve import SelfImprovementEngine
        from conversation_tracker import get_or_create_conversation

        conv = get_or_create_conversation("test", "628111222333", engine_mode="cs")
        conv_id = conv["id"]

        _seed_feedback(fresh_db, conv_id, 1, "bad", "Halo Kak! Ada yang bisa dibantu?")

        engine = SelfImprovementEngine("test")
        winners = engine.extract_winning_patterns(days=7)
        admin = [w for w in winners if w.get("source") == "admin_feedback"]
        assert len(admin) == 1
        assert "Halo Kak" in admin[0]["text"]
        assert admin[0]["score"] == 1.0

    def test_apply_learnings_dry_run_counts_corrections(self, fresh_db):
        from cs_self_improve import SelfImprovementEngine
        from conversation_tracker import get_or_create_conversation, add_message

        conv = get_or_create_conversation("test", "628999888777", engine_mode="cs")
        conv_id = conv["id"]
        msg_id = add_message(conv_id, "out", "Original AI response here")

        _seed_feedback(fresh_db, conv_id, msg_id, "bad", "Better response here")

        engine = SelfImprovementEngine("test")
        results = engine.apply_learnings(dry_run=True)
        assert results["admin_corrections_applied"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
