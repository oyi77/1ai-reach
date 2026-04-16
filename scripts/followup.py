"""
Automated follow-up sender.

Sends a short follow-up email to leads that:
  - Status is 'contacted' (not yet replied)
  - contacted_at was more than FOLLOWUP_DAYS ago
  - Not already followed up (status != 'followed_up')

After sending, marks status as 'followed_up' and sets followup_at timestamp.
A second follow-up at SECOND_FOLLOWUP_DAYS marks status 'cold' and stops.
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone

from leads import load_leads, save_leads
from senders import send_email
from utils import parse_display_name, is_empty
from config import REVIEWER_MODEL

FOLLOWUP_DAYS = 7  # days after first contact before follow-up
SECOND_FOLLOWUP_DAYS = 14  # days after first contact before marking cold
PROPOSAL_SUBJECT_PREFIX = "Re: Collaboration Proposal from BerkahKarya"


def _build_followup_prompt(name: str, business_type: str, is_second: bool) -> str:
    if is_second:
        return (
            f"Write a very short (3-4 sentences) final follow-up email.\n"
            f"Context: We sent a collaboration proposal to {name} ({business_type}) 2 weeks ago. No reply.\n"
            f"Sender: Vilona from BerkahKarya (AI Automation, Digital Marketing, Software Dev).\n"
            f"Tone: Warm, understanding, leave the door open. Not pushy.\n"
            f"End with: feel free to reach out anytime.\n"
            f"Output: just the email body, no subject line, no extra text."
        )
    return (
        f"Write a short (4-5 sentences) follow-up email.\n"
        f"Context: We sent a collaboration proposal to {name} ({business_type}) 1 week ago. No reply yet.\n"
        f"Sender: Vilona from BerkahKarya (AI Automation, Digital Marketing, Software Dev).\n"
        f"Tone: Friendly, helpful, not pushy. Reference AI automation as the key value.\n"
        f"Ask for a 15-minute call. Offer to share a quick case study.\n"
        f"Output: just the email body, no subject line, no extra text."
    )


def _generate_followup(name: str, business_type: str, is_second: bool = False) -> str:
    prompt = _build_followup_prompt(name, business_type, is_second)
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", REVIEWER_MODEL],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"Claude followup error: {e}", file=sys.stderr)

    # Fallback: static template (always works)
    if is_second:
        return (
            f"Hi,\n\nI wanted to follow up one last time regarding our proposal for {name}.\n"
            f"I completely understand if now isn't the right time. "
            f"Feel free to reach out whenever you're ready to explore how AI automation can help your business grow.\n\n"
            f"Wishing you all the best,\nVilona\nBerkahKarya"
        )
    return (
        f"Hi,\n\nI hope this message finds you well. I wanted to gently follow up on the proposal I sent last week "
        f"regarding AI automation and digital marketing opportunities for {name}.\n\n"
        f"Many businesses like yours have seen significant efficiency gains and cost reductions with our solutions. "
        f"Would you be open to a quick 15-minute call this week?\n\n"
        f"Best regards,\nVilona\nBerkahKarya"
    )


def _days_since(iso_str: str) -> float:
    try:
        dt = datetime.fromisoformat(str(iso_str)).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return 0


def send_followups() -> None:
    df = load_leads()
    if df is None:
        return

    for col in ("status", "contacted_at", "followup_at"):
        if col not in df.columns:
            df[col] = None
        df[col] = df[col].astype(object)

    sent = skipped = cold_marked = 0

    for index, row in df.iterrows():
        status = str(row.get("status", ""))
        email = str(row.get("email", "")).strip()
        contacted_at = str(row.get("followup_at", "") or row.get("contacted_at", ""))

        if status not in ("contacted", "followed_up"):
            continue
        if is_empty(email):
            continue
        if is_empty(contacted_at):
            continue

        name = parse_display_name(row.get("displayName"))
        business_type = str(
            row.get("type", "") or row.get("primaryType", "") or "Business"
        )
        days_since_contact = _days_since(contacted_at)

        # Mark cold after second follow-up window
        original_contacted_at = str(row.get("contacted_at", ""))
        total_days = (
            _days_since(original_contacted_at)
            if original_contacted_at
            else days_since_contact
        )

        if total_days >= SECOND_FOLLOWUP_DAYS and status == "followed_up":
            print(
                f"[cold] {name} — no reply after {total_days:.0f} days. Marking cold."
            )
            df.at[index, "status"] = "cold"
            cold_marked += 1
            continue

        if days_since_contact < FOLLOWUP_DAYS:
            skipped += 1
            continue

        is_second = status == "followed_up"
        subject_prefix = "Final Check-in" if is_second else "Following Up"
        subject = f"{subject_prefix}: Collaboration Proposal from BerkahKarya"

        print(
            f"\n[followup{'#2' if is_second else '#1'}] {name} ({days_since_contact:.0f} days since last contact)"
        )
        body = _generate_followup(name, business_type, is_second)

        success = send_email(email, subject, body)
        if success:
            df.at[index, "status"] = "followed_up"
            df.at[index, "followup_at"] = datetime.now(timezone.utc).isoformat()
            sent += 1

    save_leads(df)
    print(f"\n--- Follow-up complete ---")
    print(f"  Sent:         {sent}")
    print(f"  Skipped:      {skipped}")
    print(f"  Marked cold:  {cold_marked}")


if __name__ == "__main__":
    send_followups()
