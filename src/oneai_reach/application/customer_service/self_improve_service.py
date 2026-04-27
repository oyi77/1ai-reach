"""CS Self-Improvement service - auto-learn from conversation outcomes."""

from datetime import datetime
from typing import List

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class SelfImproveService:
    """Auto-learn from conversation outcomes to improve responses."""

    def __init__(
        self, config: Settings, db_connection, analytics_service, outcomes_service
    ):
        self.config = config
        self._connect = db_connection
        self.analytics = analytics_service
        self.outcomes = outcomes_service

    def analyze_conversation(self, conversation_id: int) -> dict:
        metrics = self.outcomes.get_conversation_metrics(conversation_id)
        if not metrics:
            return {}

        outcome = metrics.get("outcome", {})
        responses = metrics.get("responses", [])

        result = {
            "conversation_id": conversation_id,
            "final_status": outcome.get("final_status"),
            "total_messages": outcome.get("message_count", 0),
            "effective_responses": [],
            "ineffective_responses": [],
            "suggested_improvements": [],
        }

        for resp in responses:
            if resp.get("was_effective"):
                result["effective_responses"].append(
                    {
                        "text": resp.get("response_text", "")[:200],
                        "pattern": resp.get("pattern_used"),
                        "score": resp.get("outcome_score", 0),
                    }
                )
            else:
                result["ineffective_responses"].append(
                    {
                        "text": resp.get("response_text", "")[:200],
                        "score": resp.get("outcome_score", 0),
                    }
                )

        return result

    def extract_winning_patterns(
        self, days: int = 7, min_score: float = 0.7
    ) -> List[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT 
                    response_text,
                    pattern_used,
                    user_type,
                    AVG(outcome_score) as avg_score,
                    COUNT(*) as times_used,
                    SUM(CASE WHEN was_effective THEN 1 ELSE 0 END) as successes
                FROM response_outcomes
                WHERE sent_at >= datetime('now', '-{} days')
                AND outcome_score >= ?
                GROUP BY response_hash
                HAVING times_used >= 2 AND avg_score >= ?
                ORDER BY avg_score DESC, times_used DESC
                LIMIT 20
                """.format(days),
                (min_score, min_score),
            )

            winners = []
            for row in cursor.fetchall():
                winners.append(
                    {
                        "text": row["response_text"],
                        "pattern": row["pattern_used"],
                        "user_type": row["user_type"],
                        "score": row["avg_score"],
                        "uses": row["times_used"],
                        "successes": row["successes"],
                    }
                )

            try:
                corrected_rows = conn.execute(
                    """
                    SELECT af.corrected_response, af.note, af.rating
                    FROM admin_feedback af
                    WHERE af.corrected_response IS NOT NULL
                    AND af.corrected_response != ''
                    AND af.created_at >= datetime('now', '-{} days')
                    """.format(days),
                ).fetchall()
                for row in corrected_rows:
                    winners.append(
                        {
                            "text": row["corrected_response"],
                            "pattern": "admin_corrected",
                            "user_type": "unknown",
                            "score": 1.0,
                            "uses": 1,
                            "successes": 1,
                            "source": "admin_feedback",
                            "note": row["note"],
                        }
                    )
            except Exception:
                pass

            return winners
        finally:
            conn.close()

    def identify_low_performers(self, days: int = 7) -> List[dict]:
        rankings = self.analytics.get_kb_rankings(days=days, min_uses=2)

        low_performers = []
        for entry in rankings:
            if entry.get("avg_score", 1) < 0.4 and entry.get("times_used", 0) >= 3:
                low_performers.append(
                    {
                        "kb_id": entry["id"],
                        "question": entry["question"],
                        "current_answer": entry["answer"][:100],
                        "score": entry["avg_score"],
                        "uses": entry["times_used"],
                        "suggestion": "Consider rewriting this response",
                    }
                )

        return low_performers

    def suggest_new_kb_entries(self, days: int = 7) -> List[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT message_text, COUNT(*) as frequency
                FROM conversation_messages
                WHERE direction = 'in'
                AND conversation_id IN (
                    SELECT id FROM conversations
                    WHERE last_message_at >= datetime('now', '-{} days')
                )
                AND message_text NOT IN (
                    SELECT question FROM knowledge_base
                )
                GROUP BY message_text
                HAVING frequency >= 3
                ORDER BY frequency DESC
                LIMIT 10
                """.format(days),
            )

            suggestions = []
            for row in cursor.fetchall():
                suggestions.append(
                    {
                        "question": row["message_text"],
                        "frequency": row["frequency"],
                        "suggested_category": "faq",
                        "rationale": f"Asked {row['frequency']} times without KB match",
                    }
                )

            return suggestions
        finally:
            conn.close()

    def generate_weekly_report(self) -> dict:
        funnel = self.outcomes.get_conversion_funnel(days=7)

        report = {
            "period": "Last 7 days",
            "generated_at": datetime.now().isoformat(),
            "funnel_summary": funnel,
            "winning_patterns": self.extract_winning_patterns(days=7),
            "low_performers": self.identify_low_performers(days=7),
            "suggested_entries": self.suggest_new_kb_entries(days=7),
            "admin_feedback_summary": self._get_admin_feedback_summary(),
            "recommendations": [],
        }

        if report["winning_patterns"]:
            report["recommendations"].append(
                f"✅ Add {len(report['winning_patterns'])} winning patterns to KB"
            )

        if report["low_performers"]:
            report["recommendations"].append(
                f"⚠️ Review {len(report['low_performers'])} underperforming KB entries"
            )

        if funnel.get("conversion_rate", 0) < 0.1:
            report["recommendations"].append(
                "🎯 Focus on closing techniques - conversion rate below 10%"
            )

        fb = report["admin_feedback_summary"]
        if fb.get("bad_ratings", 0) > 0:
            report["recommendations"].append(
                f"📝 {fb['bad_ratings']} admin-flagged bad responses — review corrected versions"
            )

        return report

    def _get_admin_feedback_summary(self) -> dict:
        conn = self._connect()
        try:
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
            good = conn.execute(
                "SELECT COUNT(*) FROM admin_feedback WHERE rating = 'good'"
            ).fetchone()[0]
            bad = conn.execute(
                "SELECT COUNT(*) FROM admin_feedback WHERE rating = 'bad'"
            ).fetchone()[0]
            corrected = conn.execute(
                "SELECT COUNT(*) FROM admin_feedback WHERE corrected_response IS NOT NULL AND corrected_response != ''"
            ).fetchone()[0]
            return {
                "good_ratings": good,
                "bad_ratings": bad,
                "corrected_responses": corrected,
            }
        except Exception:
            return {"good_ratings": 0, "bad_ratings": 0, "corrected_responses": 0}
        finally:
            conn.close()

    def apply_learnings(self, dry_run: bool = True) -> dict:
        results = {
            "patterns_added": 0,
            "entries_updated": 0,
            "suggestions_created": 0,
            "admin_corrections_applied": 0,
            "errors": [],
        }

        winners = self.extract_winning_patterns(min_score=0.8)
        for pattern in winners[:5]:
            if dry_run:
                results["patterns_added"] += 1
                continue

            try:
                from kb_manager import add_entry

                add_entry(
                    wa_number_id="default",
                    category="snippet",
                    question=f"Learned pattern: {pattern['pattern'] or 'general'}",
                    answer=pattern["text"],
                    content=f"auto_learned score={pattern['score']:.2f}",
                    tags=f"learned,auto,effective,{pattern['user_type']}",
                    priority=8,
                )
                results["patterns_added"] += 1
            except Exception as e:
                results["errors"].append(f"Failed to add pattern: {e}")

        conn = self._connect()
        try:
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
            corrected = conn.execute(
                """
                SELECT af.corrected_response, af.note, m.message_text as original
                FROM admin_feedback af
                LEFT JOIN conversation_messages m ON af.message_id = m.id
                WHERE af.corrected_response IS NOT NULL
                AND af.corrected_response != ''
                AND af.rating = 'bad'
                ORDER BY af.created_at DESC
                LIMIT 10
                """
            ).fetchall()

            for row in corrected:
                if dry_run:
                    results["admin_corrections_applied"] += 1
                    continue
                try:
                    from kb_manager import add_entry

                    add_entry(
                        wa_number_id="default",
                        category="snippet",
                        question=f"Admin correction for: {row['original'][:100]}",
                        answer=row["corrected_response"],
                        content=f"admin_corrected note={row['note']}",
                        tags="learned,admin,corrected",
                        priority=9,
                    )
                    results["admin_corrections_applied"] += 1
                except Exception as e:
                    results["errors"].append(f"Failed to add correction: {e}")
        except Exception as e:
            results["errors"].append(f"Admin feedback query failed: {e}")
        finally:
            conn.close()

        suggestions = self.suggest_new_kb_entries()
        results["suggestions_created"] = len(suggestions)

        return results
