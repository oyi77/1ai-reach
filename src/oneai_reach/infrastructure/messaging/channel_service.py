"""Channel service — DB-backed CRUD for workspaces and channels.

Provides workspace/channel management and dispatches messaging operations
to platform-specific senders (WhatsApp, Instagram, Twitter, Telegram, Email).
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Optional

from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)

SUPPORTED_PLATFORMS = {"whatsapp", "instagram", "twitter", "telegram", "email"}
VALID_MODES = {"cs", "coldcall", "nurture", "support"}


class ChannelService:
    """DB-backed channel management service."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a row to dict, parsing JSON fields."""
        data = dict(row)
        for field in ("config", "session_data"):
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = json.loads(data[field])
                except (json.JSONDecodeError, TypeError):
                    data[field] = {}
        return data

    # ── Workspace CRUD ──────────────────────────────────────────────

    def list_workspaces(self) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM workspaces ORDER BY created_at DESC").fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_workspace(self, workspace_id: str) -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def create_workspace(self, name: str, description: str = "") -> dict:
        ws_id = name.lower().strip().replace(" ", "-")
        ws_id = "".join(c for c in ws_id if c.isalnum() or c == "-") or str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO workspaces (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (ws_id, name, description, now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def delete_workspace(self, workspace_id: str) -> bool:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM channels WHERE workspace_id = ?", (workspace_id,))
            cursor = conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Channel CRUD ────────────────────────────────────────────────

    def list_channels(
        self,
        workspace_id: Optional[str] = None,
        mode: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> list[dict]:
        conn = self._connect()
        try:
            query = "SELECT * FROM channels WHERE 1=1"
            params: list[Any] = []
            if workspace_id:
                query += " AND workspace_id = ?"
                params.append(workspace_id)
            if mode:
                query += " AND mode = ?"
                params.append(mode)
            if platform:
                query += " AND platform = ?"
                params.append(platform)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_channel(self, channel_id: str) -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def create_channel(
        self,
        workspace_id: str,
        platform: str,
        label: str,
        mode: str = "cs",
        config: Optional[dict] = None,
        username: str = "",
        phone: str = "",
    ) -> dict:
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {platform}. Supported: {SUPPORTED_PLATFORMS}")
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}. Valid: {VALID_MODES}")

        # Verify workspace exists
        ws = self.get_workspace(workspace_id)
        if not ws:
            raise ValueError(f"Workspace not found: {workspace_id}")

        ch_id = f"ch-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        config_json = json.dumps(config or {})

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO channels
                   (id, workspace_id, platform, label, mode, enabled, connected, username, phone, config, session_data, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?, ?, '{}', ?, ?)""",
                (ch_id, workspace_id, platform, label, mode, username, phone, config_json, now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (ch_id,)).fetchone()
            return self._row_to_dict(row)
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_channel(self, channel_id: str, **kwargs) -> Optional[dict]:
        """Update channel fields. Accepts: label, mode, enabled, connected, username, phone, config, session_data."""
        allowed = {"label", "mode", "enabled", "connected", "username", "phone", "config", "session_data", "last_check"}
        updates = {}
        for key, value in kwargs.items():
            if key in allowed:
                if key in ("config", "session_data") and isinstance(value, dict):
                    value = json.dumps(value)
                if key in ("enabled", "connected"):
                    value = 1 if value else 0
                updates[key] = value

        if not updates:
            return self.get_channel(channel_id)

        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [channel_id]

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"UPDATE channels SET {set_clause} WHERE id = ?", values)
            conn.commit()
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_channel(self, channel_id: str) -> bool:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Channel Operations ──────────────────────────────────────────

    def test_connection(self, channel_id: str) -> dict:
        """Test connection for a channel. Returns {success, username, error}."""
        ch = self.get_channel(channel_id)
        if not ch:
            return {"success": False, "error": "Channel not found"}

        platform = ch["platform"]
        config = ch.get("config", {})

        try:
            if platform == "instagram":
                sender = self._get_instagram_sender(channel_id, config)
                sessionid = config.get("cookies", {}).get("sessionid", "")
                return sender.test_connection(sessionid)
            elif platform == "twitter":
                sender = self._get_twitter_sender(channel_id, config)
                cookies = config.get("cookies", {})
                return sender.test_connection(
                    auth_token=cookies.get("auth_token", ""),
                    ct0=cookies.get("ct0", ""),
                    twid=cookies.get("twid", ""),
                )
            elif platform == "telegram":
                sender = self._get_telegram_sender(channel_id, config)
                return sender.test_connection()
            elif platform == "email":
                sender = self._get_email_sender(channel_id, config)
                return sender.test_connection()
            elif platform == "whatsapp":
                return {"success": True, "error": "WhatsApp uses WAHA API — check WAHA status separately"}
            else:
                return {"success": False, "error": f"Unknown platform: {platform}"}
        except Exception as e:
            logger.error(f"Connection test failed for {channel_id}: {e}")
            return {"success": False, "error": str(e)}

    def send_message(self, channel_id: str, recipient: str, message: str, subject: str = None) -> bool:
        """Send a message through a channel."""
        ch = self.get_channel(channel_id)
        if not ch:
            logger.error(f"Channel not found: {channel_id}")
            return False

        platform = ch["platform"]
        config = ch.get("config", {})

        try:
            if platform == "instagram":
                sender = self._get_instagram_sender(channel_id, config)
                return sender.send(recipient, message)
            elif platform == "twitter":
                sender = self._get_twitter_sender(channel_id, config)
                return sender.send(recipient, message)
            elif platform == "telegram":
                sender = self._get_telegram_sender(channel_id, config)
                return sender.send(recipient, message)
            elif platform == "email":
                sender = self._get_email_sender(channel_id, config)
                return sender.send(recipient, subject or "Message", message)
            elif platform == "whatsapp":
                # WhatsApp sending goes through WAHA — delegate to senders.py
                return self._send_whatsapp(ch, recipient, message)
            else:
                logger.error(f"Unknown platform: {platform}")
                return False
        except Exception as e:
            logger.error(f"Send failed via {platform}/{channel_id}: {e}")
            return False

    def get_threads(self, channel_id: str, limit: int = 20) -> list[dict]:
        """Get conversation threads from a channel."""
        ch = self.get_channel(channel_id)
        if not ch:
            return []

        platform = ch["platform"]
        config = ch.get("config", {})

        try:
            if platform == "instagram":
                sender = self._get_instagram_sender(channel_id, config)
                return sender.get_threads(limit)
            elif platform == "twitter":
                sender = self._get_twitter_sender(channel_id, config)
                return sender.get_dm_threads(limit)
            elif platform == "telegram":
                sender = self._get_telegram_sender(channel_id, config)
                return sender.get_threads(limit)
            else:
                return []
        except Exception as e:
            logger.error(f"Get threads failed for {channel_id}: {e}")
            return []

    def poll_inbound(self, channel_id: str, limit: int = 20) -> list[dict]:
        """Poll for inbound messages on a channel."""
        ch = self.get_channel(channel_id)
        if not ch:
            return []

        platform = ch["platform"]
        config = ch.get("config", {})

        try:
            if platform == "telegram":
                sender = self._get_telegram_sender(channel_id, config)
                return sender.poll_inbound(limit)
            elif platform == "email":
                sender = self._get_email_sender(channel_id, config)
                return sender.poll_replies(limit)
            else:
                return []
        except Exception as e:
            logger.error(f"Poll failed for {channel_id}: {e}")
            return []

    def poll_all_cs(self) -> list[dict]:
        """Poll all enabled CS channels."""
        channels = self.list_channels(mode="cs")
        results = []
        for ch in channels:
            if not ch.get("enabled"):
                continue
            msgs = self.poll_inbound(ch["id"])
            results.extend(msgs)
        return results

    def poll_all_coldcall(self) -> list[dict]:
        """Poll all coldcall channels for replies."""
        channels = self.list_channels(mode="coldcall")
        results = []
        for ch in channels:
            if not ch.get("enabled"):
                continue
            msgs = self.poll_inbound(ch["id"])
            results.extend(msgs)
        return results

    # ── Sender Factories ────────────────────────────────────────────

    def _get_instagram_sender(self, channel_id: str, config: dict):
        from oneai_reach.infrastructure.messaging.channels.instagram_sender import InstagramSender
        # Use from_channel_id if config has cookies (new style)
        cookies = config.get("cookies", {})
        if cookies:
            return InstagramSender.from_channel_id(channel_id, config)
        # Fallback to legacy wa_number_id-based init
        wa_number_id = config.get("wa_number_id", channel_id)
        return InstagramSender(wa_number_id)

    def _get_twitter_sender(self, channel_id: str, config: dict):
        from oneai_reach.infrastructure.messaging.channels.twitter_sender import TwitterSender
        cookies = config.get("cookies", {})
        if cookies:
            return TwitterSender.from_channel_id(channel_id, config)
        wa_number_id = config.get("wa_number_id", channel_id)
        return TwitterSender(wa_number_id)

    def _get_telegram_sender(self, channel_id: str, config: dict):
        from oneai_reach.infrastructure.messaging.channels.telegram_sender import TelegramSender
        return TelegramSender(channel_id, config)

    def _get_email_sender(self, channel_id: str, config: dict):
        from oneai_reach.infrastructure.messaging.channels.email_sender import EmailSender
        return EmailSender(channel_id, config)

    def _send_whatsapp(self, ch: dict, recipient: str, message: str) -> bool:
        """Send via WAHA API using existing senders.py chain."""
        import sys
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        scripts = os.path.join(project_root, "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        try:
            from senders import send_whatsapp
            ok = send_whatsapp(recipient, message)
            if ok:
                # Log the message to conversation for display in UI
                self._log_sent_message(ch, recipient, message)
            return ok
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            return False

    def _log_sent_message(self, ch: dict, recipient: str, message: str) -> None:
        """Log sent message to conversation for UI display."""
        try:
            from oneai_reach.application.customer_service.conversation_service import ConversationService
            from oneai_reach.config.settings import get_settings

            settings = get_settings()
            cs = ConversationService(settings.database.db_file)

            # Extract wa_number_id from channel config
            config = ch.get("config", {})
            wa_number_id = config.get("wa_number_id") or ch.get("wa_number_id") or ch.get("channel_id", "")

            conv = cs.get_or_create_conversation(
                wa_number_id=wa_number_id,
                contact_phone=recipient,
                engine_mode="manual",
            )

            if conv and conv.get("id"):
                cs.add_message(conv["id"], "out", message)
                logger.info(f"Logged sent message to conversation {conv['id']}")
        except Exception as e:
            logger.error(f"Failed to log sent message: {e}")
