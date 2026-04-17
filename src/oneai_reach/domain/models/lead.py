"""Lead domain model with Pydantic validation."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, HttpUrl


class LeadStatus(str, Enum):
    """Lead funnel stages."""

    NEW = "new"
    ENRICHED = "enriched"
    DRAFT_READY = "draft_ready"
    NEEDS_REVISION = "needs_revision"
    REVIEWED = "reviewed"
    CONTACTED = "contacted"
    FOLLOWED_UP = "followed_up"
    REPLIED = "replied"
    MEETING_BOOKED = "meeting_booked"
    WON = "won"
    LOST = "lost"
    COLD = "cold"
    UNSUBSCRIBED = "unsubscribed"


class Lead(BaseModel):
    """Lead entity with validation rules."""

    model_config = {"from_attributes": True}

    # Core identification
    id: str
    displayName: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    internationalPhoneNumber: Optional[str] = None

    # Location & web presence
    formattedAddress: Optional[str] = None
    websiteUri: Optional[str] = None
    linkedin: Optional[str] = None

    # Business classification
    primaryType: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None

    # Pipeline status
    status: LeadStatus = LeadStatus.NEW
    contacted_at: Optional[datetime] = None
    followup_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None

    # Research & review
    research: Optional[str] = None
    review_score: Optional[str] = None
    review_issues: Optional[str] = None
    reply_text: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("phone", "internationalPhoneNumber")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate Indonesian phone format (+62xxx)."""
        if v is None:
            return v

        # Clean the phone number
        cleaned = v.strip()
        if not cleaned:
            return None

        # Check if it starts with +62 or 62 or 0
        if cleaned.startswith("+62"):
            return cleaned
        elif cleaned.startswith("62"):
            return f"+{cleaned}"
        elif cleaned.startswith("0"):
            return f"+62{cleaned[1:]}"
        else:
            # If it doesn't match Indonesian format, return as-is
            return cleaned

    @field_validator("websiteUri", "linkedin")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL format."""
        if v is None or not v.strip():
            return None

        url = v.strip()
        # Add http:// if no scheme present
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        return url

    @property
    def is_warm(self) -> bool:
        """Check if lead is warm (replied or meeting booked)."""
        return self.status in [LeadStatus.REPLIED, LeadStatus.MEETING_BOOKED]

    @property
    def is_cold(self) -> bool:
        """Check if lead is cold or lost."""
        return self.status in [
            LeadStatus.COLD,
            LeadStatus.LOST,
            LeadStatus.UNSUBSCRIBED,
        ]

    @property
    def days_since_contact(self) -> Optional[int]:
        """Calculate days since last contact."""
        if not self.contacted_at:
            return None
        return (datetime.now() - self.contacted_at).days

    @property
    def days_since_reply(self) -> Optional[int]:
        """Calculate days since last reply."""
        if not self.replied_at:
            return None
        return (datetime.now() - self.replied_at).days

    @property
    def needs_followup(self) -> bool:
        """Check if lead needs follow-up."""
        if self.status not in [LeadStatus.CONTACTED, LeadStatus.FOLLOWED_UP]:
            return False

        if self.followup_at and datetime.now() >= self.followup_at:
            return True

        # Auto-followup after 3 days if no reply
        if self.contacted_at and not self.replied_at:
            days = self.days_since_contact
            return days is not None and days >= 3

        return False

    @property
    def is_replied(self) -> bool:
        """Check if lead has replied."""
        return self.replied_at is not None
