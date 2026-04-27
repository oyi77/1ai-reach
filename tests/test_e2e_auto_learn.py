"""E2E Tests for Auto-Learn System"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.mark.filterwarnings("ignore:scripts/cs_outcomes.py is deprecated:DeprecationWarning")
@pytest.mark.filterwarnings("ignore:scripts/cs_self_improve.py is deprecated:DeprecationWarning")


class TestAutoLearnE2E:
    def test_complete_learning_cycle(self, fresh_db):
        from cs_outcomes import (
            record_conversation_start,
            record_response_sent,
            record_user_reply,
            record_final_outcome,
            get_conversation_metrics,
        )
        from cs_self_improve import SelfImprovementEngine

        wa_number_id = "test_session"
        conv_id = 1

        record_conversation_start(
            conversation_id=conv_id,
            wa_number_id=wa_number_id,
            contact_phone="628123456789",
        )

        response_text = "Halo! Terima kasih."
        record_response_sent(
            conversation_id=conv_id,
            response_text=response_text,
            kb_entry_ids=[1, 2],
            pattern_used="greeting",
            user_type="normal",
            sales_stage="ENTRY",
        )

        record_user_reply(
            conversation_id=conv_id,
            response_text=response_text,
            user_reply="Ya mau",
            time_to_reply_seconds=30,
        )

        record_final_outcome(
            conversation_id=conv_id, status="purchase", total_value=5000000
        )

        metrics = get_conversation_metrics(conv_id)
        assert metrics is not None

        engine = SelfImprovementEngine(wa_number_id)
        analysis = engine.analyze_conversation(conv_id)
        assert analysis["conversation_id"] == conv_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
