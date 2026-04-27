"""
Conversion automator: replied → meeting_booked → (won/lost).

Thin wrapper around ConverterService from application layer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.outreach import ConverterService
from oneai_reach.config.settings import get_settings
from leads import load_leads, save_leads
from senders import send_email
from utils import parse_display_name, is_empty


def process_replied_leads() -> None:
    settings = get_settings()
    service = ConverterService(settings)
    
    df = load_leads()
    if df is None:
        return

    converted = service.process_replied_leads(
        df,
        send_email_fn=send_email,
        parse_display_name_fn=parse_display_name,
        is_empty_fn=is_empty,
        save_leads_fn=save_leads,
    )

    print(f"\nConversion complete. {converted} leads sent meeting invites.")


if __name__ == "__main__":
    process_replied_leads()
