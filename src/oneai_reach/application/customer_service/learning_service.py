"""CS Learning service - CLI wrapper for self-improvement management."""

import argparse
from typing import Optional

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class LearningService:
    """Service for managing CS learning and self-improvement commands."""

    def __init__(self, config: Settings, self_improve_service):
        self.config = config
        self.self_improve_service = self_improve_service

    def generate_report(self, wa_number_id: str) -> dict:
        engine = self.self_improve_service
        report = engine.generate_weekly_report()

        return {
            "wa_number_id": wa_number_id,
            "funnel_summary": report["funnel_summary"],
            "winning_patterns": report["winning_patterns"][:5],
            "low_performers": report["low_performers"][:5],
            "suggested_entries": report["suggested_entries"][:5],
            "recommendations": report["recommendations"],
        }

    def apply_improvements(self, wa_number_id: str, dry_run: bool = True) -> dict:
        engine = self.self_improve_service
        results = engine.apply_learnings(dry_run=dry_run)

        return {
            "patterns_added": results["patterns_added"],
            "suggestions_created": results["suggestions_created"],
            "admin_corrections_applied": results.get("admin_corrections_applied", 0),
            "errors": results["errors"],
            "dry_run": dry_run,
        }

    def record_feedback(
        self,
        conversation_id: int,
        response_text: str,
        reaction: str,
        outcome: str,
    ) -> bool:
        from cs_outcomes import record_outcome_feedback

        record_outcome_feedback(
            conversation_id=conversation_id,
            response_text=response_text,
            user_reaction=reaction,
            outcome=outcome,
        )
        return True
