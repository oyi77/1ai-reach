import os
import subprocess
import sys

try:
    import requests as _req
    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import (
    GMAIL_ACCOUNT, GMAIL_KEYRING_PASSWORD, LOGS_DIR,
    WAHA_URL, WAHA_API_KEY, WAHA_SESSION,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
    BREVO_API_KEY,
)

EMAIL_QUEUE_LOG = str(LOGS_DIR / "email_queue.log")

_WAHA_HEADERS = {"X-Api-Key": WAHA_API_KEY, "Content-Type": "application/json"}


def _send_wa_waha(phone: str, message: str) -> bool:
    """Primary: send WhatsApp via WAHA HTTP API."""
    if not _HTTP_OK:
        return False
    clean = "".join(filter(str.isdigit, str(phone)))
    if not clean.startswith("62"):
        clean = "62" + clean.lstrip("0")
    chat_id = f"{clean}@c.us"
    url = f"{WAHA_URL}/api/sendText"
    try:
        r = _req.post(url, json={
            "chatId":  chat_id,
            "text":    message,
            "session": WAHA_SESSION,
        }, headers=_WAHA_HEADERS, timeout=15)
        if r.status_code < 300:
            print(f"✅ WA sent via WAHA to {clean}")
            return True
        print(f"❌ WAHA error {r.status_code}: {r.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"❌ WAHA failed: {e}", file=sys.stderr)
    return False


def _send_wa_wacli(phone: str, message: str) -> bool:
    """Fallback: send WhatsApp via wacli CLI."""
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    try:
        result = subprocess.run(
            ["wacli", "send", "text", "--to", clean_phone, "--message", message],
            capture_output=True, text=True,
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


def send_whatsapp(phone: str, message: str) -> bool:
    if not phone or str(phone).lower() in ("nan", "none", ""):
        print("Skip WA: No phone number.")
        return False
    # Try WAHA first (HTTP API), fall back to wacli
    for name, fn in [("WAHA", _send_wa_waha), ("wacli", _send_wa_wacli)]:
        try:
            if fn(phone, message):
                return True
        except Exception as e:
            print(f"WA method {name} failed: {e}", file=sys.stderr)
    print(f"❌ All WA methods failed for {phone}")
    return False


def _send_via_brevo(email: str, subject: str, body: str) -> bool:
    """Primary: send via Brevo HTTP API (trusted IP, 300/day free)."""
    from email.utils import parseaddr
    print(f"Attempting email via Brevo to {email}...")
    if not _HTTP_OK:
        print("❌ Brevo: requests not available")
        return False
    try:
        _, from_email = parseaddr(SMTP_FROM)
        from_name = SMTP_FROM.split("<")[0].strip() if "<" in SMTP_FROM else "BerkahKarya"
        resp = _req.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            json={
                "sender": {"name": from_name, "email": from_email},
                "to": [{"email": email}],
                "subject": subject,
                "textContent": body,
            },
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


def _send_via_stalwart(email: str, subject: str, body: str) -> bool:
    """Fallback: send via Stalwart SMTP as marketing@berkahkarya.org."""
    from email.utils import parseaddr
    print(f"Attempting email via Stalwart SMTP to {email}...")
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = SMTP_FROM
        msg["To"]      = email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
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
    env = {**os.environ, "GOG_KEYRING_PASSWORD": GMAIL_KEYRING_PASSWORD, "GOG_ACCOUNT": GMAIL_ACCOUNT}
    try:
        result = subprocess.run(
            ["gog", "gmail", "send", "--to", email, "--subject", subject, "--body", body],
            capture_output=True, text=True, timeout=30, env=env,
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
            input=template, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"✅ Email sent via himalaya to {email}")
            return True
        print(f"❌ Himalaya error: {result.stderr.strip()}")
        return False
    except Exception as e:
        print(f"❌ Himalaya failed: {e}")
        return False


def _send_via_mock(email: str, subject: str, body: str) -> bool:
    """Last resort: queue email locally for manual review (free, no send)."""
    print(f"[QUEUE] Email logged for {email} — review at {EMAIL_QUEUE_LOG}")
    os.makedirs(os.path.dirname(EMAIL_QUEUE_LOG), exist_ok=True)
    with open(EMAIL_QUEUE_LOG, "a") as f:
        f.write(f"\n---\nTo: {email}\nSubject: {subject}\nBody: {body}\n")
    return True


def send_email(email: str, subject: str, body: str) -> bool:
    if not email or str(email).lower() == "nan":
        print("Skip Email: No email address.")
        return False
    for name, method in [
        ("brevo",    lambda: _send_via_brevo(email, subject, body)),
        ("stalwart", lambda: _send_via_stalwart(email, subject, body)),
        ("gog",      lambda: _send_via_gog(email, subject, body)),
        ("himalaya", lambda: _send_via_himalaya(email, subject, body)),
        ("queue",    lambda: _send_via_mock(email, subject, body)),
    ]:
        try:
            if method():
                return True
        except Exception as e:
            print(f"Method {name} failed: {e}")
    print(f"❌ All email methods failed for {email}")
    return False
