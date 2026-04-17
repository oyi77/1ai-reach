"""CS Analytics service - performance metrics and KB optimization."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class AnalyticsService:
    """Analytics engine for CS performance optimization."""

    def __init__(self, config: Settings, db_connection):
        self.config = config
        self._connect = db_connection

    def get_kb_rankings(self, days: int = 30, min_uses: int = 3) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT 
                    kb.id,
                    kb.question,
                    kb.answer,
                    kb.tags,
                    kb.priority,
                    COUNT(ro.id) as times_used,
                    AVG(ro.outcome_score) as avg_score,
                    SUM(CASE WHEN ro.was_effective THEN 1 ELSE 0 END) as successful_replies,
                    AVG(ro.reply_time_seconds) as avg_response_time
                FROM knowledge_base kb
                LEFT JOIN response_outcomes ro ON ro.kb_entry_ids LIKE '%"' || kb.id || '"%'
                WHERE ro.sent_at >= datetime('now', '-{} days')
                GROUP BY kb.id
                HAVING times_used >= {}
                ORDER BY avg_score DESC, times_used DESC
                """.format(days, min_uses)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_scenario_performance(self, days: int = 30) -> dict:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT 
                    ro.pattern_used,
                    ro.user_type,
                    ro.sales_stage,
                    COUNT(*) as total_responses,
                    AVG(ro.outcome_score) as avg_score,
                    SUM(CASE WHEN ro.was_effective THEN 1 ELSE 0 END) as successes
                FROM response_outcomes ro
                WHERE ro.sent_at >= datetime('now', '-{} days')
                GROUP BY ro.pattern_used
                ORDER BY avg_score DESC
                """.format(days)
            )

            scenarios = {}
            for row in cursor.fetchall():
                pattern = row["pattern_used"] or "unknown"
                scenarios[pattern] = {
                    "total": row["total_responses"],
                    "success_rate": row["avg_score"],
                    "successes": row["successes"],
                }
            return scenarios
        finally:
            conn.close()

    def get_learning_recommendations(self) -> list[dict]:
        recommendations = []
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT kb.id, kb.question, COUNT(ro.id) as uses, AVG(ro.outcome_score) as score
                FROM knowledge_base kb
                LEFT JOIN response_outcomes ro ON ro.kb_entry_ids LIKE '%"' || kb.id || '"%'
                GROUP BY kb.id
                HAVING uses >= 5 AND score < 0.4
                """
            )
            for row in cursor.fetchall():
                recommendations.append(
                    {
                        "type": "review_kb",
                        "priority": "high",
                        "kb_id": row["id"],
                        "reason": f"Low effectiveness score: {row['score']:.2f} after {row['uses']} uses",
                        "action": f"Review KB entry #{row['id']}: {row['question'][:50]}...",
                    }
                )

            cursor = conn.execute(
                """
                SELECT response_text, pattern_used, AVG(outcome_score) as score, COUNT(*) as uses
                FROM response_outcomes
                WHERE kb_entry_ids = '[]' OR kb_entry_ids IS NULL
                GROUP BY response_hash
                HAVING uses >= 3 AND score > 0.8
                ORDER BY score DESC
                LIMIT 10
                """
            )
            for row in cursor.fetchall():
                recommendations.append(
                    {
                        "type": "add_to_kb",
                        "priority": "medium",
                        "pattern": row["pattern_used"],
                        "reason": f"High-performing response (score: {row['score']:.2f})",
                        "action": "Consider adding to KB",
                        "sample": row["response_text"][:100] + "...",
                    }
                )

            cursor = conn.execute(
                """
                SELECT pattern_used, COUNT(*) as failures
                FROM response_outcomes
                WHERE outcome_score < 0.3
                GROUP BY pattern_used
                HAVING failures >= 5
                ORDER BY failures DESC
                LIMIT 5
                """
            )
            for row in cursor.fetchall():
                recommendations.append(
                    {
                        "type": "improve_pattern",
                        "priority": "medium",
                        "pattern": row["pattern_used"],
                        "reason": f"{row['failures']} low-scoring responses",
                        "action": "Review and improve pattern",
                    }
                )

            return sorted(recommendations, key=lambda x: x["priority"], reverse=True)
        finally:
            conn.close()

    def get_conversion_timeline(self, days: int = 30) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT 
                    DATE(started_at) as date,
                    COUNT(*) as total,
                    SUM(CASE WHEN final_status IN ('closed', 'purchase') THEN 1 ELSE 0 END) as conversions,
                    SUM(CASE WHEN converted_to_purchase THEN 1 ELSE 0 END) as purchases,
                    AVG(message_count) as avg_messages
                FROM conversation_outcomes
                WHERE started_at >= DATE('now', '-{} days')
                GROUP BY DATE(started_at)
                ORDER BY date
                """.format(days)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_ab_test_results(
        self, pattern_a: str, pattern_b: str, days: int = 30
    ) -> dict:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT 
                    pattern_used,
                    COUNT(*) as n,
                    AVG(outcome_score) as mean_score,
                    AVG(reply_time_seconds) as mean_reply_time
                FROM response_outcomes
                WHERE pattern_used IN (?, ?)
                AND sent_at >= DATE('now', '-{} days')
                GROUP BY pattern_used
                """.format(days),
                (pattern_a, pattern_b),
            )

            results = {row["pattern_used"]: dict(row) for row in cursor.fetchall()}

            if pattern_a not in results or pattern_b not in results:
                return {"error": "Insufficient data for comparison"}

            a = results[pattern_a]
            b = results[pattern_b]

            pooled_std = 0.5
            se = pooled_std * (1 / a["n"] + 1 / b["n"]) ** 0.5
            z_score = (a["mean_score"] - b["mean_score"]) / se if se > 0 else 0

            return {
                "pattern_a": pattern_a,
                "pattern_b": pattern_b,
                "n_a": a["n"],
                "n_b": b["n"],
                "score_a": a["mean_score"],
                "score_b": b["mean_score"],
                "z_score": z_score,
                "winner": pattern_a
                if z_score > 1.0
                else pattern_b
                if z_score < -1.0
                else "tie",
                "significant": abs(z_score) > 1.96,
            }
        finally:
            conn.close()

    def generate_daily_report(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as conversations,
                    AVG(message_count) as avg_length,
                    SUM(CASE WHEN converted_to_purchase THEN 1 ELSE 0 END) as purchases
                FROM conversation_outcomes
                WHERE DATE(started_at) = DATE('now')
                """
            )
            today_stats = dict(cursor.fetchone() or {})

            cursor = conn.execute(
                """
                SELECT pattern_used, COUNT(*) as uses, AVG(outcome_score) as score
                FROM response_outcomes
                WHERE DATE(sent_at) = DATE('now') AND pattern_used IS NOT NULL
                GROUP BY pattern_used
                HAVING uses >= 2
                ORDER BY score DESC
                LIMIT 5
                """
            )
            top_patterns = [dict(row) for row in cursor.fetchall()]

            cursor = conn.execute(
                """
                SELECT COUNT(*) as extracted
                FROM learning_queue
                WHERE DATE(extracted_at) = DATE('now')
                """
            )
            learnings = cursor.fetchone()[0]

            return {
                "date": today,
                "conversations": today_stats.get("conversations", 0),
                "avg_length": round(today_stats.get("avg_length", 0), 1),
                "purchases": today_stats.get("purchases", 0),
                "top_patterns": top_patterns,
                "learnings_today": learnings,
            }
        finally:
            conn.close()

    def export_high_performers(self, output_file: str = None) -> str:
        kb_entries = self.get_kb_rankings(days=30, min_uses=2)[:20]

        export = {
            "generated_at": datetime.now().isoformat(),
            "kb_entries": [
                {
                    "id": e["id"],
                    "question": e["question"],
                    "answer": e["answer"],
                    "effectiveness": e["avg_score"],
                    "uses": e["times_used"],
                }
                for e in kb_entries
            ],
            "scenarios": self.get_scenario_performance(30),
        }

        if output_file:
            Path(output_file).write_text(
                json.dumps(export, indent=2, ensure_ascii=False)
            )
            return output_file

        return json.dumps(export, indent=2, ensure_ascii=False)
