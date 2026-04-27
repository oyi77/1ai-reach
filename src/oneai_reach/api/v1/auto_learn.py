"""Auto-learn analytics and improvement API endpoints."""

from typing import Optional

from fastapi import APIRouter, Request

from oneai_reach.infrastructure.legacy import state_manager

router = APIRouter(tags=["auto-learn"])


@router.get("/report")
async def api_auto_learn_report(session: Optional[str] = None):
    conn = state_manager._connect()
    try:
        funnel_summary = {}
        for row in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM conversations GROUP BY status"
        ).fetchall():
            funnel_summary[row[0] or "unknown"] = row[1]

        winning = []
        for row in conn.execute(
            """SELECT pattern_used, response_text, AVG(outcome_score) as avg_score, COUNT(*) as uses
               FROM response_outcomes
               WHERE was_effective = 1 AND pattern_used IS NOT NULL AND pattern_used != ''
               GROUP BY pattern_used ORDER BY avg_score DESC LIMIT 10"""
        ).fetchall():
            winning.append({"pattern": row[0], "text": row[1][:200] if row[1] else "", "score": round(row[2], 2), "uses": row[3]})

        low_performers = []
        for row in conn.execute(
            """SELECT response_text, AVG(outcome_score) as avg_score, COUNT(*) as uses
               FROM response_outcomes
               WHERE was_effective = 0
               GROUP BY response_hash ORDER BY avg_score ASC LIMIT 10"""
        ).fetchall():
            suggestion = "Consider revising this response pattern"
            low_performers.append({"question": row[0][:100] if row[0] else "", "suggestion": suggestion, "score": round(row[1], 2), "uses": row[2]})

        suggested_entries = []
        for row in conn.execute(
            """SELECT cm.message_text, COUNT(*) as freq
               FROM conversation_messages cm
               JOIN conversations c ON cm.conversation_id = c.id
               WHERE cm.direction = 'in' AND c.wa_number_id = ?
               GROUP BY cm.message_text ORDER BY freq DESC LIMIT 10""",
            (session or "default",),
        ).fetchall():
            q = row[0].strip() if row[0] else ""
            if q and len(q) > 3:
                kb_match = conn.execute(
                    "SELECT COUNT(*) FROM knowledge_base WHERE question LIKE ?", (f"%{q[:30]}%",)
                ).fetchone()[0]
                if kb_match == 0:
                    suggested_entries.append({"question": q[:100], "frequency": row[1]})

        fb_stats = {"good": 0, "bad": 0}
        for row in conn.execute("SELECT rating, COUNT(*) FROM admin_feedback GROUP BY rating").fetchall():
            fb_stats[row[0]] = row[1]

        return {
            "status": "success",
            "data": {
                "funnel_summary": funnel_summary,
                "winning_patterns": winning,
                "low_performers": low_performers,
                "suggested_entries": suggested_entries[:5],
                "feedback_stats": fb_stats,
            },
        }
    finally:
        conn.close()


@router.post("/improve")
async def api_auto_learn_improve(request: Request):
    data = await request.json()
    session = data.get("session", "default")
    apply_changes = data.get("apply", False)

    conn = state_manager._connect()
    errors = []
    patterns_added = 0
    suggestions_created = 0

    try:
        bad_feedback = conn.execute(
            """SELECT af.conversation_id, af.message_id, af.corrected_response, cm.message_text as original
               FROM admin_feedback af
               JOIN conversation_messages cm ON af.message_id = cm.id
               WHERE af.rating = 'bad' AND af.corrected_response IS NOT NULL AND af.corrected_response != ''
               ORDER BY af.created_at DESC LIMIT 20"""
        ).fetchall()

        for fb in bad_feedback:
            corrected = fb["corrected_response"].strip()
            original_inbound = conn.execute(
                "SELECT message_text FROM conversation_messages WHERE conversation_id = ? AND direction = 'in' AND id < ? ORDER BY id DESC LIMIT 1",
                (fb["conversation_id"], fb["message_id"]),
            ).fetchone()
            question = original_inbound["message_text"].strip()[:200] if original_inbound else ""

            if not question:
                continue

            existing = conn.execute(
                "SELECT id FROM knowledge_base WHERE question LIKE ? AND wa_number_id = ?",
                (f"%{question[:50]}%", session),
            ).fetchone()

            if existing and apply_changes:
                conn.execute(
                    "UPDATE knowledge_base SET answer = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (corrected, existing["id"]),
                )
                patterns_added += 1
            elif not existing and apply_changes:
                conn.execute(
                    "INSERT INTO knowledge_base (wa_number_id, category, question, answer, priority) VALUES (?, 'auto-learn', ?, ?, 5)",
                    (session, question, corrected),
                )
                patterns_added += 1
            else:
                suggestions_created += 1

        winning = conn.execute(
            """SELECT pattern_used, response_text, AVG(outcome_score) as score
               FROM response_outcomes WHERE was_effective = 1 AND pattern_used IS NOT NULL
               GROUP BY pattern_used ORDER BY score DESC LIMIT 5"""
        ).fetchall()

        for w in winning:
            existing = conn.execute(
                "SELECT id FROM pattern_effectiveness WHERE pattern_text = ?",
                (w["pattern_used"],),
            ).fetchone()
            if not existing and apply_changes and w["pattern_used"]:
                conn.execute(
                    "INSERT INTO pattern_effectiveness (pattern_text, scenario, times_used, times_successful, success_rate) VALUES (?, 'auto-detected', 1, 1, 1.0)",
                    (w["pattern_used"],),
                )
                patterns_added += 1
            elif not existing:
                suggestions_created += 1

        if apply_changes:
            conn.commit()

        return {
            "status": "success",
            "data": {
                "ok": True,
                "patterns_added": patterns_added,
                "suggestions_created": suggestions_created,
                "errors": errors,
            },
        }
    except Exception as e:
        errors.append(str(e))
        return {
            "status": "error",
            "data": {"ok": False, "patterns_added": 0, "suggestions_created": 0, "errors": errors},
        }
    finally:
        conn.close()