"""Proposal domain model with Pydantic validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Proposal(BaseModel):
    """Proposal entity for lead outreach."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[int] = None
    lead_id: str

    # Proposal content
    content: str
    score: Optional[float] = Field(None, ge=0.0, le=10.0)

    # Review status
    reviewed: bool = False
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: Optional[float]) -> Optional[float]:
        """Validate score is between 0 and 10."""
        if v is None:
            return v
        if not 0.0 <= v <= 10.0:
            raise ValueError("Score must be between 0 and 10")
        return round(v, 2)

    @property
    def is_high_quality(self) -> bool:
        """Check if proposal has high quality score (>= 7.0)."""
        return self.score is not None and self.score >= 7.0

    @property
    def is_reviewed(self) -> bool:
        """Check if proposal has been reviewed."""
        return self.reviewed and self.reviewed_at is not None

    @property
    def needs_revision(self) -> bool:
        """Check if proposal needs revision (low score)."""
        return self.score is not None and self.score < 5.0

    @property
    def word_count(self) -> int:
        """Calculate word count of proposal content."""
        return len(self.content.split())

    @property
    def char_count(self) -> int:
        """Calculate character count of proposal content."""
        return len(self.content)
