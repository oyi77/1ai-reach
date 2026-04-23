"""
Reply tracker — Gmail + WAHA (WhatsApp).

Thin wrapper around ReplyTrackerService from application layer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oneai_reach.application.outreach import ReplyTrackerService
from oneai_reach.config.settings import get_settings
from leads import load_leads, save_leads
from state_manager import update_lead, get_wa_numbers, _connect as _db_connect
from utils import parse_display_name, is_empty, normalize_phone

try:
    from cs_engine import handle_inbound_message as _cs_handle
except Exception:
    _cs_handle = None

try:
    from warmcall_engine import process_reply as _warmcall_process
except Exception:
    _warmcall_process = None

try:
    from state_manager import get_or_create_conversation as _get_conv
except Exception:
    _get_conv = None


def check_replies() -> None:
    settings = get_settings()
    service = ReplyTrackerService(settings)
    
    df = load_leads()
    if df is None:
        return

    updated = service.check_replies(
        df,
        update_lead_fn=update_lead,
        get_wa_numbers_fn=get_wa_numbers,
        db_connect_fn=_db_connect,
        parse_display_name_fn=parse_display_name,
        is_empty_fn=is_empty,
        normalize_phone_fn=normalize_phone,
        cs_handle_fn=_cs_handle,
        warmcall_process_fn=_warmcall_process,
        get_or_create_conversation_fn=_get_conv,
    )

    save_leads(df)
    print(f"Reply check complete. {updated} new replies detected.")


track_replies = check_replies


if __name__ == "__main__":
    check_replies()
