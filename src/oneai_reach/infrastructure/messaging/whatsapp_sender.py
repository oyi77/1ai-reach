"""WhatsApp sender with fallback chain and delivery tracking.

Fallback chain: WAHA HTTP API → wacli CLI
"""

import subprocess
from typing import Optional

try:
    import requests

    _HTTP_OK = True
except ImportError:
    _HTTP_OK = False

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.external.waha_client import WAHAClient


class WhatsAppSender:
    """WhatsApp sender with WAHA → wacli fallback chain.

    Fallback order:
    1. WAHA HTTP API (primary, supports multiple sessions)
    2. wacli CLI (fallback, local WhatsApp client)
    """

    def __init__(self, settings: Settings, waha_client: Optional[WAHAClient] = None):
        """Initialize WhatsApp sender with settings.

        Args:
            settings: Application settings
            waha_client: Optional WAHAClient instance (creates new if not provided)
        """
        self.settings = settings
        self.waha_client = waha_client or WAHAClient(settings)

    def send(
        self, phone: str, message: str, session_name: Optional[str] = None
    ) -> bool:
        """Send WhatsApp message with fallback chain.

        Args:
            phone: Phone number (628xxx, 628xxx@c.us, or XXXX@lid)
            message: Message text
            session_name: Optional WAHA session name (uses default if not provided)

        Returns:
            True if sent successfully via any method
        """
        if not phone or not phone.strip():
            print("Skip WA: No phone number.")
            return False

        session = session_name or self.settings.waha.session

        for name, method in [
            ("WAHA", lambda: self._send_via_waha(phone, message, session)),
            ("wacli", lambda: self._send_via_wacli(phone, message)),
        ]:
            try:
                if method():
                    return True
            except Exception as e:
                print(f"WA method {name} failed: {e}")

        print(f"❌ All WA methods failed for {phone}")
        return False

    def send_typing_indicator(
        self, phone: str, session_name: str, typing: bool = True
    ) -> bool:
        """Start or stop typing indicator via WAHA API.

        Args:
            phone: Phone number (628xxx or 628xxx@c.us)
            session_name: WAHA session name
            typing: True to start typing, False to stop

        Returns:
            True if successful
        """
        if not _HTTP_OK:
            return False

        chat_id = self._phone_to_chat_id(phone)
        endpoint = "startTyping" if typing else "stopTyping"

        try:
            response = self.waha_client._post(
                f"/api/{endpoint}",
                {"chatId": chat_id, "session": session_name},
            )
            return response.status_code < 300
        except Exception:
            return False

    def send_seen(self, phone: str, session_name: str) -> bool:
        """Mark chat as seen (read receipt) via WAHA API.

        Args:
            phone: Phone number (628xxx or 628xxx@c.us)
            session_name: WAHA session name

        Returns:
            True if successful
        """
        if not _HTTP_OK:
            return False

        chat_id = self._phone_to_chat_id(phone)

        try:
            response = self.waha_client._post(
                "/api/sendSeen",
                {"chatId": chat_id, "session": session_name},
            )
            return response.status_code < 300
        except Exception:
            return False

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone to clean digits starting with 62."""
        clean = "".join(filter(str.isdigit, str(phone)))
        if not clean.startswith("62"):
            clean = "62" + clean.lstrip("0")
        return clean

    def _phone_to_chat_id(self, phone: str) -> str:
        """Convert phone to WAHA chat ID format.

        Preserves @lid format (from WAHA webhook), converts others to @c.us
        """
        if "@lid" in phone:
            return phone
        if "@c.us" in phone:
            return phone
        return f"{self._normalize_phone(phone)}@c.us"

    def _send_via_waha(self, phone: str, message: str, session_name: str) -> bool:
        """Send via WAHA HTTP API (primary method)."""
        if not _HTTP_OK:
            return False

        chat_id = self._phone_to_chat_id(phone)
        clean = self._normalize_phone(phone)

        targets_to_try = [
            ("WAHA", self.settings.waha.url, self.settings.waha.api_key),
            (
                "WAHA_DIRECT",
                self.settings.waha.direct_url,
                self.settings.waha.direct_api_key,
            ),
        ]

        for target_name, base_url, api_key in targets_to_try:
            url = str(base_url or "").rstrip("/")
            key = str(api_key or "")
            if not url:
                continue

            headers = {"X-Api-Key": key, "Content-Type": "application/json"}

            try:
                response = requests.post(
                    f"{url}/api/sendText",
                    json={"chatId": chat_id, "text": message, "session": session_name},
                    headers=headers,
                    timeout=15,
                )

                if response.status_code < 300:
                    print(f"✅ WA sent via {target_name} ({session_name}) to {clean}")
                    return True

                print(
                    f"❌ {target_name} ({session_name}) error {response.status_code}: "
                    f"{response.text[:200]}"
                )

            except Exception as e:
                print(f"❌ {target_name} ({session_name}) failed: {e}")

        return False

    def _send_via_wacli(self, phone: str, message: str) -> bool:
        """Send via wacli CLI (fallback method)."""
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

            print(f"❌ wacli error: {result.stderr}")
            return False

        except FileNotFoundError:
            print("❌ wacli not found.")
            return False
        except Exception as e:
            print(f"❌ wacli failed: {e}")
            return False
