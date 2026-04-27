import logging
import os
import smtplib
import subprocess
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from config import (
    GMAIL_ACCOUNT,
    GMAIL_KEYRING_PASSWORD,
    LOGS_DIR,
    WAHA_URL,
    WAHA_DIRECT_URL,
    WAHA_API_KEY,
    WAHA_DIRECT_API_KEY,
    WAHA_SESSION,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM,
    BREVO_API_KEY,
)
from utils import is_empty

_wa_logger = logging.getLogger("waha")
_email_logger = logging.getLogger("email")

try:
    import requests as _req

    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

# ---------------------------------------------------------------------------
# Multi-channel (Instagram / Twitter) integration
# ---------------------------------------------------------------------------
# The channel senders live in src/ but pipeline scripts import from scripts/.
# We lazily bridge them here so scripts/senders.py can route to IG/Twitter too.

_CHANNELS_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "channels")


def _channel_enabled(channel: str, wa_number_id: str) -> bool:
    """Check if a channel is enabled for a given WA number."""
    import json as _json
    cfg_path = os.path.join(_CHANNELS_ROOT, channel, wa_number_id, "config.json")
    if not os.path.exists(cfg_path):
        return False
    try:
        cfg = _json.loads(open(cfg_path).read())
        return cfg.get("enabled", False) and bool(cfg.get("cookies"))
    except Exception:
        return False


def send_instagram(username: str, message: str, wa_number_id: str = "default") -> bool:
    """Send an Instagram DM via instagrapi (cookie-based auth).

    Requires the Instagram channel to be enabled and cookies configured
    through the dashboard /api/v1/channels endpoint.
    """
    if not _channel_enabled("instagram", wa_number_id):
        print(f"Skip Instagram: channel not enabled/configured for {wa_number_id}")
        return False
    try:
        src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from oneai_reach.infrastructure.messaging.channels.instagram_sender import InstagramSender
        sender = InstagramSender(wa_number_id)
        ok = sender.send(username, message)
        if ok:
            print(f"✅ Instagram DM sent to @{username}")
        else:
            print(f"❌ Instagram DM failed for @{username}")
        return ok
    except ImportError:
        print("❌ instagrapi not installed. Run: pip install instagrapi")
        return False
    except Exception as e:
        print(f"❌ Instagram send error: {e}")
        return False


def send_twitter(username: str, message: str, wa_number_id: str = "default") -> bool:
    """Send a Twitter/X DM via tweety-ns (cookie-based auth).

    Requires the Twitter channel to be enabled and cookies configured
    through the dashboard /api/v1/channels endpoint.
    """
    if not _channel_enabled("twitter", wa_number_id):
        print(f"Skip Twitter: channel not enabled/configured for {wa_number_id}")
        return False
    try:
        src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from oneai_reach.infrastructure.messaging.channels.twitter_sender import TwitterSender
        sender = TwitterSender(wa_number_id)
        ok = sender.send(username, message)
        if ok:
            print(f"✅ Twitter DM sent to @{username}")
        else:
            print(f"❌ Twitter DM failed for @{username}")
        return ok
    except ImportError:
        print("❌ tweety-ns not installed. Run: pip install tweety-ns")
        return False
    except Exception as e:
        print(f"❌ Twitter send error: {e}")
        return False

EMAIL_QUEUE_LOG = str(LOGS_DIR / "email_queue.log")


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
        targets.append(
            (
                name,
                url,
                {"X-Api-Key": key, "Content-Type": "application/json"},
            )
        )
    return targets


def _waha_sessions(base_url: str, headers: dict[str, str]) -> list[str]:
    sessions = [WAHA_SESSION]
    if not _HTTP_OK:
        return sessions
    try:
        r = _req.get(
            f"{base_url}/api/sessions",
            params={"all": "true"},
            headers={k: v for k, v in headers.items() if k != "Content-Type"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                for item in data:
                    name = str(item.get("name") or "").strip()
                    status = str(item.get("status") or "").upper()
                    if name and status == "WORKING" and name not in sessions:
                        sessions.append(name)
    except Exception:
        pass
    return sessions


def _normalize_phone(phone: str) -> str:
    """Normalize phone to clean digits starting with 62."""
    clean = "".join(filter(str.isdigit, str(phone)))
    if not clean.startswith("62"):
        clean = "62" + clean.lstrip("0")
    return clean


def _phone_to_chat_id(phone: str) -> str:
    """Convert phone to WAHA chat ID format."""
    return f"{_normalize_phone(phone)}@c.us"


def _send_wa_waha(phone: str, message: str, session_name: str = None) -> bool:
    """Primary: send WhatsApp via WAHA HTTP API.

    If *session_name* is given, tries that session first. If the preferred
    session fails on all targets, falls back to iterating all working sessions.
    """
    if not _HTTP_OK:
        return False
    clean = _normalize_phone(phone)
    chat_id = _phone_to_chat_id(phone)

    if session_name is not None:
        # Try preferred session first on all targets
        # Prefer WAHA_URL (PLUS tier supports multiple sessions) over WAHA_DIRECT (CORE tier)
        targets_to_try = [
            ("WAHA", WAHA_URL, WAHA_API_KEY),
            ("WAHA_DIRECT", WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY),
        ]

        for target_name, base_url, api_key in targets_to_try:
            url = str(base_url or "").rstrip("/")
            key = str(api_key or "")
            if not url:
                continue
            headers = {"X-Api-Key": key, "Content-Type": "application/json"}
            try:
                r = _req.post(
                    f"{url}/api/sendText",
                    json={"chatId": chat_id, "text": message, "session": session_name},
                    headers=headers,
                    timeout=15,
                )
                if r.status_code < 300:
                    print(f"✅ WA sent via {target_name} ({session_name}) to {clean}")
                    _wa_logger.info(f"SEND OK target={target_name} session={session_name} to={clean} len={len(message)}")
                    return True
                # Session FAILED or other error — try next target
                print(
                    f"⚠️ {target_name} ({session_name}) error {r.status_code}: "
                    f"{r.text[:200]}, falling back to other sessions",
                    file=sys.stderr,
                )
                _wa_logger.warning(f"SEND FAIL target={target_name} session={session_name} to={clean} status={r.status_code} body={r.text[:100]}")
            except Exception as e:
                print(f"❌ {target_name} ({session_name}) failed: {e}", file=sys.stderr)
                _wa_logger.error(f"SEND ERROR target={target_name} session={session_name} to={clean} err={e}")

    for target_name, base_url, headers in _waha_targets():
        for sess in _waha_sessions(base_url, headers):
            try:
                r = _req.post(
                    f"{base_url}/api/sendText",
                    json={
                        "chatId": chat_id,
                        "text": message,
                        "session": sess,
                    },
                    headers=headers,
                    timeout=15,
                )
                if r.status_code < 300:
                    print(f"✅ WA sent via {target_name} ({sess}) to {clean}")
                    return True
                print(
                    f"❌ {target_name} ({sess}) error {r.status_code}: {r.text[:200]}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(f"❌ {target_name} ({sess}) failed: {e}", file=sys.stderr)
    return False


def _send_wa_wacli(phone: str, message: str) -> bool:
    """Fallback: send WhatsApp via wacli CLI."""
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    try:
        result = subprocess.run(
            ["wacli", "send", "text", "--to", clean_phone, "--message", message],
            capture_output=True,
            text=True,
        )
        if "not authenticated" in result.stderr:
            print("WA Error: wacli not authenticated. Run 'wacli auth'.")
            return False
        if result.returncode == 0:
            print(f"✅ WA sent via wacli to {clean_phone}")
            return True
        print(f"❌ wacli error: {result.stderr}", file=sys.stderr)
    except FileNotFoundError:
        print("❌ wacli not found.", file=sys.stderr)
    return False


def send_whatsapp(phone: str, message: str, session_name: str = None) -> bool:
    if is_empty(phone):
        print("Skip WA: No phone number.")
        return False
    # Try WAHA first (HTTP API), fall back to wacli
    for name, fn in [
        ("WAHA", lambda: _send_wa_waha(phone, message, session_name)),
        ("wacli", lambda: _send_wa_wacli(phone, message)),
    ]:
        try:
            if fn():
                return True
        except Exception as e:
            print(f"WA method {name} failed: {e}", file=sys.stderr)
    print(f"❌ All WA methods failed for {phone}")
    return False


def send_whatsapp_session(phone: str, message: str, session_name: str) -> bool:
    """Send WhatsApp message through a specific WAHA session.

    Accepts phone in various formats: 628xxx, 628xxx@c.us, or XXXX@lid
    Preserves @lid format as-is (from WAHA webhook), converts others to @c.us
    """
    if is_empty(phone):
        print("Skip WA: No phone number.")
        return False

    # Check if it's already in LID format (from WAHA webhook)
    if "@lid" in phone:
        chat_id = phone
        clean = phone.replace("@lid", "")
    else:
        # Normal phone format - convert to @c.us
        chat_id = _phone_to_chat_id(phone)
        clean = _normalize_phone(phone)

    return _send_wa_waha_raw(chat_id, message, session_name, clean)


def _send_wa_waha_raw(
    chat_id: str, message: str, session_name: str, clean_phone: str
) -> bool:
    if not _HTTP_OK:
        return False

    if session_name is not None:
        targets_to_try = [
            ("WAHA", WAHA_URL, WAHA_API_KEY),
            ("WAHA_DIRECT", WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY),
        ]

        for target_name, base_url, api_key in targets_to_try:
            url = str(base_url or "").rstrip("/")
            key = str(api_key or "")
            if not url:
                continue
            headers = {"X-Api-Key": key, "Content-Type": "application/json"}
            try:
                r = _req.post(
                    f"{url}/api/sendText",
                    json={"chatId": chat_id, "text": message, "session": session_name},
                    headers=headers,
                    timeout=15,
                )
                if r.status_code < 300:
                    print(f"✅ WA sent via {target_name} to {clean_phone or chat_id}")
                    return True
                print(
                    f"⚠️ {target_name} ({session_name}) error {r.status_code}: "
                    f"{r.text[:200]}, falling back to other sessions",
                    file=sys.stderr,
                )
            except Exception as e:
                print(f"❌ {target_name} failed: {e}", file=sys.stderr)

    for target_name, base_url, headers in _waha_targets():
        for sess in _waha_sessions(base_url, headers):
            try:
                r = _req.post(
                    f"{base_url}/api/sendText",
                    json={"chatId": chat_id, "text": message, "session": sess},
                    headers=headers,
                    timeout=15,
                )
                if r.status_code < 300:
                    print(
                        f"✅ WA sent via {target_name} ({sess}) to {clean_phone or chat_id}"
                    )
                    return True
            except Exception:
                pass
    return False


def send_typing_indicator(session_name: str, chat_id: str, typing: bool = True) -> bool:
    """Start or stop typing indicator via WAHA API.

    *chat_id* must already be in WAHA format (e.g. ``628xxx@c.us``).
    """
    if not _HTTP_OK:
        return False
    url = str(WAHA_DIRECT_URL or "").rstrip("/")
    if not url:
        return False
    endpoint = "startTyping" if typing else "stopTyping"
    headers = {
        "X-Api-Key": str(WAHA_DIRECT_API_KEY or ""),
        "Content-Type": "application/json",
    }
    try:
        r = _req.post(
            f"{url}/api/{endpoint}",
            json={"chatId": chat_id, "session": session_name},
            headers=headers,
            timeout=10,
        )
        return r.status_code < 300
    except Exception:
        return False


def send_seen(session_name: str, chat_id: str) -> bool:
    """Mark a chat as seen (read receipt) via WAHA API.

    *chat_id* must already be in WAHA format (e.g. ``628xxx@c.us``).
    """
    if not _HTTP_OK:
        return False
    url = str(WAHA_DIRECT_URL or "").rstrip("/")
    if not url:
        return False
    headers = {
        "X-Api-Key": str(WAHA_DIRECT_API_KEY or ""),
        "Content-Type": "application/json",
    }
    try:
        r = _req.post(
            f"{url}/api/sendSeen",
            json={"chatId": chat_id, "session": session_name},
            headers=headers,
            timeout=10,
        )
        return r.status_code < 300
    except Exception:
        return False


LOGO_URL = "https://raw.githubusercontent.com/oyi77/1ai-reach/master/assets/logo.svg"


def _make_html_body(body: str) -> str:
    """Wrap plain text body in a branded HTML email template."""
    paragraphs = "".join(
        f"<p>{line if line.strip() else '&nbsp;'}</p>" for line in body.split("\n")
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <!-- Header -->
        <tr><td style="background:#1a7a4a;padding:28px;text-align:center;">
          <img src="{LOGO_URL}" width="72" height="72" alt="BerkahKarya" style="border-radius:50%;display:block;margin:0 auto 12px;">
          <span style="color:#ffffff;font-size:20px;font-weight:bold;letter-spacing:1px;">BerkahKarya</span>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:36px 40px;color:#333333;font-size:15px;line-height:1.7;">
          {paragraphs}
        </td></tr>
        <!-- Footer -->
        <tr><td style="background:#f4f6f8;padding:20px;text-align:center;font-size:12px;color:#888888;">
          &copy; 2026 BerkahKarya &bull; marketing@berkahkarya.org<br>
          <span style="font-size:11px;">Jika Anda tidak ingin menerima email ini, balas dengan kata "berhenti".</span>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _send_via_brevo(email: str, subject: str, body: str, pdf_bytes: Optional[bytes] = None, filename: Optional[str] = None) -> bool:
    """Primary: send via Brevo HTTP API (trusted IP, 300/day free)."""
    import base64
    from email.utils import parseaddr

    print(f"Attempting email via Brevo to {email}...")
    if not _HTTP_OK:
        print("❌ Brevo: requests not available")
        return False
    try:
        _, from_email = parseaddr(SMTP_FROM)
        from_name = (
            SMTP_FROM.split("<")[0].strip() if "<" in SMTP_FROM else "BerkahKarya"
        )

        msg_payload = {
            "sender": {"name": from_name, "email": from_email},
            "to": [{"email": email}],
            "subject": subject,
            "textContent": body,
            "htmlContent": _make_html_body(body),
        }

        if pdf_bytes and filename:
            msg_payload["attachment"] = [
                {"name": filename, "content": base64.b64encode(pdf_bytes).decode("utf-8")}
            ]

        resp = _req.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            json=msg_payload,
            timeout=30,
        )
        if resp.status_code in (200, 201) or "messageId" in resp.text:
            print(f"✅ Email sent via Brevo to {email}")
            return True
        print(f"❌ Brevo error {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"❌ Brevo failed: {e}")
        return False


def _send_via_stalwart(email: str, subject: str, body: str, pdf_bytes: Optional[bytes] = None, filename: Optional[str] = None) -> bool:
    """Fallback: send via Stalwart SMTP as marketing@berkahkarya.org."""
    from email.mime.base import MIMEBase
    from email import encoders
    from email.utils import parseaddr

    print(f"Attempting email via Stalwart SMTP to {email}...")
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_FROM
        msg["To"] = email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(_make_html_body(body), "html", "utf-8"))

        if pdf_bytes and filename:
            part = MIMEBase("application", "pdf")
            part.set_payload(pdf_bytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)

        _, mail_from = parseaddr(SMTP_FROM)
        mail_from = mail_from or SMTP_USER
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(mail_from, [email], msg.as_string())
        print(f"✅ Email sent via Stalwart to {email}")
        return True
    except Exception as e:
        print(f"❌ Stalwart SMTP failed: {e}")
        return False


def _send_via_gog(email: str, subject: str, body: str) -> bool:
    """Primary: send via gog Gmail CLI (free)."""
    print(f"Attempting email via gog to {email}...")
    env = {
        **os.environ,
        "GOG_KEYRING_PASSWORD": GMAIL_KEYRING_PASSWORD,
        "GOG_ACCOUNT": GMAIL_ACCOUNT,
    }
    try:
        result = subprocess.run(
            [
                "gog",
                "gmail",
                "send",
                "--to",
                email,
                "--subject",
                subject,
                "--body",
                body,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode == 0:
            print(f"✅ Email sent via gog to {email}")
            return True
        print(f"❌ Gog error: {result.stderr.strip()}")
        return False
    except Exception as e:
        print(f"❌ Gog failed: {e}")
        return False


def _send_via_himalaya(email: str, subject: str, body: str) -> bool:
    """Fallback: send via himalaya IMAP/SMTP (free)."""
    print(f"Attempting email via himalaya to {email}...")
    template = f"To: {email}\nSubject: {subject}\n\n{body}"
    try:
        result = subprocess.run(
            ["himalaya", "template", "send"],
            input=template,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"✅ Email sent via himalaya to {email}")
            return True
        print(f"❌ Himalaya error: {result.stderr.strip()}")
        return False
    except Exception as e:
        print(f"❌ Himalaya failed: {e}")
        return False


def _send_via_mock(email: str, subject: str, body: str, pdf_bytes: Optional[bytes] = None, filename: Optional[str] = None) -> bool:
    """Last resort: queue email locally for manual review (free, no send)."""
    print(f"[QUEUE] Email logged for {email} — review at {EMAIL_QUEUE_LOG}")
    os.makedirs(os.path.dirname(EMAIL_QUEUE_LOG), exist_ok=True)
    with open(EMAIL_QUEUE_LOG, "a") as f:
        f.write(f"\n---\nTo: {email}\nSubject: {subject}\nBody: {body}\n")
        if pdf_bytes and filename:
            attachment_dir = Path(EMAIL_QUEUE_LOG).parent / "email_attachments"
            attachment_dir.mkdir(parents=True, exist_ok=True)
            attachment_path = attachment_dir / filename
            attachment_path.write_bytes(pdf_bytes)
            f.write(f"Attachment: {attachment_path}\n")
    return not (pdf_bytes and filename)


def send_email(email: str, subject: str, body: str, pdf_bytes: Optional[bytes] = None, filename: Optional[str] = None) -> bool:
    if is_empty(email):
        print("Skip Email: No email address.")
        return False
    attachment_required = pdf_bytes is not None or filename is not None
    for name, method in [
        ("brevo", lambda: _send_via_brevo(email, subject, body, pdf_bytes, filename)),
        ("stalwart", lambda: _send_via_stalwart(email, subject, body, pdf_bytes, filename)),
        ("gog", lambda: _send_via_gog(email, subject, body)),
        ("himalaya", lambda: _send_via_himalaya(email, subject, body)),
        ("queue", lambda: _send_via_mock(email, subject, body, pdf_bytes, filename)),
    ]:
        if attachment_required and name in {"gog", "himalaya"}:
            print(f"Skip {name}: PDF attachment required but this method cannot attach files")
            continue
        try:
            if method():
                return True
        except Exception as e:
            print(f"Method {name} failed: {e}")
    print(f"❌ All email methods failed for {email}")
    return False


def send_voice_note(phone: str, audio_bytes: bytes, session_name: str, audio_format: str = "ogg") -> bool:
    """Send voice note via WAHA API.
    
    Args:
        phone: Phone number (628xxx or 628xxx@c.us)
        audio_bytes: Raw audio data (OGG/OPUS)
        session_name: WAHA session name
        audio_format: Audio format (ogg, wav, mp3)
    
    Returns:
        True if sent successfully
    """
    if not _HTTP_OK:
        return False
    
    # Normalize phone to chat_id
    if "@lid" in phone:
        chat_id = phone
        clean = phone.replace("@lid", "")
    else:
        chat_id = _phone_to_chat_id(phone)
        clean = _normalize_phone(phone)
    
    # Base64 encode audio
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    
    # Try WAHA targets
    for target_name, base_url, api_key in [
        ("WAHA", WAHA_URL, WAHA_API_KEY),
        ("WAHA_DIRECT", WAHA_DIRECT_URL, WAHA_DIRECT_API_KEY),
    ]:
        url = str(base_url or "").rstrip("/")
        key = str(api_key or "")
        if not url:
            continue
        
        headers = {"X-Api-Key": key, "Content-Type": "application/json"}
        payload = {
            "session": session_name,
            "chatId": chat_id,
            "file": {
                "mimetype": "audio/ogg; codecs=opus",
                "data": audio_b64,
            },
        }
        
        try:
            r = _req.post(
                f"{url}/api/sendVoice",
                json=payload,
                headers=headers,
                timeout=15,
            )
            if r.status_code < 300:
                print(f"✅ Voice note sent via {target_name} to {clean}")
                return True
            print(f"❌ {target_name} error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"❌ {target_name} failed: {e}")
    
    print(f"❌ All voice send methods failed for {phone}")
    return False
