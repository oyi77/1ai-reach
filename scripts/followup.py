"""
Automated follow-up sender.

Thin wrapper around FollowupService from application layer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.outreach import FollowupService
from oneai_reach.config.settings import get_settings
from leads import load_leads, save_leads
from senders import send_email
from utils import parse_display_name, is_empty


def send_followups() -> None:
    settings = get_settings()
    service = FollowupService(settings)
    
    df = load_leads()
    if df is None:
        return

    sent, skipped, cold_marked = service.send_followups(
        df,
        send_email_fn=send_email,
        parse_display_name_fn=parse_display_name,
        is_empty_fn=is_empty,
        save_leads_fn=save_leads,
    )

    print(f"\n--- Follow-up complete ---")
    print(f"  Sent:         {sent}")
    print(f"  Skipped:      {skipped}")
    print(f"  Marked cold:  {cold_marked}")


if __name__ == "__main__":
    send_followups()
