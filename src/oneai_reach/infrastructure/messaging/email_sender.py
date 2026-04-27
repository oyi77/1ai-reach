"""Email sender with fallback chain and delivery tracking.

Fallback chain: Brevo → Stalwart SMTP → gog → himalaya → queue
"""

import os
import smtplib
import subprocess
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Optional

try:
    import requests

    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

from oneai_reach.config.settings import Settings

class EmailSender:
    """Email sender with multi-provider fallback chain.

    Fallback order:
    1. Brevo HTTP API (300/day free, trusted IP)
    2. Stalwart SMTP (marketing@berkahkarya.org)
    3. gog CLI (Gmail via gog)
    4. himalaya CLI (IMAP/SMTP)
    5. Queue to file (last resort)
    """

    LOGO_URL = (
        "https://raw.githubusercontent.com/oyi77/1ai-reach/master/assets/logo.svg"
    )

    def __init__(self, settings: Settings, queue_log_path: Optional[str] = None):
        """Initialize email sender with settings.

        Args:
            settings: Application settings
            queue_log_path: Path to email queue log file (default: logs/email_queue.log)
        """
        self.settings = settings
        self.queue_log_path = queue_log_path or str(
            settings.database.logs_dir + "/email_queue.log"
        )

    def send(self, email: str, subject: str, body: str, lead_id: Optional[str] = None, pdf_bytes: Optional[bytes] = None, filename: Optional[str] = None) -> bool:
        """Send email with fallback chain.

        Args:
            email: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            lead_id: Optional lead ID for tracking
            pdf_bytes: Optional PDF attachment bytes
            filename: Optional filename for PDF attachment

        Returns:
            True if sent successfully via any method
        """
        if not email or not email.strip():
            print("Skip Email: No email address.")
            return False

        attachment_required = pdf_bytes is not None or filename is not None
        for name, method in [
            ("brevo", lambda: self._send_via_brevo(email, subject, body, lead_id, pdf_bytes, filename)),
            ("stalwart", lambda: self._send_via_stalwart(email, subject, body, pdf_bytes, filename)),
            ("gog", lambda: self._send_via_gog(email, subject, body)),
            ("himalaya", lambda: self._send_via_himalaya(email, subject, body)),
            ("queue", lambda: self._send_via_queue(email, subject, body, pdf_bytes, filename)),
        ]:
            if attachment_required and name in {"gog", "himalaya"}:
                print(f"Skip {name}: PDF attachment required but this method cannot attach files")
                continue
            try:
                if method():
                    return True
            except Exception as e:
                print(f"Email method {name} failed: {e}")

        print(f"❌ All email methods failed for {email}")
        return False

    def _make_html_body(self, body: str, lead_id: Optional[str] = None, message_id: Optional[str] = None) -> str:
        """Wrap plain text body in branded HTML email template with tracking."""
        paragraphs = "".join(
            f"<p>{line if line.strip() else '&nbsp;'}</p>" for line in body.split("\n")
        )
        
        tracking_pixel = ""
        if lead_id and message_id:
            tracking_pixel = f'<img src="https://reach.aitradepulse.com/api/v1/webhooks/track/open/{lead_id}/{message_id}" width="1" height="1" style="display:none;" alt="" />'
        
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <!-- Header -->
        <tr><td style="background:#1a7a4a;padding:28px;text-align:center;">
          <img src="{self.LOGO_URL}" width="72" height="72" alt="BerkahKarya" style="border-radius:50%;display:block;margin:0 auto 12px;">
          <span style="color:#ffffff;font-size:20px;font-weight:bold;letter-spacing:1px;">BerkahKarya</span>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:36px 40px;color:#333333;font-size:15px;line-height:1.7;">
          {paragraphs}
        </td></tr>
        <!-- Footer -->
        <tr><td style="background:#f4f6f8;padding:20px;text-align:center;font-size:12px;color:#888888;">
          © 2026 BerkahKarya. All rights reserved.
        </td></tr>
      </table>
    </td></tr>
  </table>
  {tracking_pixel}
</body></html>"""

    def _send_via_brevo(self, email: str, subject: str, body: str, lead_id: Optional[str] = None, pdf_bytes: Optional[bytes] = None, filename: Optional[str] = None) -> bool:
        """Send via Brevo HTTP API (primary method)."""
        import base64

        print(f"Attempting email via Brevo to {email}...")
        if not _HTTP_OK:
            print("❌ Brevo: requests not available")
            return False

        if not self.settings.email.brevo_api_key:
            print("❌ Brevo: API key not configured")
            return False

        try:
            _, from_email = parseaddr(self.settings.email.smtp_from)
            from_name = (
                self.settings.email.smtp_from.split("<")[0].strip()
                if "<" in self.settings.email.smtp_from
                else "BerkahKarya"
            )

            msg_payload = {
                "sender": {"name": from_name, "email": from_email},
                "to": [{"email": email}],
                "subject": subject,
                "textContent": body,
                "htmlContent": self._make_html_body(body),
            }

            if pdf_bytes and filename:
                msg_payload["attachment"] = [
                    {
                        "name": filename,
                        "content": base64.b64encode(pdf_bytes).decode("utf-8"),
                    }
                ]

            resp = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": self.settings.email.brevo_api_key,
                    "Content-Type": "application/json",
                },
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

    def _send_via_stalwart(self, email: str, subject: str, body: str, pdf_bytes: Optional[bytes] = None, filename: Optional[str] = None) -> bool:
        """Send via Stalwart SMTP (fallback method)."""
        from email.mime.base import MIMEBase
        from email import encoders

        print(f"Attempting email via Stalwart SMTP to {email}...")

        if not self.settings.email.smtp_password:
            print("❌ Stalwart: SMTP password not configured")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.settings.email.smtp_from
            msg["To"] = email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(self._make_html_body(body), "html", "utf-8"))

            if pdf_bytes and filename:
                part = MIMEBase("application", "pdf")
                part.set_payload(pdf_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

            _, mail_from = parseaddr(self.settings.email.smtp_from)
            mail_from = mail_from or self.settings.email.smtp_user

            with smtplib.SMTP(
                self.settings.email.smtp_host,
                self.settings.email.smtp_port,
                timeout=30,
            ) as server:
                server.ehlo()
                server.starttls()
                server.login(
                    self.settings.email.smtp_user, self.settings.email.smtp_password
                )
                server.sendmail(mail_from, [email], msg.as_string())

            print(f"✅ Email sent via Stalwart to {email}")
            return True

        except Exception as e:
            print(f"❌ Stalwart SMTP failed: {e}")
            return False

    def _send_via_gog(self, email: str, subject: str, body: str) -> bool:
        """Send via gog Gmail CLI (fallback method)."""
        print(f"Attempting email via gog to {email}...")

        if not self.settings.gmail.keyring_password:
            print("❌ gog: Gmail keyring password not configured")
            return False

        env = {
            **os.environ,
            "GOG_KEYRING_PASSWORD": self.settings.gmail.keyring_password,
            "GOG_ACCOUNT": self.settings.gmail.account,
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

        except FileNotFoundError:
            print("❌ gog CLI not found")
            return False
        except Exception as e:
            print(f"❌ Gog failed: {e}")
            return False

    def _send_via_himalaya(self, email: str, subject: str, body: str) -> bool:
        """Send via himalaya IMAP/SMTP CLI (fallback method)."""
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

        except FileNotFoundError:
            print("❌ himalaya CLI not found")
            return False
        except Exception as e:
            print(f"❌ Himalaya failed: {e}")
            return False

    def _send_via_queue(self, email: str, subject: str, body: str, pdf_bytes: Optional[bytes] = None, filename: Optional[str] = None) -> bool:
        """Queue email to file for manual review (last resort)."""
        print(f"[QUEUE] Email logged for {email} — review at {self.queue_log_path}")

        try:
            os.makedirs(os.path.dirname(self.queue_log_path), exist_ok=True)
            with open(self.queue_log_path, "a") as f:
                f.write(f"\n---\nTo: {email}\nSubject: {subject}\nBody: {body}\n")
                if pdf_bytes and filename:
                    attachment_dir = Path(self.queue_log_path).parent / "email_attachments"
                    attachment_dir.mkdir(parents=True, exist_ok=True)
                    attachment_path = attachment_dir / filename
                    attachment_path.write_bytes(pdf_bytes)
                    f.write(f"Attachment: {attachment_path}\n")
            return not (pdf_bytes and filename)
        except Exception as e:
            print(f"❌ Queue failed: {e}")
            return False

    def _store_message_id(self, lead_id: str, message_id: str) -> None:
        """Store message ID in database for tracking."""
        try:
            import sqlite3
            from pathlib import Path
            
            db_path = Path(self.settings.database.db_file)
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE leads SET email_message_id = ? WHERE id = ?",
                (message_id, lead_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Failed to store message ID: {e}")
