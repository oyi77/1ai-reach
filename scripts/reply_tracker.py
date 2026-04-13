"""
Reply tracker — Gmail + WAHA (WhatsApp).

Checks both Gmail inbox and WAHA WhatsApp inbox for replies from contacted leads.
Updates funnel status: contacted/followed_up → replied.
Routes inbound WhatsApp messages by engine mode (cold/cs/warmcall) based on
the ``wa_numbers`` DB table.

Methods tried in order:
  1. gog gmail search  (primary, free)
  2. WAHA API          (WhatsApp inbox — multi-session, mode-aware)
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
    WAHA_DIRECT_URL,
    WAHA_API_KEY,
    WAHA_DIRECT_API_KEY,
    WAHA_SESSION,
)
from leads import load_leads, save_leads
from state_manager import update_lead, get_wa_numbers, _connect as _db_connect
from utils import parse_display_name, is_empty, normalize_phone

# Graceful imports — cs_engine / warmcall_engine may not exist yet
try:
    from cs_engine import handle_inbound_message as _cs_handle
except Exception:  # ImportError or transitive failures
    _cs_handle = None

try:
    from warmcall_engine import process_reply as _warmcall_process
except Exception:
    _warmcall_process = None


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------


def _is_waha_msg_processed(waha_message_id: str) -> bool:
    """Return True if this WAHA message ID already exists in conversation_messages."""
    if not waha_message_id:
        return False
    conn = _db_connect()
    try:
        row = conn.execute(
            "SELECT id FROM conversation_messages WHERE waha_message_id = ?",
            (waha_message_id,),
        ).fetchone()
        return row is not None
    except Exception:
        # Table may not exist yet in older DBs — treat as not processed
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# WAHA targets & sessions
# ---------------------------------------------------------------------------


def _waha_targets() -> list[tuple[str, str, dict[str, str]]]:
    targets: list[tuple[str, str, dict[str, str]]] = []
    seen: set[tuple[str, str]] = set()
    for name, base_url, api_key in [
        ("WAHA", WAHA_URL, WAHA_API_KEY),
        ("WAHA_DIRECT", WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY),
    ]:
        url = str(base_url or "").rstrip("/")
        key = str(api_key or "")
        if not url or (url, key) in seen:
            continue
        seen.add((url, key))
        targets.append((name, url, {"X-Api-Key": key}))
    return targets


def _waha_sessions(base_url: str, headers: dict[str, str]) -> list[dict]:
    """Return WAHA sessions merged with ``wa_numbers`` DB table.

    Each entry: ``{"session_name": str, "mode": str, "wa_number_id": str | None}``

    Merge strategy:
      1. Query WAHA API for all WORKING sessions.
      2. Load ``wa_numbers`` from DB and index by ``session_name``.
      3. For every WORKING session that has a DB row, use the DB ``mode``.
      4. For WORKING sessions *without* a DB row, default to ``"cold"``.
      5. If no wa_numbers entries exist at all, fall back to the legacy
         single-session behaviour (``WAHA_SESSION``, mode ``"cold"``).
    """
    # --- 1. Collect WORKING sessions from WAHA API ---
    api_session_names: list[str] = []
    if _HTTP_OK:
        try:
            r = _req.get(
                f"{base_url}/api/sessions",
                params={"all": "true"},
                headers=headers,
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    for item in data:
                        name = str(item.get("name") or "").strip()
                        status = str(item.get("status") or "").upper()
                        if name and status == "WORKING":
                            api_session_names.append(name)
        except Exception:
            pass

    # Always include the default session as a baseline
    if WAHA_SESSION and WAHA_SESSION not in api_session_names:
        api_session_names.insert(0, WAHA_SESSION)

    # --- 2. Load wa_numbers from DB ---
    try:
        wa_rows = get_wa_numbers()
    except Exception:
        wa_rows = []

    wa_by_session: dict[str, dict] = {}
    for row in wa_rows:
        sn = row.get("session_name", "")
        if sn:
            wa_by_session[sn] = row

    # --- 3. Merge ---
    # If DB has wa_numbers entries, iterate ALL known sessions (API ∪ DB)
    if wa_by_session:
        all_session_names = list(
            dict.fromkeys(api_session_names + list(wa_by_session.keys()))
        )
        result: list[dict] = []
        for sn in all_session_names:
            db_row = wa_by_session.get(sn)
            mode = db_row["mode"] if db_row and db_row.get("mode") else "cold"
            wa_id = db_row["id"] if db_row else None
            result.append(
                {
                    "session_name": sn,
                    "mode": mode,
                    "wa_number_id": wa_id,
                }
            )
        return result

    # --- 4. Fallback: no wa_numbers in DB → legacy single/multi session as cold ---
    return [
        {"session_name": sn, "mode": "cold", "wa_number_id": None}
        for sn in api_session_names
    ]


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

    # Build map of sender emails → reply text from inbox
    inbox_replies: dict[str, str] = {}
    for m in messages:
        sender = _extract_sender_email(m)
        if sender:
            body = m.get("body", "") or m.get("snippet", "") or m.get("text", "") or ""
            inbox_replies[sender] = str(body).strip()[:2000]

    updated = 0
    for index, row in contacted.iterrows():
        lead_email = str(row.get("email") or "").strip().lower()
        if not lead_email:
            continue
        if lead_email in inbox_replies:
            name = parse_display_name(row.get("displayName"))
            reply_text = inbox_replies[lead_email]
            print(f"  📬 REPLY from {name} ({lead_email})")
            df.at[index, "status"] = "replied"
            df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
            # Store reply text in DB
            lead_id = str(row.get("id") or row.name or "")
            if lead_id and reply_text:
                try:
                    update_lead(lead_id, reply_text=reply_text)
                except Exception as e:
                    print(
                        f"  ⚠️ Failed to store reply text for {name}: {e}",
                        file=sys.stderr,
                    )
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
    """Check WAHA inbox for WhatsApp replies — routes by engine mode."""
    if not _HTTP_OK:
        return
    last_error = ""
    for target_name, base_url, headers in _waha_targets():
        sessions = _waha_sessions(base_url, headers)
        for sess_info in sessions:
            session_name = sess_info["session_name"]
            mode = sess_info["mode"]
            wa_number_id = sess_info["wa_number_id"]
            try:
                r = _req.get(
                    f"{base_url}/api/chats",
                    params={"session": session_name, "limit": 100},
                    headers=headers,
                    timeout=10,
                )
                if r.status_code != 200:
                    last_error = (
                        f"{target_name} ({session_name}) chats error {r.status_code}"
                    )
                    continue

                raw = r.json()
                chats = raw if isinstance(raw, list) else raw.get("chats", [])

                for chat in chats:
                    chat_id = str(
                        chat.get("id", {}).get("user", "") or chat.get("id", "")
                    )
                    if not chat_id:
                        continue

                    last_msg = chat.get("lastMessage") or {}
                    waha_msg_id = str(
                        last_msg.get("id", "") or chat.get("messageId", "") or ""
                    ).strip()

                    if _is_waha_msg_processed(waha_msg_id):
                        continue

                    body = str(
                        last_msg.get("body", "")
                        or chat.get("last_message", "")
                        or chat.get("body", "")
                        or ""
                    ).strip()[:2000]

                    if not body:
                        continue

                    contact_phone = chat_id
                    digits = _phone_digits(chat_id)

                    _route_waha_message(
                        mode=mode,
                        wa_number_id=wa_number_id,
                        session_name=session_name,
                        contact_phone=contact_phone,
                        digits=digits,
                        body=body,
                        waha_msg_id=waha_msg_id,
                        target_name=target_name,
                        df=df,
                        contacted=contacted,
                    )
                return
            except Exception as e:
                last_error = f"{target_name} ({session_name}) reply check error: {e}"
    if last_error:
        print(last_error, file=sys.stderr)


def _route_waha_message(
    *,
    mode: str,
    wa_number_id: str | None,
    session_name: str,
    contact_phone: str,
    digits: str,
    body: str,
    waha_msg_id: str,
    target_name: str,
    df: pd.DataFrame,
    contacted: pd.DataFrame,
) -> None:
    """Route a single inbound WAHA message to the correct engine handler."""

    if mode == "cs" and _cs_handle is not None:
        effective_wa_id = wa_number_id or session_name
        try:
            _cs_handle(effective_wa_id, contact_phone, body, session_name)
            print(
                f"  🤖 CS handled: {contact_phone} [via {target_name}/{session_name}]"
            )
        except Exception as e:
            print(
                f"  ⚠️ cs_engine error for {contact_phone}: {e}",
                file=sys.stderr,
            )
        return

    if mode == "warmcall" and _warmcall_process is not None:
        try:
            from state_manager import get_or_create_conversation as _get_conv

            effective_wa_id = wa_number_id or session_name
            conv_id = _get_conv(effective_wa_id, contact_phone, "warmcall")
            _warmcall_process(conv_id, body)
            print(
                f"  🔥 Warmcall handled: {contact_phone} [via {target_name}/{session_name}]"
            )
        except Exception as e:
            print(
                f"  ⚠️ warmcall_engine error for {contact_phone}: {e}",
                file=sys.stderr,
            )
        return

    # Default: cold-call lead matching (existing behaviour)
    _handle_cold_reply(
        digits=digits,
        body=body,
        target_name=target_name,
        session_name=session_name,
        df=df,
        contacted=contacted,
    )


def _handle_cold_reply(
    *,
    digits: str,
    body: str,
    target_name: str,
    session_name: str,
    df: pd.DataFrame,
    contacted: pd.DataFrame,
) -> None:
    """Match a WAHA reply to a contacted lead and mark as replied (cold mode)."""
    for index, row in contacted.iterrows():
        phone = str(
            row.get("internationalPhoneNumber") or row.get("phone") or ""
        ).strip()
        if not phone or is_empty(phone):
            continue
        lead_digits = _phone_digits(phone)
        if lead_digits != digits:
            continue
        if str(df.at[index, "status"]) == "replied":
            continue
        name = parse_display_name(row.get("displayName"))
        print(f"  📱 WA REPLY from {name} ({phone}) [via {target_name}/{session_name}]")
        df.at[index, "status"] = "replied"
        df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
        lead_id = str(row.get("id") or row.name or "")
        if lead_id and body:
            try:
                update_lead(lead_id, reply_text=body)
            except Exception as e:
                print(
                    f"  ⚠️ Failed to store WA reply text for {name}: {e}",
                    file=sys.stderr,
                )
        return


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
        inbox_replies: dict[str, str] = {}
        for m in messages:
            sender = m.get("from", {})
            if isinstance(sender, dict):
                addr = sender.get("addr", "").lower()
            elif isinstance(sender, str):
                addr = sender.lower()
            else:
                addr = ""
            if "@" in addr:
                body = str(
                    m.get("body", "") or m.get("text", "") or m.get("subject", "") or ""
                ).strip()[:2000]
                inbox_replies[addr] = body

        for index, row in contacted.iterrows():
            lead_email = str(row.get("email") or "").strip().lower()
            if lead_email in inbox_replies:
                name = parse_display_name(row.get("displayName"))
                reply_text = inbox_replies[lead_email]
                print(f"  📬 REPLY from {name} ({lead_email}) [via himalaya]")
                df.at[index, "status"] = "replied"
                df.at[index, "replied_at"] = datetime.now(timezone.utc).isoformat()
                lead_id = str(row.get("id") or row.name or "")
                if lead_id and reply_text:
                    try:
                        update_lead(lead_id, reply_text=reply_text)
                    except Exception as e:
                        print(
                            f"  ⚠️ Failed to store reply text for {name}: {e}",
                            file=sys.stderr,
                        )
    except Exception as e:
        print(f"Himalaya fallback error: {e}", file=sys.stderr)


track_replies = check_replies


if __name__ == "__main__":
    check_replies()
