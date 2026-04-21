"""Product catalog domain models for multi-tenant product management."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ProductStatus(str, Enum):
    """Product lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DISCONTINUED = "discontinued"
    DRAFT = "draft"


class VisibilityStatus(str, Enum):
    """Product visibility status."""

    PUBLIC = "public"
    PRIVATE = "private"
    HIDDEN = "hidden"


class InventoryReason(str, Enum):
    """Reason for inventory adjustment."""

    PURCHASE = "purchase"
    SALE = "sale"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    DAMAGE = "damage"
    RESTOCK = "restock"


class Product(BaseModel):
    """Product entity for catalog management."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[str] = None
    wa_number_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = Field(default="general", max_length=100)

    # Pricing
    base_price_cents: int = Field(..., gt=0)
    currency: str = Field(default="IDR", max_length=3)

    # Product management
    sku: str = Field(..., min_length=1, max_length=100)
    status: ProductStatus = ProductStatus.ACTIVE
    visibility: VisibilityStatus = VisibilityStatus.PUBLIC

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("base_price_cents")
    @classmethod
    def validate_price(cls, v: int) -> int:
        """Validate price is positive."""
        if v <= 0:
            raise ValueError("Price must be greater than 0")
        return v

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        """Validate SKU format (alphanumeric, hyphens, underscores)."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("SKU must contain only alphanumeric characters, hyphens, and underscores")
        return v.upper()

    @property
    def display_price(self) -> float:
        """Get price in display format (IDR)."""
        return self.base_price_cents / 100

    @property
    def is_active(self) -> bool:
        """Check if product is active."""
        return self.status == ProductStatus.ACTIVE

    @property
    def is_visible(self) -> bool:
        """Check if product is visible to customers."""
        return self.visibility == VisibilityStatus.PUBLIC


class ProductVariant(BaseModel):
    """Product variant for different options (size, color, etc)."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[str] = None
    product_id: str
    sku: str = Field(..., min_length=1, max_length=100)
    variant_name: str = Field(..., min_length=1, max_length=255)

    # Pricing
    price_cents: int = Field(..., gt=0)

    # Physical properties
    weight_grams: Optional[int] = Field(None, ge=0)
    dimensions_json: Optional[str] = None  # JSON: {"length": 10, "width": 5, "height": 3}

    # Status
    status: ProductStatus = ProductStatus.ACTIVE

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("price_cents")
    @classmethod
    def validate_price(cls, v: int) -> int:
        """Validate price is positive."""
        if v <= 0:
            raise ValueError("Price must be greater than 0")
        return v

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        """Validate SKU format."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("SKU must contain only alphanumeric characters, hyphens, and underscores")
        return v.upper()

    @field_validator("weight_grams")
    @classmethod
    def validate_weight(cls, v: Optional[int]) -> Optional[int]:
        """Validate weight is non-negative."""
        if v is not None and v < 0:
            raise ValueError("Weight must be non-negative")
        return v

    @property
    def display_price(self) -> float:
        """Get price in display format."""
        return self.price_cents / 100

    @property
    def is_active(self) -> bool:
        """Check if variant is active."""
        return self.status == ProductStatus.ACTIVE


class Inventory(BaseModel):
    """Inventory tracking for product variants."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[str] = None
    variant_id: str

    # Stock levels
    on_hand: int = Field(default=0, ge=0)
    reserved: int = Field(default=0, ge=0)
    sold: int = Field(default=0, ge=0)

    # Reorder settings
    reorder_level: int = Field(default=10, ge=0)

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("on_hand", "reserved", "sold")
    @classmethod
    def validate_stock(cls, v: int) -> int:
        """Validate stock quantities are non-negative."""
        if v < 0:
            raise ValueError("Stock quantity must be non-negative")
        return v

    @property
    def available(self) -> int:
        """Calculate available stock (on_hand - reserved)."""
        return max(0, self.on_hand - self.reserved)

    @property
    def is_in_stock(self) -> bool:
        """Check if variant is in stock."""
        return self.available > 0

    @property
    def is_low_stock(self) -> bool:
        """Check if stock is below reorder level."""
        return self.available <= self.reorder_level

    @property
    def stock_status(self) -> str:
        """Get human-readable stock status."""
        if self.available == 0:
            return "out_of_stock"
        if self.is_low_stock:
            return "low_stock"
        return "in_stock"


class ProductOverride(BaseModel):
    """Tenant-specific product overrides (pricing, visibility)."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[str] = None
    wa_number_id: str
    product_id: str

    # Overrides
    override_price_cents: Optional[int] = Field(None, gt=0)
    override_stock_quantity: Optional[int] = Field(None, ge=0)
    is_hidden: bool = False

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("override_price_cents")
    @classmethod
    def validate_price(cls, v: Optional[int]) -> Optional[int]:
        """Validate override price is positive if set."""
        if v is not None and v <= 0:
            raise ValueError("Override price must be greater than 0")
        return v

    @field_validator("override_stock_quantity")
    @classmethod
    def validate_stock(cls, v: Optional[int]) -> Optional[int]:
        """Validate override stock is non-negative if set."""
        if v is not None and v < 0:
            raise ValueError("Override stock must be non-negative")
        return v

    @property
    def has_price_override(self) -> bool:
        """Check if price is overridden."""
        return self.override_price_cents is not None

    @property
    def has_stock_override(self) -> bool:
        """Check if stock is overridden."""
        return self.override_stock_quantity is not None

    @property
    def display_override_price(self) -> Optional[float]:
        """Get override price in display format."""
        if self.override_price_cents is None:
            return None
        return self.override_price_cents / 100


class ProductImage(BaseModel):
    """Product images for catalog display."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[str] = None
    product_id: str
    image_url: str = Field(..., min_length=1)
    alt_text: Optional[str] = Field(None, max_length=255)

    # Display settings
    display_order: int = Field(default=0, ge=0)
    is_primary: bool = False

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("image_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate image URL format."""
        if not v.startswith(("http://", "https://", "s3://", "gs://")):
            raise ValueError("Image URL must be a valid HTTP(S) or cloud storage URL")
        return v

    @property
    def is_valid_url(self) -> bool:
        """Check if image URL is valid."""
        return self.image_url.startswith(("http://", "https://", "s3://", "gs://"))


class VariantOption(BaseModel):
    """Variant options (size, color, material, etc)."""

    model_config = {"from_attributes": True}

    # Core identification
    id: Optional[str] = None
    variant_id: str
    option_name: str = Field(..., min_length=1, max_length=100)
    option_value: str = Field(..., min_length=1, max_length=255)

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("option_name")
    @classmethod
    def validate_option_name(cls, v: str) -> str:
        """Normalize option name to lowercase."""
        return v.lower().strip()

    @field_validator("option_value")
    @classmethod
    def validate_option_value(cls, v: str) -> str:
        """Normalize option value."""
        return v.strip()

    @property
    def display_name(self) -> str:
        """Get display-friendly option name."""
        return self.option_name.replace("_", " ").title()

    @property
    def full_option(self) -> str:
        """Get full option as 'name: value'."""
        return f"{self.display_name}: {self.option_value}"
