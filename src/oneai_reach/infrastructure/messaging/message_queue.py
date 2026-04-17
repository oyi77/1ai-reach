"""Message queue for email rate limiting and delivery tracking.

Manages email queue with status tracking (pending, sent, failed, retry).
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class MessageQueue:
    """Message queue for email rate limiting and retry management.

    Tracks message delivery status and supports retry logic for failed messages.
    Queue is persisted to a JSON log file.
    """

    def __init__(self, log_path: str):
        """Initialize message queue with log file path.

        Args:
            log_path: Path to queue log file (JSON format)
        """
        self.log_path = Path(log_path)
        self._ensure_log_exists()

    def _ensure_log_exists(self) -> None:
        """Create log file and parent directories if they don't exist."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("[]")

    def _read_queue(self) -> List[Dict]:
        """Read all messages from queue."""
        try:
            content = self.log_path.read_text()
            if not content.strip():
                return []
            return json.loads(content)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_queue(self, messages: List[Dict]) -> None:
        """Write all messages to queue."""
        self.log_path.write_text(json.dumps(messages, indent=2))

    def add(
        self,
        message_type: str,
        recipient: str,
        subject: str = "",
        body: str = "",
        status: str = "pending",
        error: Optional[str] = None,
    ) -> int:
        """Add message to queue.

        Args:
            message_type: Type of message (email, whatsapp)
            recipient: Recipient address (email or phone)
            subject: Message subject (for email)
            body: Message body
            status: Initial status (pending, sent, failed)
            error: Error message if status is failed

        Returns:
            Message ID (index in queue)
        """
        messages = self._read_queue()

        message = {
            "id": len(messages),
            "type": message_type,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "status": status,
            "error": error,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "retry_count": 0,
        }

        messages.append(message)
        self._write_queue(messages)

        return message["id"]

    def get_pending(self) -> List[Dict]:
        """Get all pending or failed messages that need retry.

        Returns:
            List of messages with status 'pending' or 'failed'
        """
        messages = self._read_queue()
        return [m for m in messages if m.get("status") in ("pending", "failed")]

    def get_by_id(self, message_id: int) -> Optional[Dict]:
        """Get message by ID.

        Args:
            message_id: Message ID

        Returns:
            Message dict or None if not found
        """
        messages = self._read_queue()
        for msg in messages:
            if msg.get("id") == message_id:
                return msg
        return None

    def mark_sent(self, message_id: int) -> bool:
        """Mark message as sent.

        Args:
            message_id: Message ID

        Returns:
            True if message was found and updated
        """
        messages = self._read_queue()
        updated = False

        for msg in messages:
            if msg.get("id") == message_id:
                msg["status"] = "sent"
                msg["updated_at"] = datetime.utcnow().isoformat()
                updated = True
                break

        if updated:
            self._write_queue(messages)

        return updated

    def mark_failed(self, message_id: int, error: str) -> bool:
        """Mark message as failed with error.

        Args:
            message_id: Message ID
            error: Error message

        Returns:
            True if message was found and updated
        """
        messages = self._read_queue()
        updated = False

        for msg in messages:
            if msg.get("id") == message_id:
                msg["status"] = "failed"
                msg["error"] = error
                msg["updated_at"] = datetime.utcnow().isoformat()
                msg["retry_count"] = msg.get("retry_count", 0) + 1
                updated = True
                break

        if updated:
            self._write_queue(messages)

        return updated

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics.

        Returns:
            Dict with counts by status (pending, sent, failed, total)
        """
        messages = self._read_queue()

        stats = {
            "total": len(messages),
            "pending": 0,
            "sent": 0,
            "failed": 0,
        }

        for msg in messages:
            status = msg.get("status", "pending")
            if status in stats:
                stats[status] += 1

        return stats

    def clear_sent(self) -> int:
        """Remove all sent messages from queue.

        Returns:
            Number of messages removed
        """
        messages = self._read_queue()
        original_count = len(messages)

        messages = [m for m in messages if m.get("status") != "sent"]

        self._write_queue(messages)

        for i, msg in enumerate(messages):
            msg["id"] = i

        self._write_queue(messages)

        return original_count - len(messages)
