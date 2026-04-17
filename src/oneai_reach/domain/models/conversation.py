"""Conversation domain model with Pydantic validation."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ConversationStatus(str, Enum):
    """Conversation status states."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    COLD = "cold"


class EngineMode(str, Enum):
    """Conversation engine modes."""

    CS = "cs"  # Customer service
    COLD = "cold"  # Cold calling
    MANUAL = "manual"  # Manual mode


class Conversation(BaseModel):
    """Conversation entity for WhatsApp threads."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[int] = None
    wa_number_id: str
    contact_phone: str
    contact_name: Optional[str] = None
    lead_id: Optional[str] = None

    # Conversation settings
    engine_mode: EngineMode = EngineMode.CS
    status: ConversationStatus = ConversationStatus.ACTIVE
    manual_mode: bool = False
    test_mode: bool = False

    # Metrics
    last_message_at: Optional[datetime] = None
    message_count: int = 0

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        """Check if conversation is active."""
        return self.status == ConversationStatus.ACTIVE

    @property
    def is_escalated(self) -> bool:
        """Check if conversation is escalated."""
        return self.status == ConversationStatus.ESCALATED

    @property
    def hours_since_last_message(self) -> Optional[float]:
        """Calculate hours since last message."""
        if not self.last_message_at:
            return None
        delta = datetime.now() - self.last_message_at
        return delta.total_seconds() / 3600

    @property
    def is_stale(self) -> bool:
        """Check if conversation is stale (>48 hours inactive)."""
        hours = self.hours_since_last_message
        return hours is not None and hours > 48

    @property
    def is_cold_lead(self) -> bool:
        """Check if this is a cold calling conversation."""
        return self.engine_mode == EngineMode.COLD
