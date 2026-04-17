"""Message domain model with Pydantic validation."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MessageDirection(str, Enum):
    """Message direction."""

    IN = "in"  # Incoming from customer
    OUT = "out"  # Outgoing from agent


class MessageType(str, Enum):
    """Message content types."""

    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    DOCUMENT = "document"
    VIDEO = "video"
    AUDIO = "audio"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"


class Message(BaseModel):
    """Message entity for conversation threads."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[int] = None
    conversation_id: int
    waha_message_id: Optional[str] = None

    # Message content
    direction: MessageDirection
    message_text: Optional[str] = None
    message_type: MessageType = MessageType.TEXT

    # Timestamp
    timestamp: Optional[datetime] = None

    @property
    def is_incoming(self) -> bool:
        """Check if message is from customer."""
        return self.direction == MessageDirection.IN

    @property
    def is_outgoing(self) -> bool:
        """Check if message is from agent."""
        return self.direction == MessageDirection.OUT

    @property
    def is_voice(self) -> bool:
        """Check if message is voice note."""
        return self.message_type == MessageType.VOICE

    @property
    def is_media(self) -> bool:
        """Check if message contains media."""
        return self.message_type in [
            MessageType.IMAGE,
            MessageType.VIDEO,
            MessageType.AUDIO,
            MessageType.DOCUMENT,
            MessageType.VOICE,
        ]

    @property
    def age_minutes(self) -> Optional[float]:
        """Calculate message age in minutes."""
        if not self.timestamp:
            return None
        delta = datetime.now() - self.timestamp
        return delta.total_seconds() / 60
