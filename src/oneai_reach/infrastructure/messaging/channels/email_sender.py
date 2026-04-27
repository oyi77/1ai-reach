"""Email channel sender — wraps existing send_email chain from scripts/senders.py.

Supports Brevo → Stalwart → gog → himalaya fallback chain.
Also supports IMAP-based reply polling.
"""

import imaplib
import email
from email.header import decode_header
from typing import Optional

from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


class EmailSender:
    """Email channel wrapping existing send chain."""

    def __init__(self, channel_id: str, config: dict):
        self.channel_id = channel_id
        self.config = config
        self.from_name = config.get("from_name", "")
        self.from_email = config.get("from_email", "")

    def send(self, to_email: str, subject: str, body: str) -> bool:
        """Send email using the existing senders.py chain."""
        try:
            from oneai_reach.infrastructure.legacy.senders import send_email
            return send_email(to_email, subject, body)
        except Exception as e:
            logger.error(f"Email send failed to {to_email}: {e}")
            return False

    def test_connection(self) -> dict:
        """Test email connection — try SMTP EHLO or Brevo API check."""
        smtp_host = self.config.get("smtp_host")
        if smtp_host:
            import smtplib
            try:
                with smtplib.SMTP(smtp_host, self.config.get("smtp_port", 587)) as server:
                    server.ehlo()
                    if self.config.get("smtp_user"):
                        server.starttls()
                        server.login(self.config.get("smtp_user", ""), self.config.get("smtp_password", ""))
                    return {"success": True, "username": self.from_email}
            except Exception as e:
                return {"success": False, "error": f"SMTP test failed: {e}"}

        # Brevo API check
        brevo_key = self.config.get("brevo_api_key")
        if brevo_key:
            try:
                import requests
                resp = requests.get(
                    "https://api.brevo.com/v3/account",
                    headers={"api-key": brevo_key},
                    timeout=10,
                )
                if resp.ok:
                    data = resp.json()
                    return {"success": True, "username": data.get("email", self.from_email)}
                return {"success": False, "error": f"Brevo API returned {resp.status_code}"}
            except Exception as e:
                return {"success": False, "error": f"Brevo test failed: {e}"}

        # Fallback — just check if from_email is set
        if self.from_email:
            return {"success": True, "username": self.from_email}

        return {"success": False, "error": "No SMTP or Brevo config, and no from_email set"}

    def poll_replies(self, limit: int = 20) -> list[dict]:
        """Poll IMAP inbox for replies."""
        imap_host = self.config.get("imap_host")
        imap_user = self.config.get("imap_user")
        imap_password = self.config.get("imap_password")

        if not imap_host or not imap_user or not imap_password:
            logger.warning(f"Email channel {self.channel_id}: IMAP not configured, cannot poll replies")
            return []

        try:
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(imap_user, imap_password)
            mail.select("INBOX")

            # Search for recent emails
            _, msg_ids = mail.search(None, "UNSEEN")
            if not msg_ids[0]:
                mail.logout()
                return []

            id_list = msg_ids[0].split()[-limit:]  # Get last N
            messages = []

            for mid in reversed(id_list):
                _, msg_data = mail.fetch(mid, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])

                        # Decode subject
                        subject = ""
                        if msg["Subject"]:
                            decoded = decode_header(msg["Subject"])
                            subject = "".join(
                                part.decode(enc or "utf-8") if isinstance(part, bytes) else part
                                for part, enc in decoded
                            )

                        # Decode from
                        from_addr = msg.get("From", "")

                        # Get body text
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body = payload.decode("utf-8", errors="replace")
                                        break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")

                        messages.append({
                            "channel": "email",
                            "channel_id": self.channel_id,
                            "thread_id": msg.get("Message-ID", ""),
                            "sender_user_id": from_addr,
                            "text": body[:500],
                            "timestamp": msg.get("Date", ""),
                            "msg_id": msg.get("Message-ID", str(mid)),
                            "users": [from_addr],
                            "subject": subject,
                        })

            mail.logout()
            return messages[:limit]
        except Exception as e:
            logger.error(f"Email IMAP poll failed for {self.channel_id}: {e}")
            return []
