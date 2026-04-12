"""
Reply tracker — Gmail + WAHA (WhatsApp).

Checks both Gmail inbox and WAHA WhatsApp inbox for replies from contacted leads.
Updates funnel status: contacted/followed_up → replied.

Methods tried in order:
  1. gog gmail search  (primary, free)
  2. WAHA API          (WhatsApp inbox)
  3. himalaya          (IMAP fallback)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

try:
    import requests as _req

    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

import pandas as pd

from config import (
    GMAIL_ACCOUNT,
    GMAIL_KEYRING_PASSWORD,
    WAHA_URL,
    WAHA_API_KEY,
    WAHA_SESSION,
)
from leads import load_leads, save_leads
from utils import parse_display_name, is_empty, normalize_phone

_WAHA_HEADERS = {"X-Api-Key": WAHA_API_KEY}


def _gog_search(query: str) -> list[dict]:
    """Search Gmail via gog CLI, returns list of thread dicts."""
    env = {
        **os.environ,
        "GOG_KEYRING_PASSWORD": GMAIL_KEYRING_PASSWORD,
        "GOG_ACCOUNT": GMAIL_ACCOUNT,
    }
    cmd = ["gog", "gmail", "search", "-j"]
    if query:
        cmd.append(query)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, env=env
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            # gog returns {"threads": [...]} or a list directly
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("threads", data.get("messages", [data]))
    except Exception as e:
        print(f"gog search failed: {e}", file=sys.stderr)
    return []


def _extract_sender_email(thread: dict) -> str:
    """Pull the From: email address from a gog thread dict."""
    val = thread.get("from", "")
    if not val:
        return ""
    # Extract email from "Name <email@domain.com>" or bare "email@domain.com"
    if "<" in val and ">" in val:
        return val.split("<")[1].rstrip(">").strip().lower()
    return val.strip().lower()


def check_replies() -> None:
    df = load_leads()
    if df is None:
        return

    for col in ("status", "replied_at"):
        if col not in df.columns:
            df[col] = None
        df[col] = df[col].astype(object)

    # Get all leads that were contacted and have email addresses
    contacted = df[
        df["status"].isin(["contacted", "followed_up"])
        & df["email"].notna()
        & ~df["email"].apply(is_empty)
    ]

    if contacted.empty:
        print("No contacted leads to check for replies.")
        return

    print(f"Checking {len(contacted)} contacted leads for replies...")

    # Search inbox for replies from external senders (not our own sent mail)
    messages = _gog_search(f"in:inbox -from:{GMAIL_ACCOUNT}")
    if not messages:
        # Fallback: search all inbox
        messages = _gog_search("in:inbox")

    if not messages:
        print("No messages found in inbox (gog search returned empty).")
        # Fallback: try himalaya
        _check_replies_himalaya(df, contacted)
        save_leads(df)
        return

    # Build set of sender emails from inbox
    inbox_senders = {_extract_sender_email(m) for m in messages}
    inbox_senders.discard("")

    updated = 0
    for index, row in contacted.iterrows():
        lead_email = str(row.get("email") or "").strip().lower()
        if not lead_email:
            continue
        if lead_email in inbox_senders:
            name = parse_display_name(row.get("displayName"))
            print(f"  📬 REPLY from {name} ({lead_email})")
            df.at[index, "status"] = "replied"
            df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
            updated += 1

    # Also check WAHA (WhatsApp) for replies by phone number
    _check_replies_waha(df, contacted)

    save_leads(df)
    print(f"Reply check complete. {updated} new replies detected.")


def _phone_digits(phone: str) -> str:
    """Return raw digits (no '+') for a phone number, normalized to 62xxx."""
    p = normalize_phone(phone)
    return p.lstrip("+") if p else ""


def _check_replies_waha(df: pd.DataFrame, contacted: pd.DataFrame) -> None:
    """Check WAHA inbox for WhatsApp replies from contacted leads."""
    if not _HTTP_OK:
        return
    try:
        # Get recent chats from WAHA
        r = _req.get(
            f"{WAHA_URL}/api/chats",
            params={"session": WAHA_SESSION, "limit": 100},
            headers=_WAHA_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            print(f"WAHA chats error {r.status_code}", file=sys.stderr)
            return

        chats = r.json() if isinstance(r.json(), list) else r.json().get("chats", [])

        # Build set of phone numbers that sent us messages
        wa_senders: set[str] = set()
        for chat in chats:
            chat_id = str(chat.get("id", {}).get("user", "") or chat.get("id", ""))
            if chat_id:
                wa_senders.add(_phone_digits(chat_id))

        for index, row in contacted.iterrows():
            phone = str(
                row.get("internationalPhoneNumber") or row.get("phone") or ""
            ).strip()
            if not phone or is_empty(phone):
                continue
            digits = _phone_digits(phone)
            if digits in wa_senders:
                name = parse_display_name(row.get("displayName"))
                if str(df.at[index, "status"]) != "replied":
                    print(f"  📱 WA REPLY from {name} ({phone}) [via WAHA]")
                    df.at[index, "status"] = "replied"
                    df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        print(f"WAHA reply check error: {e}", file=sys.stderr)


def _check_replies_himalaya(df: pd.DataFrame, contacted: pd.DataFrame) -> None:
    """Fallback: use himalaya list to check for recent messages."""
    try:
        result = subprocess.run(
            ["himalaya", "envelope", "list", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            print("Himalaya fallback also failed.", file=sys.stderr)
            return

        messages = json.loads(result.stdout)
        inbox_senders = set()
        for m in messages:
            sender = m.get("from", {})
            if isinstance(sender, dict):
                addr = sender.get("addr", "").lower()
            elif isinstance(sender, str):
                addr = sender.lower()
            else:
                addr = ""
            if "@" in addr:
                inbox_senders.add(addr)

        for index, row in contacted.iterrows():
            lead_email = str(row.get("email") or "").strip().lower()
            if lead_email in inbox_senders:
                name = parse_display_name(row.get("displayName"))
                print(f"  📬 REPLY from {name} ({lead_email}) [via himalaya]")
                df.at[index, "status"] = "replied"
                df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        print(f"Himalaya fallback error: {e}", file=sys.stderr)


if __name__ == "__main__":
    check_replies()
