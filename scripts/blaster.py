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
from senders import send_email, send_whatsapp, send_instagram, send_twitter
from utils import draft_path, is_empty, parse_display_name
from oneai_reach.application.outreach.proposal_pdf import (
    ProposalPdfError,
    generate_proposal_pdf,
    persist_proposal_pdf,
    proposal_pdf_filename,
)

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

        status = str(row.get("status") or "")
        if status not in ("reviewed", "new", ""):
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
        ig_handle = str(row.get("instagram") or "").strip().lstrip("@")
        tw_handle = str(row.get("twitter") or "").strip().lstrip("@")
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
        any_sent = blast_lead(
            phone,
            email,
            ig_handle,
            tw_handle,
            proposal,
            wa_draft,
            lead_name=name,
            lead_index=index,
        )

        if any_sent:
            df.at[index, "status"] = "contacted"
            df.at[index, "contacted_at"] = datetime.now(timezone.utc).isoformat()
            sent += 1

    save_leads(df)
    print("\n--- Blast complete ---")
    print(f"  Sent:              {sent}")
    print(f"  Skipped (cooldown): {skipped_cooldown}")
    print(f"  Skipped (no draft): {skipped_no_draft}")


def blast_lead(phone: str, email: str, ig_handle: str, tw_handle: str,
               proposal: str, wa_draft: str, lead_name: str = "Business", lead_index=None) -> bool:
    """Send proposal to a lead via all available channels."""
    wa_sent = email_sent = ig_sent = tw_sent = False

    if phone:
        wa_sent = send_whatsapp(phone, wa_draft)

    if email:
        try:
            pdf_bytes = generate_proposal_pdf(proposal, lead_name)
        except ProposalPdfError as exc:
            print(f"  [skip email] {lead_name} — {exc}")
            pdf_bytes = None
        if pdf_bytes is None:
            email_sent = False
        else:
            email_sent = send_email(
                email,
                PROPOSAL_SUBJECT,
                proposal,
                pdf_bytes=pdf_bytes,
                filename=proposal_pdf_filename(lead_name),
            )
        if email_sent and lead_index is not None and pdf_bytes:
            from config import PROPOSALS_DIR

            pdf_path = persist_proposal_pdf(pdf_bytes, PROPOSALS_DIR, lead_index, lead_name)
            print(f"  Saved proposal PDF: {pdf_path}")


    if ig_handle:
        ig_sent = send_instagram(ig_handle, wa_draft)

    if tw_handle:
        tw_sent = send_twitter(tw_handle, wa_draft)

    return wa_sent or email_sent or ig_sent or tw_sent


def blast_via_channels(phone: str, email: str, ig_handle: str, tw_handle: str,
                       proposal: str, wa_draft: str, mode: str = "coldcall") -> bool:
    """Send proposal using ChannelService mode-based channel lookup.

    Finds all enabled channels matching the given mode and sends through them.
    Falls back to direct sender calls for channels without a DB entry.
    """
    try:
        _project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(_project, "src"))
        from oneai_reach.infrastructure.messaging.channel_service import ChannelService
        db_path = os.path.join(_project, "data", "leads.db")
        svc = ChannelService(db_path)
        channels = svc.list_channels(mode=mode)
    except Exception:
        return blast_lead(phone, email, ig_handle, tw_handle, proposal, wa_draft)

    any_sent = False
    for ch in channels:
        if not ch.get("enabled"):
            continue
        platform = ch["platform"]
        ch_id = ch["id"]
        try:
            if platform == "whatsapp" and phone:
                any_sent |= svc.send_message(ch_id, phone, wa_draft)
            elif platform == "email" and email:
                any_sent |= blast_lead("", email, "", "", proposal, wa_draft)
            elif platform == "instagram" and ig_handle:
                any_sent |= svc.send_message(ch_id, ig_handle, wa_draft)
            elif platform == "twitter" and tw_handle:
                any_sent |= svc.send_message(ch_id, tw_handle, wa_draft)
            elif platform == "telegram" and (ig_handle or phone):
                any_sent |= svc.send_message(ch_id, ig_handle or phone, wa_draft)
        except Exception as e:
            print(f"  [error] {platform}/{ch_id}: {e}")

    if not any_sent:
        any_sent = blast_lead(phone, email, ig_handle, tw_handle, proposal, wa_draft)

    return any_sent


if __name__ == "__main__":
    blast()
