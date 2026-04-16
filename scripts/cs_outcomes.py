"""
CS Outcomes Tracker — Self-improvement through conversation outcome tracking.

Tracks:
- Conversation outcomes (abandoned, engaged, qualified, closed, purchase)
- Response effectiveness (which KB entries lead to positive outcomes)
- Pattern learning (extract winning responses into playbook)
- User journey analytics (drop-off points, conversion rates)

Usage:
    from cs_outcomes import record_outcome, get_conversation_metrics, learn_from_winners

Tables:
- conversation_outcomes: Final outcome per conversation
- response_outcomes: Track each response's effectiveness
- user_journey: Step-by-step conversion funnel tracking
- pattern_effectiveness: Which patterns work best per scenario
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from config import DB_FILE

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_OUTCOMES_SCHEMA = """
-- Conversation outcomes (one per conversation)
CREATE TABLE IF NOT EXISTS conversation_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    wa_number_id TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    final_status TEXT NOT NULL,  -- abandoned, engaged, qualified, closed, purchase
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    total_value REAL DEFAULT 0,  -- For purchases
    escalation_reason TEXT,
    converted_to_purchase BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(conversation_id)
);

-- Response effectiveness (track each agent response)
CREATE TABLE IF NOT EXISTS response_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    wa_number_id TEXT,
    response_hash TEXT NOT NULL,  -- hash of response text for deduplication
    response_text TEXT NOT NULL,   -- actual response sent
    kb_entry_ids TEXT,             -- JSON array of KB entries used
    pattern_used TEXT,             -- pattern ID if from playbook
    user_type TEXT,                -- normal, price_sensitive, urgent, bulk, friction
    sales_stage TEXT,              -- ENTRY, QUALIFY, OFFER, etc.
    sent_at TIMESTAMP NOT NULL,
    next_user_action TEXT,         -- reply, abandon, purchase, escalate
    reply_time_seconds INTEGER,    -- time to next user message
    was_effective BOOLEAN DEFAULT FALSE,  -- led to positive outcome
    outcome_score REAL DEFAULT 0,  -- 0-1 effectiveness score
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User journey tracking (conversion funnel)
CREATE TABLE IF NOT EXISTS user_journey (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    wa_number_id TEXT NOT NULL,
    step_name TEXT NOT NULL,       -- e.g., "first_reply", "pricing_asked", "shipping_discussed"
    step_order INTEGER NOT NULL,
    reached_at TIMESTAMP NOT NULL,
    dropped_off BOOLEAN DEFAULT FALSE,
    time_spent_seconds INTEGER
);

-- Pattern effectiveness analytics
CREATE TABLE IF NOT EXISTS pattern_effectiveness (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id TEXT NOT NULL,
    pattern_text TEXT NOT NULL,
    scenario TEXT NOT NULL,        -- e.g., "price_objection", "closing_request"
    times_used INTEGER DEFAULT 0,
    times_successful INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0,
    avg_response_time_seconds REAL DEFAULT 0,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pattern_id, scenario)
);

-- Learning queue (patterns to extract from successful conversations)
CREATE TABLE IF NOT EXISTS learning_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    winning_responses TEXT NOT NULL,  -- JSON array of effective responses
    scenario_type TEXT NOT NULL,      -- what scenario was handled
    extracted_at TIMESTAMP,
    added_to_kb BOOLEAN DEFAULT FALSE,
    priority INTEGER DEFAULT 5,     -- 1-10, higher = learn first
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_outcomes_conv ON conversation_outcomes(conversation_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_status ON conversation_outcomes(final_status);
CREATE INDEX IF NOT EXISTS idx_outcomes_phone ON conversation_outcomes(contact_phone);
CREATE INDEX IF NOT EXISTS idx_response_conv ON response_outcomes(conversation_id);
CREATE INDEX IF NOT EXISTS idx_response_pattern ON response_outcomes(pattern_used);
CREATE INDEX IF NOT EXISTS idx_journey_conv ON user_journey(conversation_id);
CREATE INDEX IF NOT EXISTS idx_pattern_scenario ON pattern_effectiveness(scenario);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_outcomes_db():
    """Initialize outcomes tables."""
    conn = _connect()
    try:
        conn.executescript(_OUTCOMES_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Outcome Recording
# ---------------------------------------------------------------------------

OUTCOME_STATUSES = ["abandoned", "engaged", "qualified", "closed", "purchase"]


def record_conversation_start(
    conversation_id: int,
    wa_number_id: str,
    contact_phone: str,
) -> None:
    """Record the start of a conversation."""
    conn = _connect()
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
    conversation_id: int,
    response_text: str,
    kb_entry_ids: list[int] = None,
    pattern_used: str = None,
    user_type: str = "normal",
    sales_stage: str = "ENTRY",
    wa_number_id: str = None,
) -> int:
    """Record an agent response for effectiveness tracking. Returns response_id."""
    import hashlib

    response_hash = hashlib.md5(response_text.encode()).hexdigest()[:16]
    kb_ids_json = json.dumps(kb_entry_ids or [])

    conn = _connect()
    try:
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
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def record_user_reply(
    conversation_id: int,
    response_text: str,
    user_reply: str,
    time_to_reply_seconds: int = None,
) -> None:
    """Update response effectiveness based on user reply."""
    import hashlib

    response_hash = hashlib.md5(response_text.encode()).hexdigest()[:16]

    # Determine if effective (simplified: user replied with interest)
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
    outcome_score = max(0, min(1, (outcome_score + 1) / 2))  # Normalize to 0-1

    conn = _connect()
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
    conversation_id: int,
    wa_number_id: str,
    step_name: str,
    step_order: int,
) -> None:
    """Record a step in the user journey."""
    conn = _connect()
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
    conversation_id: int,
    status: str,
    total_value: float = 0,
    escalation_reason: str = None,
) -> None:
    """Record the final outcome of a conversation."""
    if status not in OUTCOME_STATUSES:
        raise ValueError(f"Invalid status: {status}. Must be one of {OUTCOME_STATUSES}")

    is_purchase = status == "purchase"

    conn = _connect()
    try:
        conn.execute(
            """UPDATE conversation_outcomes
                SET final_status = ?,
                    ended_at = datetime('now'),
                    total_value = ?,
                    escalation_reason = ?,
                    converted_to_purchase = ?,
                    message_count = (SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ?)
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

        # Update response effectiveness based on final outcome
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

    # Queue for learning if successful
    if status in ["closed", "purchase"]:
        queue_for_learning(conversation_id, status)


# ---------------------------------------------------------------------------
# Pattern Effectiveness
# ---------------------------------------------------------------------------


def record_pattern_use(
    pattern_id: str,
    pattern_text: str,
    scenario: str,
    was_successful: bool = False,
    response_time_seconds: int = None,
) -> None:
    """Track pattern effectiveness."""
    conn = _connect()
    try:
        # Check if exists
        row = conn.execute(
            "SELECT times_used, times_successful FROM pattern_effectiveness WHERE pattern_id = ? AND scenario = ?",
            (pattern_id, scenario),
        ).fetchone()

        if row:
            times_used = row["times_used"] + 1
            times_successful = row["times_successful"] + (1 if was_successful else 0)
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


def get_best_patterns(scenario: str, limit: int = 3) -> list[dict]:
    """Get the most effective patterns for a scenario."""
    conn = _connect()
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


# ---------------------------------------------------------------------------
# Learning System
# ---------------------------------------------------------------------------


def queue_for_learning(conversation_id: int, outcome: str) -> None:
    """Queue a winning conversation for pattern extraction."""
    conn = _connect()
    try:
        # Get effective responses from this conversation
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

        # Determine scenario type from patterns
        scenario = "general"
        for r in rows:
            if r["pattern_used"]:
                if "price" in r["pattern_used"] or r["user_type"] == "price_sensitive":
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


def extract_learnings(limit: int = 10) -> list[dict]:
    """Extract learnings from successful conversations."""
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT id, conversation_id, winning_responses, scenario_type
                FROM learning_queue
                WHERE added_to_kb = FALSE
                ORDER BY priority DESC, created_at ASC
                LIMIT ?""",
            (limit,),
        ).fetchall()

        learnings = []
        for row in rows:
            learnings.append(
                {
                    "id": row["id"],
                    "conversation_id": row["conversation_id"],
                    "responses": json.loads(row["winning_responses"]),
                    "scenario": row["scenario_type"],
                }
            )
        return learnings
    finally:
        conn.close()


def mark_learning_extracted(learning_id: int) -> None:
    """Mark learning as extracted and added to KB."""
    conn = _connect()
    try:
        conn.execute(
            """UPDATE learning_queue
                SET extracted_at = datetime('now'), added_to_kb = TRUE
                WHERE id = ?""",
            (learning_id,),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def get_conversion_funnel(days: int = 30) -> dict:
    """Get conversion funnel stats."""
    conn = _connect()
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


def get_kb_effectiveness(kb_entry_id: int = None, limit: int = 20) -> list[dict]:
    """Get effectiveness metrics for KB entries."""
    conn = _connect()
    try:
        if kb_entry_id:
            rows = conn.execute(
                """SELECT kb_entry_ids, AVG(outcome_score) as avg_score,
                          COUNT(*) as times_used,
                          SUM(CASE WHEN was_effective THEN 1 ELSE 0 END) as effective_count
                    FROM response_outcomes
                    WHERE kb_entry_ids LIKE ?
                    GROUP BY kb_entry_ids""",
                (f'%"{kb_entry_id}"%',),
            ).fetchall()
        else:
            # Get top performing responses
            rows = conn.execute(
                """SELECT response_text, pattern_used, AVG(outcome_score) as avg_score,
                          COUNT(*) as times_used,
                          SUM(CASE WHEN was_effective THEN 1 ELSE 0 END) as effective_count
                    FROM response_outcomes
                    GROUP BY response_hash
                    HAVING times_used >= 2
                    ORDER BY avg_score DESC, times_used DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_conversation_metrics(conversation_id: int) -> dict:
    """Get detailed metrics for a conversation."""
    conn = _connect()
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


def get_learning_stats() -> dict:
    """Get learning system statistics."""
    conn = _connect()
    try:
        total_learned = conn.execute(
            "SELECT COUNT(*) FROM learning_queue WHERE added_to_kb = TRUE"
        ).fetchone()[0]

        pending = conn.execute(
            "SELECT COUNT(*) FROM learning_queue WHERE added_to_kb = FALSE"
        ).fetchone()[0]

        top_scenarios = conn.execute(
            """SELECT scenario_type, COUNT(*) as count
                FROM learning_queue
                GROUP BY scenario_type
                ORDER BY count DESC
                LIMIT 5"""
        ).fetchall()

        return {
            "total_learned": total_learned,
            "pending_extraction": pending,
            "top_scenarios": [dict(r) for r in top_scenarios],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    init_outcomes_db()

    p = argparse.ArgumentParser(description="CS Outcomes Tracker")
    p.add_argument("--funnel", action="store_true", help="Show conversion funnel")
    p.add_argument("--days", type=int, default=30, help="Days to analyze")
    p.add_argument("--top-patterns", action="store_true", help="Show top patterns")
    p.add_argument("--scenario", default="closing", help="Scenario for patterns")
    p.add_argument(
        "--learning-stats", action="store_true", help="Learning system stats"
    )
    p.add_argument("--extract", action="store_true", help="Extract learnings")

    args = p.parse_args()

    if args.funnel:
        funnel = get_conversion_funnel(args.days)
        print(f"\n📊 Conversion Funnel (last {args.days} days)")
        print(f"Total conversations: {funnel['total']}")
        for status in OUTCOME_STATUSES:
            count = funnel.get(status, 0)
            pct = (count / funnel["total"] * 100) if funnel["total"] > 0 else 0
            emoji = {
                "abandoned": "💔",
                "engaged": "💬",
                "qualified": "✅",
                "closed": "🤝",
                "purchase": "💰",
            }.get(status, "📋")
            print(f"  {emoji} {status}: {count} ({pct:.1f}%)")
        print(f"\nEngagement rate: {funnel.get('engagement_rate', 0) * 100:.1f}%")
        print(f"Conversion rate: {funnel.get('conversion_rate', 0) * 100:.1f}%")

    elif args.top_patterns:
        patterns = get_best_patterns(args.scenario, limit=5)
        print(f"\n🏆 Top Patterns for '{args.scenario}'")
        for i, p in enumerate(patterns, 1):
            print(f"\n{i}. {p['pattern_id']} (Success: {p['success_rate'] * 100:.1f}%)")
            print(f"   Used: {p['times_used']} times")
            print(f"   " + p["pattern_text"][:100] + "...")

    elif args.learning_stats:
        stats = get_learning_stats()
        print(f"\n🧠 Learning System Stats")
        print(f"  Total learned: {stats['total_learned']}")
        print(f"  Pending extraction: {stats['pending_extraction']}")
        print(f"\n  Top scenarios:")
        for s in stats["top_scenarios"]:
            print(f"    - {s['scenario_type']}: {s['count']}")

    elif args.extract:
        learnings = extract_learnings(limit=5)
        print(f"\n📚 Extracting {len(learnings)} learnings...")
        for l in learnings:
            print(f"\n  Conversation {l['conversation_id']} ({l['scenario']}):")
            for r in l["responses"][:2]:
                print(f"    - {r['response'][:60]}...")

    else:
        p.print_help()
