"""Knowledge base domain model with Pydantic validation."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class KnowledgeCategory(str, Enum):
    """Knowledge base entry categories."""

    FAQ = "faq"
    DOC = "doc"
    SNIPPET = "snippet"
    PRODUCT = "product"


class KnowledgeEntry(BaseModel):
    """Knowledge base entry for customer service."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[int] = None
    wa_number_id: str

    # Entry content
    category: KnowledgeCategory
    question: str
    answer: str
    content: Optional[str] = None  # Additional searchable content

    # Metadata
    tags: Optional[str] = None  # Comma-separated tags
    priority: int = Field(default=0, ge=0, le=10)

    # Product fields (optional, for PRODUCT category)
    product_id: Optional[str] = None
    sku: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None  # e.g., "USD", "IDR"
    stock_quantity: Optional[int] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: int) -> int:
        """Validate priority is between 0 and 10."""
        if not 0 <= v <= 10:
            raise ValueError("Priority must be between 0 and 10")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[str]) -> Optional[str]:
        """Normalize tags to lowercase."""
        if v is None or not v.strip():
            return None
        # Normalize: lowercase, strip whitespace
        tags = [tag.strip().lower() for tag in v.split(",") if tag.strip()]
        return ",".join(tags) if tags else None

    @property
    def is_faq(self) -> bool:
        """Check if entry is FAQ."""
        return self.category == KnowledgeCategory.FAQ

    @property
    def is_snippet(self) -> bool:
        """Check if entry is snippet."""
        return self.category == KnowledgeCategory.SNIPPET

    @property
    def is_product(self) -> bool:
        """Check if entry is product."""
        return self.category == KnowledgeCategory.PRODUCT

    @property
    def is_high_priority(self) -> bool:
        """Check if entry has high priority (>= 7)."""
        return self.priority >= 7

    @property
    def tag_list(self) -> list[str]:
        """Get tags as list."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

    @property
    def searchable_text(self) -> str:
        """Get all searchable text combined."""
        parts = [self.question, self.answer]
        if self.content:
            parts.append(self.content)
        return " ".join(parts)
