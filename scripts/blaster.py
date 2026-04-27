"""
Blast proposals to enriched leads.

Thin wrapper around BlasterService from application layer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.outreach import BlasterService
from oneai_reach.config.settings import get_settings
from leads import load_leads, save_leads
from senders import send_email, send_whatsapp
from utils import draft_path, is_empty, parse_display_name


def blast() -> None:
    settings = get_settings()
    service = BlasterService(settings)

    df = load_leads()
    if df is None:
        return

    for col in ("status", "contacted_at"):
        if col not in df.columns:
            df[col] = None
        df[col] = df[col].astype(object)

    print(f"Found {len(df)} leads.")

    sent, skipped_cooldown, skipped_no_draft = service.blast_proposals(
        df,
        send_email_fn=send_email,
        send_whatsapp_fn=send_whatsapp,
        draft_path_fn=draft_path,
        is_empty_fn=is_empty,
        parse_display_name_fn=parse_display_name,
    )

    save_leads(df)
    print(f"\n--- Blast complete ---")
    print(f"  Sent:              {sent}")
    print(f"  Skipped (cooldown): {skipped_cooldown}")
    print(f"  Skipped (no draft): {skipped_no_draft}")


if __name__ == "__main__":
    blast()
