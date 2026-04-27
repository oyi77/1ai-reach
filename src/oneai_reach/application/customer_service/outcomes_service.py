"""CS Outcomes service - conversation outcome tracking and pattern learning."""

import hashlib
import json

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

OUTCOME_STATUSES = ["abandoned", "engaged", "qualified", "closed", "purchase"]


class OutcomesService:
    """Service for tracking conversation outcomes and learning from success patterns."""

    def __init__(self, config: Settings, db_connection):
        self.config = config
        self._connect = db_connection

    def record_conversation_start(
        self, conversation_id: int, wa_number_id: str, contact_phone: str
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO conversation_outcomes
                    (conversation_id, wa_number_id, contact_phone, final_status, started_at)
                    VALUES (?, ?, ?, 'engaged', datetime('now'))""",
                (conversation_id, wa_number_id, contact_phone),
            )
            conn.commit()
        finally:
            conn.close()

    def record_response_sent(
        self,
        conversation_id: int,
        response_text: str,
        kb_entry_ids: list[int] = None,
        pattern_used: str = None,
        user_type: str = "normal",
        sales_stage: str = "ENTRY",
        wa_number_id: str = None,
    ) -> int:
        response_hash = hashlib.md5(response_text.encode()).hexdigest()[:16]
        kb_ids_json = json.dumps(kb_entry_ids or [])

        conn = self._connect()
        try:
            if wa_number_id:
                cur = conn.execute(
                    """INSERT INTO response_outcomes
                        (conversation_id, wa_number_id, response_hash, response_text, kb_entry_ids,
                         pattern_used, user_type, sales_stage, sent_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (
                        conversation_id,
                        wa_number_id,
                        response_hash,
                        response_text,
                        kb_ids_json,
                        pattern_used,
                        user_type,
                        sales_stage,
                    ),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO response_outcomes
                        (conversation_id, response_hash, response_text, kb_entry_ids,
                         pattern_used, user_type, sales_stage, sent_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (
                        conversation_id,
                        response_hash,
                        response_text,
                        kb_ids_json,
                        pattern_used,
                        user_type,
                        sales_stage,
                    ),
                )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def record_user_reply(
        self,
        conversation_id: int,
        response_text: str,
        user_reply: str,
        time_to_reply_seconds: int = None,
    ) -> None:
        response_hash = hashlib.md5(response_text.encode()).hexdigest()[:16]

        positive_indicators = [
            "mau",
            "order",
            "pesan",
            "beli",
            "transfer",
            "bayar",
            "ok",
            "oke",
            "siap",
            "bisa",
            "yes",
            "ya",
            "minat",
            "harga",
            "berapa",
            "detail",
            "kirim",
            "alamat",
        ]
        negative_indicators = [
            "mahal",
            "jauh",
            "nanti",
            "belum",
            "tidak",
            "gak",
            "ga",
            "skip",
            "batal",
            "cancel",
        ]

        user_reply_lower = user_reply.lower()
        positive_score = sum(1 for p in positive_indicators if p in user_reply_lower)
        negative_score = sum(1 for n in negative_indicators if n in user_reply_lower)

        is_effective = positive_score > negative_score
        outcome_score = (positive_score - negative_score) / max(
            positive_score + negative_score, 1
        )
        outcome_score = max(0, min(1, (outcome_score + 1) / 2))

        conn = self._connect()
        try:
            conn.execute(
                """UPDATE response_outcomes
                    SET next_user_action = 'reply',
                        reply_time_seconds = ?,
                        was_effective = ?,
                        outcome_score = ?
                    WHERE id = (
                        SELECT id FROM response_outcomes
                        WHERE conversation_id = ? AND response_hash = ?
                        ORDER BY sent_at DESC LIMIT 1
                    )""",
                (
                    time_to_reply_seconds,
                    is_effective,
                    outcome_score,
                    conversation_id,
                    response_hash,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def record_journey_step(
        self, conversation_id: int, wa_number_id: str, step_name: str, step_order: int
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO user_journey
                    (conversation_id, wa_number_id, step_name, step_order, reached_at)
                    VALUES (?, ?, ?, ?, datetime('now'))""",
                (conversation_id, wa_number_id, step_name, step_order),
            )
            conn.commit()
        finally:
            conn.close()

    def record_final_outcome(
        self,
        conversation_id: int,
        status: str,
        total_value: float = 0,
        escalation_reason: str = None,
    ) -> None:
        if status not in OUTCOME_STATUSES:
            raise ValueError(
                f"Invalid status: {status}. Must be one of {OUTCOME_STATUSES}"
            )

        is_purchase = status == "purchase"

        conn = self._connect()
        try:
            conn.execute(
                """UPDATE conversation_outcomes
                    SET final_status = ?,
                        ended_at = datetime('now'),
                        total_value = ?,
                        escalation_reason = ?,
                        converted_to_purchase = ?,
                        total_messages = (SELECT COUNT(*) FROM response_outcomes WHERE conversation_id = ?)
                    WHERE conversation_id = ?""",
                (
                    status,
                    total_value,
                    escalation_reason,
                    is_purchase,
                    conversation_id,
                    conversation_id,
                ),
            )

            if is_purchase:
                conn.execute(
                    """UPDATE response_outcomes
                        SET was_effective = TRUE, outcome_score = 1.0
                        WHERE conversation_id = ? AND outcome_score < 0.5""",
                    (conversation_id,),
                )

            conn.commit()
        finally:
            conn.close()

        if status in ["closed", "purchase"]:
            self.queue_for_learning(conversation_id, status)

    def record_pattern_use(
        self,
        pattern_id: str,
        pattern_text: str,
        scenario: str,
        was_successful: bool = False,
        response_time_seconds: int = None,
    ) -> None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT times_used, times_successful FROM pattern_effectiveness WHERE pattern_id = ? AND scenario = ?",
                (pattern_id, scenario),
            ).fetchone()

            if row:
                times_used = row["times_used"] + 1
                times_successful = row["times_successful"] + (
                    1 if was_successful else 0
                )
                success_rate = times_successful / times_used

                conn.execute(
                    """UPDATE pattern_effectiveness
                        SET times_used = ?,
                            times_successful = ?,
                            success_rate = ?,
                            last_used = datetime('now')
                        WHERE pattern_id = ? AND scenario = ?""",
                    (times_used, times_successful, success_rate, pattern_id, scenario),
                )
            else:
                conn.execute(
                    """INSERT INTO pattern_effectiveness
                        (pattern_id, pattern_text, scenario, times_used, times_successful,
                         success_rate, last_used)
                        VALUES (?, ?, ?, 1, ?, ?, datetime('now'))""",
                    (
                        pattern_id,
                        pattern_text,
                        scenario,
                        1 if was_successful else 0,
                        1.0 if was_successful else 0.0,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_best_patterns(self, scenario: str, limit: int = 3) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT pattern_id, pattern_text, success_rate, times_used
                    FROM pattern_effectiveness
                    WHERE scenario = ? AND times_used >= 3
                    ORDER BY success_rate DESC, times_used DESC
                    LIMIT ?""",
                (scenario, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def queue_for_learning(self, conversation_id: int, outcome: str) -> None:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT response_text, pattern_used, user_type, sales_stage
                    FROM response_outcomes
                    WHERE conversation_id = ? AND was_effective = TRUE
                    ORDER BY sent_at""",
                (conversation_id,),
            ).fetchall()

            if not rows:
                return

            winning = [
                {
                    "response": r["response_text"],
                    "pattern": r["pattern_used"],
                    "user_type": r["user_type"],
                    "stage": r["sales_stage"],
                }
                for r in rows
            ]

            scenario = "general"
            for r in rows:
                if r["pattern_used"]:
                    if (
                        "price" in r["pattern_used"]
                        or r["user_type"] == "price_sensitive"
                    ):
                        scenario = "price_objection"
                        break
                    elif "close" in r["pattern_used"]:
                        scenario = "closing"
                        break
                    elif "bulk" in r["pattern_used"] or r["user_type"] == "bulk":
                        scenario = "bulk_order"
                        break

            conn.execute(
                """INSERT INTO learning_queue
                    (conversation_id, winning_responses, scenario_type, priority)
                    VALUES (?, ?, ?, ?)""",
                (
                    conversation_id,
                    json.dumps(winning),
                    scenario,
                    8 if outcome == "purchase" else 5,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_conversion_funnel(self, days: int = 30) -> dict:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """SELECT final_status, COUNT(*) as count
                    FROM conversation_outcomes
                    WHERE started_at >= datetime('now', ? || ' days')
                    GROUP BY final_status""",
                (f"-{days}",),
            )

            stats = {status: 0 for status in OUTCOME_STATUSES}
            for row in cursor:
                stats[row["final_status"]] = row["count"]

            total = sum(stats.values())
            if total > 0:
                stats["conversion_rate"] = (
                    stats.get("purchase", 0) + stats.get("closed", 0)
                ) / total
                stats["engagement_rate"] = (total - stats.get("abandoned", 0)) / total

            stats["total"] = total
            return stats
        finally:
            conn.close()

    def get_conversation_metrics(self, conversation_id: int) -> dict:
        conn = self._connect()
        try:
            outcome = conn.execute(
                "SELECT * FROM conversation_outcomes WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()

            if not outcome:
                return {}

            responses = conn.execute(
                """SELECT * FROM response_outcomes
                    WHERE conversation_id = ?
                    ORDER BY sent_at""",
                (conversation_id,),
            ).fetchall()

            journey = conn.execute(
                """SELECT * FROM user_journey
                    WHERE conversation_id = ?
                    ORDER BY step_order""",
                (conversation_id,),
            ).fetchall()

            return {
                "outcome": dict(outcome),
                "responses": [dict(r) for r in responses],
                "journey": [dict(j) for j in journey],
            }
        finally:
            conn.close()
