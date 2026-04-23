"""
Blast proposals to enriched leads.

- Skips leads already contacted within COOLDOWN_DAYS.
- Marks each lead as contacted with a timestamp after sending.
- Sends WhatsApp (wacli) + Email (senders.py chain: gog → himalaya → queue).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from leads import load_leads, save_leads
from senders import send_email, send_whatsapp
from utils import draft_path, is_empty, parse_display_name

PROPOSAL_SUBJECT = "Collaboration Proposal from BerkahKarya"
COOLDOWN_DAYS = 30  # don't re-contact the same lead within this window


def _is_recently_contacted(row: pd.Series) -> bool:
    val = row.get("contacted_at")
    if is_empty(val):
        return False
    try:
        contacted = datetime.fromisoformat(str(val)).replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - contacted < timedelta(days=COOLDOWN_DAYS)
    except Exception:
        return False


def blast() -> None:
    df = load_leads()
    if df is None:
        return

    for col in ("status", "contacted_at"):
        if col not in df.columns:
            df[col] = None
        df[col] = df[col].astype(object)

    total = len(df)
    skipped_no_draft = skipped_cooldown = sent = 0

    print(f"Found {total} leads.")

    for index, row in df.iterrows():
        name = parse_display_name(row.get("displayName"))

        # Only send leads that passed the quality review gate
        status = str(row.get("status") or "")
        if status not in ("reviewed", "new", ""):
            # Skip leads in other pipeline stages (needs_revision, contacted, replied, etc.)
            if status not in ("nan", "none"):
                skipped_cooldown += 1
                continue

        if _is_recently_contacted(row):
            print(f"[skip] {name} — contacted within last {COOLDOWN_DAYS} days.")
            skipped_cooldown += 1
            continue

        email = str(row.get("email") or "").strip()
        phone = str(
            row.get("internationalPhoneNumber") or row.get("phone") or ""
        ).strip()
        if is_empty(email):
            email = ""
        if is_empty(phone):
            phone = ""

        path = draft_path(index, name)
        if not os.path.exists(path):
            print(f"[skip] {name} — no draft at {path}.")
            skipped_no_draft += 1
            continue

        with open(path) as f:
            content = f.read()

        parts = content.split("---WHATSAPP---")
        proposal = parts[0].replace("---PROPOSAL---", "").strip()
        wa_draft = parts[1].strip() if len(parts) > 1 else proposal

        print(f"\nProcessing: {name}")
        wa_sent = False
        email_sent = False

        if phone:
            wa_sent = send_whatsapp(phone, wa_draft)

        if email:
            email_sent = send_email(email, PROPOSAL_SUBJECT, proposal)

        if wa_sent or email_sent:
            df.at[index, "status"] = "contacted"
            df.at[index, "contacted_at"] = datetime.now(timezone.utc).isoformat()
            sent += 1

    save_leads(df)
    print(f"\n--- Blast complete ---")
    print(f"  Sent:              {sent}")
    print(f"  Skipped (cooldown): {skipped_cooldown}")
    print(f"  Skipped (no draft): {skipped_no_draft}")


if __name__ == "__main__":
    blast()
