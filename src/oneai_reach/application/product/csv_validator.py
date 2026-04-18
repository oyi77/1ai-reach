"""CSV validation utilities for product imports with streaming support."""

import csv
import re
from io import StringIO
from typing import Generator, Optional, TypedDict

from oneai_reach.domain.models.product import (
    Inventory,
    Product,
    ProductImage,
    ProductOverride,
    ProductStatus,
    ProductVariant,
    VisibilityStatus,
)


class ValidationError(TypedDict):
    """Validation error with line number and details."""

    line_number: int
    field: str
    value: str
    error: str


class CSVValidationResult(TypedDict):
    """Result of CSV validation."""

    valid: bool
    total_rows: int
    valid_rows: int
    errors: list[ValidationError]


def validate_product_csv(
    rows: Generator[dict, None, None], chunk_size: int = 50000
) -> CSVValidationResult:
    """
    Validate product CSV rows with streaming support for large files.

    Args:
        rows: Generator of dict rows from csv.DictReader
        chunk_size: Process rows in chunks (default 50K for memory efficiency)

    Returns:
        CSVValidationResult with validation status and errors
    """
    errors: list[ValidationError] = []
    valid_rows = 0
    total_rows = 0
    seen_skus: set[str] = set()
    seen_variant_skus: set[str] = set()

    for line_number, row in enumerate(rows, start=2):  # Start at 2 (header is line 1)
        total_rows += 1

        # Determine row type
        row_type = row.get("type", "").lower().strip()

        try:
            if row_type == "product":
                _validate_product_row(row, line_number, errors, seen_skus)
                valid_rows += 1
            elif row_type == "variant":
                _validate_variant_row(row, line_number, errors, seen_variant_skus)
                valid_rows += 1
            elif row_type == "inventory":
                _validate_inventory_row(row, line_number, errors)
                valid_rows += 1
            elif row_type == "override":
                _validate_override_row(row, line_number, errors)
                valid_rows += 1
            elif row_type == "image":
                _validate_image_row(row, line_number, errors)
                valid_rows += 1
            else:
                errors.append(
                    {
                        "line_number": line_number,
                        "field": "type",
                        "value": row_type,
                        "error": f"Unknown row type. Must be one of: product, variant, inventory, override, image",
                    }
                )
        except Exception as e:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "row",
                    "value": str(row),
                    "error": f"Unexpected error: {str(e)}",
                }
            )

    return {
        "valid": len(errors) == 0,
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "errors": errors,
    }


def _validate_product_row(
    row: dict, line_number: int, errors: list[ValidationError], seen_skus: set[str]
) -> None:
    """Validate a product row."""
    required_fields = ["name", "sku", "base_price_cents", "wa_number_id"]
    _check_required_fields(row, line_number, errors, required_fields)

    # Validate name
    name = row.get("name", "").strip()
    if name and len(name) > 255:
        errors.append(
            {
                "line_number": line_number,
                "field": "name",
                "value": name,
                "error": "Name must be 255 characters or less",
            }
        )

    # Validate SKU
    sku = row.get("sku", "").strip().upper()
    if sku:
        if not _is_valid_sku(sku):
            errors.append(
                {
                    "line_number": line_number,
                    "field": "sku",
                    "value": sku,
                    "error": "SKU must contain only alphanumeric characters, hyphens, and underscores",
                }
            )
        if sku in seen_skus:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "sku",
                    "value": sku,
                    "error": "SKU must be unique across all products",
                }
            )
        else:
            seen_skus.add(sku)

    # Validate price
    price_str = row.get("base_price_cents", "").strip()
    if price_str:
        try:
            price = int(price_str)
            if price <= 0:
                errors.append(
                    {
                        "line_number": line_number,
                        "field": "base_price_cents",
                        "value": price_str,
                        "error": "Price must be greater than 0",
                    }
                )
        except ValueError:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "base_price_cents",
                    "value": price_str,
                    "error": "Price must be a valid integer (cents)",
                }
            )

    # Validate status
    status = row.get("status", "active").strip().lower()
    if status and status not in [s.value for s in ProductStatus]:
        errors.append(
            {
                "line_number": line_number,
                "field": "status",
                "value": status,
                "error": f"Status must be one of: {', '.join([s.value for s in ProductStatus])}",
            }
        )

    # Validate visibility
    visibility = row.get("visibility", "public").strip().lower()
    if visibility and visibility not in [v.value for v in VisibilityStatus]:
        errors.append(
            {
                "line_number": line_number,
                "field": "visibility",
                "value": visibility,
                "error": f"Visibility must be one of: {', '.join([v.value for v in VisibilityStatus])}",
            }
        )


def _validate_variant_row(
    row: dict, line_number: int, errors: list[ValidationError], seen_variant_skus: set[str]
) -> None:
    """Validate a product variant row."""
    required_fields = ["product_id", "sku", "variant_name", "price_cents"]
    _check_required_fields(row, line_number, errors, required_fields)

    # Validate SKU
    sku = row.get("sku", "").strip().upper()
    if sku:
        if not _is_valid_sku(sku):
            errors.append(
                {
                    "line_number": line_number,
                    "field": "sku",
                    "value": sku,
                    "error": "SKU must contain only alphanumeric characters, hyphens, and underscores",
                }
            )
        if sku in seen_variant_skus:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "sku",
                    "value": sku,
                    "error": "Variant SKU must be unique",
                }
            )
        else:
            seen_variant_skus.add(sku)

    # Validate variant_name
    variant_name = row.get("variant_name", "").strip()
    if variant_name and len(variant_name) > 255:
        errors.append(
            {
                "line_number": line_number,
                "field": "variant_name",
                "value": variant_name,
                "error": "Variant name must be 255 characters or less",
            }
        )

    # Validate price
    price_str = row.get("price_cents", "").strip()
    if price_str:
        try:
            price = int(price_str)
            if price <= 0:
                errors.append(
                    {
                        "line_number": line_number,
                        "field": "price_cents",
                        "value": price_str,
                        "error": "Price must be greater than 0",
                    }
                )
        except ValueError:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "price_cents",
                    "value": price_str,
                    "error": "Price must be a valid integer (cents)",
                }
            )

    # Validate weight (optional, but must be non-negative if provided)
    weight_str = row.get("weight_grams", "").strip()
    if weight_str:
        try:
            weight = int(weight_str)
            if weight < 0:
                errors.append(
                    {
                        "line_number": line_number,
                        "field": "weight_grams",
                        "value": weight_str,
                        "error": "Weight must be non-negative",
                    }
                )
        except ValueError:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "weight_grams",
                    "value": weight_str,
                    "error": "Weight must be a valid integer (grams)",
                }
            )

    # Validate status
    status = row.get("status", "active").strip().lower()
    if status and status not in [s.value for s in ProductStatus]:
        errors.append(
            {
                "line_number": line_number,
                "field": "status",
                "value": status,
                "error": f"Status must be one of: {', '.join([s.value for s in ProductStatus])}",
            }
        )


def _validate_inventory_row(
    row: dict, line_number: int, errors: list[ValidationError]
) -> None:
    """Validate an inventory row."""
    required_fields = ["variant_id"]
    _check_required_fields(row, line_number, errors, required_fields)

    # Validate stock quantities
    for field in ["on_hand", "reserved", "sold", "reorder_level"]:
        value_str = row.get(field, "").strip()
        if value_str:
            try:
                value = int(value_str)
                if value < 0:
                    errors.append(
                        {
                            "line_number": line_number,
                            "field": field,
                            "value": value_str,
                            "error": "Stock quantity must be non-negative",
                        }
                    )
            except ValueError:
                errors.append(
                    {
                        "line_number": line_number,
                        "field": field,
                        "value": value_str,
                        "error": f"{field} must be a valid integer",
                    }
                )


def _validate_override_row(
    row: dict, line_number: int, errors: list[ValidationError]
) -> None:
    """Validate a product override row."""
    required_fields = ["wa_number_id", "product_id"]
    _check_required_fields(row, line_number, errors, required_fields)

    # Validate override_price_cents (optional, but must be positive if provided)
    price_str = row.get("override_price_cents", "").strip()
    if price_str:
        try:
            price = int(price_str)
            if price <= 0:
                errors.append(
                    {
                        "line_number": line_number,
                        "field": "override_price_cents",
                        "value": price_str,
                        "error": "Override price must be greater than 0",
                    }
                )
        except ValueError:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "override_price_cents",
                    "value": price_str,
                    "error": "Override price must be a valid integer (cents)",
                }
            )

    # Validate override_stock_quantity (optional, but must be non-negative if provided)
    stock_str = row.get("override_stock_quantity", "").strip()
    if stock_str:
        try:
            stock = int(stock_str)
            if stock < 0:
                errors.append(
                    {
                        "line_number": line_number,
                        "field": "override_stock_quantity",
                        "value": stock_str,
                        "error": "Override stock must be non-negative",
                    }
                )
        except ValueError:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "override_stock_quantity",
                    "value": stock_str,
                    "error": "Override stock must be a valid integer",
                }
            )

    # Validate is_hidden (optional boolean)
    is_hidden_str = row.get("is_hidden", "").strip().lower()
    if is_hidden_str and is_hidden_str not in ["0", "1", "true", "false"]:
        errors.append(
            {
                "line_number": line_number,
                "field": "is_hidden",
                "value": is_hidden_str,
                "error": "is_hidden must be 0/1 or true/false",
            }
        )


def _validate_image_row(
    row: dict, line_number: int, errors: list[ValidationError]
) -> None:
    """Validate a product image row."""
    required_fields = ["product_id", "image_url"]
    _check_required_fields(row, line_number, errors, required_fields)

    # Validate image_url
    image_url = row.get("image_url", "").strip()
    if image_url:
        if not _is_valid_url(image_url):
            errors.append(
                {
                    "line_number": line_number,
                    "field": "image_url",
                    "value": image_url,
                    "error": "Image URL must start with http://, https://, s3://, or gs://",
                }
            )

    # Validate alt_text (optional, max 255 chars)
    alt_text = row.get("alt_text", "").strip()
    if alt_text and len(alt_text) > 255:
        errors.append(
            {
                "line_number": line_number,
                "field": "alt_text",
                "value": alt_text,
                "error": "Alt text must be 255 characters or less",
            }
        )

    # Validate display_order (optional, must be non-negative)
    order_str = row.get("display_order", "").strip()
    if order_str:
        try:
            order = int(order_str)
            if order < 0:
                errors.append(
                    {
                        "line_number": line_number,
                        "field": "display_order",
                        "value": order_str,
                        "error": "Display order must be non-negative",
                    }
                )
        except ValueError:
            errors.append(
                {
                    "line_number": line_number,
                    "field": "display_order",
                    "value": order_str,
                    "error": "Display order must be a valid integer",
                }
            )

    # Validate is_primary (optional boolean)
    is_primary_str = row.get("is_primary", "").strip().lower()
    if is_primary_str and is_primary_str not in ["0", "1", "true", "false"]:
        errors.append(
            {
                "line_number": line_number,
                "field": "is_primary",
                "value": is_primary_str,
                "error": "is_primary must be 0/1 or true/false",
            }
        )


def _check_required_fields(
    row: dict, line_number: int, errors: list[ValidationError], required_fields: list[str]
) -> None:
    """Check that all required fields are present and non-empty."""
    for field in required_fields:
        value = row.get(field, "").strip()
        if not value:
            errors.append(
                {
                    "line_number": line_number,
                    "field": field,
                    "value": "",
                    "error": f"Required field '{field}' is missing or empty",
                }
            )


def _is_valid_sku(sku: str) -> bool:
    """Check if SKU matches pattern: alphanumeric, hyphens, underscores only."""
    return bool(re.match(r"^[A-Z0-9\-_]+$", sku))


def _is_valid_url(url: str) -> bool:
    """Check if URL is valid (http, https, s3, gs)."""
    return url.startswith(("http://", "https://", "s3://", "gs://"))


def generate_error_report(
    errors: list[ValidationError], rows: Optional[list[dict]] = None
) -> str:
    """
    Generate a downloadable CSV error report.

    Args:
        errors: List of validation errors
        rows: Optional original rows for context (not included in report)

    Returns:
        CSV string with error details
    """
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["line_number", "field", "value", "error"],
        quoting=csv.QUOTE_MINIMAL,
    )

    writer.writeheader()
    for error in errors:
        writer.writerow(error)

    return output.getvalue()
