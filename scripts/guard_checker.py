"""
Cross-contamination guard audit & integration testing.

Provides two main capabilities:
  1. check_guard(contact_phone) — look up a single contact and report which
     engine modes are safe for it.
  2. run_guard_audit() — scan every active conversation + every lead and flag
     contacts that exist in the cold-call funnel AND have active non-cold
     conversations (a violation).

CLI
---
    python3 scripts/guard_checker.py --audit
    python3 scripts/guard_checker.py --check 628111222333
"""

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from state_manager import _connect, init_db  # noqa: E402

# ── Cold-funnel stages (mirrors conversation_tracker._COLD_FUNNEL_STAGES) ──
_COLD_FUNNEL_STAGES = frozenset(
    {
        "new",
        "enriched",
        "draft_ready",
        "needs_revision",
        "reviewed",
        "contacted",
        "followed_up",
    }
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_phone(raw: str) -> str:
    """Strip everything except digits from a phone string."""
    return "".join(ch for ch in raw if ch.isdigit())


def _is_cold_lead(contact_phone: str, conn) -> bool:
    """Return True when *contact_phone* matches a lead in the cold-call funnel.

    Uses suffix-matching on digit-only strings to cope with '+', spaces and
    dashes stored in the leads table.  The caller must supply an open
    *conn* (sqlite3.Connection with row_factory=sqlite3.Row).
    """
    digits = _normalize_phone(contact_phone)
    if not digits:
        return False
    rows = conn.execute(
        "SELECT phone, internationalPhoneNumber, status FROM leads"
    ).fetchall()
    for row in rows:
        for col in ("phone", "internationalPhoneNumber"):
            stored = row[col] or ""
            stored_digits = "".join(ch for ch in stored if ch.isdigit())
            if stored_digits and (
                stored_digits.endswith(digits) or digits.endswith(stored_digits)
            ):
                if row["status"] in _COLD_FUNNEL_STAGES:
                    return True
    return False


def _has_active_conversation(contact_phone: str, engine_mode: str, conn) -> bool:
    """Return True when *contact_phone* has an active conversation in *engine_mode*.

    The caller must supply an open *conn*.
    """
    digits = _normalize_phone(contact_phone)
    if not digits:
        return False
    rows = conn.execute(
        "SELECT contact_phone FROM conversations "
        "WHERE status = 'active' AND engine_mode = ?",
        (engine_mode,),
    ).fetchall()
    for row in rows:
        stored_digits = _normalize_phone(row["contact_phone"])
        if stored_digits and (
            stored_digits.endswith(digits) or digits.endswith(stored_digits)
        ):
            return True
    return False


# ── Public API ───────────────────────────────────────────────────────────────


def check_guard(contact_phone: str) -> dict:
    """Check the cross-contamination guard status for a single contact.

    Returns a dict with three boolean flags plus a ``safe_for`` list that
    contains every engine mode the contact is *not* blocked from:

    * ``cold_call``  — True if the phone matches a lead in the cold funnel.
    * ``active_cs``  — True if the phone has an active CS conversation.
    * ``active_warmcall`` — True if the phone has an active warmcall conversation.
    * ``safe_for``   — List of ``["cs", "warmcall", "cold"]`` minus blocked
      modes.  A contact in the cold funnel is only safe for ``"cold"``.  A
      contact with an active CS conversation is blocked from CS (but can
      still receive warmcall or cold).
    """
    init_db()
    conn = _connect()
    try:
        cold_call = _is_cold_lead(contact_phone, conn)
        active_cs = _has_active_conversation(contact_phone, "cs", conn)
        active_warmcall = _has_active_conversation(contact_phone, "warmcall", conn)

        safe_for: list[str] = []
        if cold_call:
            safe_for = ["cold"]
        else:
            if not active_cs:
                safe_for.append("cs")
            if not active_warmcall:
                safe_for.append("warmcall")
            safe_for.append("cold")

        return {
            "cold_call": cold_call,
            "active_cs": active_cs,
            "active_warmcall": active_warmcall,
            "safe_for": safe_for,
        }
    finally:
        conn.close()


def run_guard_audit() -> dict:
    """Scan all active conversations and leads and report guard violations.

    A **violation** is a contact that:
      * appears in the cold-call funnel (lead.status in _COLD_FUNNEL_STAGES),
        **AND**
      * has an active conversation with ``engine_mode`` other than ``"cold"``.

    Returns::

        {
            "violations": [
                {
                    "contact_phone": "628...",
                    "lead_status": "contacted",
                    "conversation_engine_mode": "cs",
                    "conversation_id": 42,
                }
            ],
            "total_checked": <int>,
            "clean": <bool>,
        }
    """
    init_db()
    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in _COLD_FUNNEL_STAGES)
        cold_leads = conn.execute(
            f"SELECT phone, internationalPhoneNumber, status FROM leads "
            f"WHERE status IN ({placeholders})",
            tuple(_COLD_FUNNEL_STAGES),
        ).fetchall()

        cold_phone_map: dict[str, str] = {}
        for row in cold_leads:
            for col in ("phone", "internationalPhoneNumber"):
                raw = row[col] or ""
                digits = _normalize_phone(raw)
                if digits:
                    cold_phone_map[digits] = row["status"]

        active_convos = conn.execute(
            "SELECT id, contact_phone, engine_mode FROM conversations "
            "WHERE status = 'active' AND engine_mode != 'cold'"
        ).fetchall()

        violations: list[dict] = []
        checked_phones: set[str] = set()

        for convo in active_convos:
            convo_digits = _normalize_phone(convo["contact_phone"])
            if not convo_digits:
                continue
            checked_phones.add(convo_digits)
            for cold_digits, lead_status in cold_phone_map.items():
                if cold_digits.endswith(convo_digits) or convo_digits.endswith(
                    cold_digits
                ):
                    violations.append(
                        {
                            "contact_phone": convo["contact_phone"],
                            "lead_status": lead_status,
                            "conversation_engine_mode": convo["engine_mode"],
                            "conversation_id": convo["id"],
                        }
                    )
                    break

        total_checked = len(checked_phones) + len(cold_phone_map)

        return {
            "violations": violations,
            "total_checked": total_checked,
            "clean": len(violations) == 0,
        }
    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Cross-contamination guard checker for 1ai-engage."
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Scan all active conversations + leads and report violations.",
    )
    parser.add_argument(
        "--check",
        metavar="PHONE",
        type=str,
        help="Check guard status for a single contact phone number.",
    )
    args = parser.parse_args()

    if not args.audit and not args.check:
        parser.print_help()
        sys.exit(1)

    if args.audit:
        result = run_guard_audit()
        print(json.dumps(result, indent=2))

    if args.check:
        result = check_guard(args.check)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
