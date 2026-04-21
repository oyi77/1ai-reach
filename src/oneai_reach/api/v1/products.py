"""Product CRUD API endpoints for multi-tenant product management."""

import csv
from io import StringIO
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from oneai_reach.api.dependencies import verify_api_key
from oneai_reach.application.product.csv_validator import validate_product_csv, CSVValidationResult
from oneai_reach.application.product.image_service import ImageService
from oneai_reach.config.settings import get_settings
from oneai_reach.domain.models.product import Product, ProductStatus, VisibilityStatus, ProductVariant, Inventory
from oneai_reach.domain.exceptions import ValidationError
from oneai_reach.infrastructure.database.sqlite_product_repository import (
    SQLiteProductRepository,
    NotFoundError,
    RepositoryError,
)
from oneai_reach.infrastructure.database.sqlite_product_variant_repository import (
    SQLiteProductVariantRepository,
)
from oneai_reach.infrastructure.database.sqlite_inventory_repository import (
    SQLiteInventoryRepository,
)

router = APIRouter(
    prefix="/api/v1/products",
    tags=["products"],
    dependencies=[Depends(verify_api_key)],
)


# Request/Response Schemas
class ProductCreate(BaseModel):
    """Request schema for creating a product."""

    wa_number_id: str = Field(..., min_length=1, description="WhatsApp number ID")
    name: str = Field(..., min_length=1, max_length=255, description="Product name")
    description: Optional[str] = Field(None, description="Product description")
    category: str = Field(default="general", max_length=100, description="Product category")
    base_price_cents: int = Field(..., gt=0, description="Base price in cents")
    currency: str = Field(default="IDR", max_length=3, description="Currency code")
    sku: str = Field(..., min_length=1, max_length=100, description="Stock keeping unit")
    status: ProductStatus = Field(default=ProductStatus.ACTIVE, description="Product status")
    visibility: VisibilityStatus = Field(default=VisibilityStatus.PUBLIC, description="Visibility status")


class ProductUpdate(BaseModel):
    """Request schema for updating a product."""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Product name")
    description: Optional[str] = Field(None, description="Product description")
    category: Optional[str] = Field(None, max_length=100, description="Product category")
    base_price_cents: Optional[int] = Field(None, gt=0, description="Base price in cents")
    currency: Optional[str] = Field(None, max_length=3, description="Currency code")
    sku: Optional[str] = Field(None, min_length=1, max_length=100, description="Stock keeping unit")
    status: Optional[ProductStatus] = Field(None, description="Product status")
    visibility: Optional[VisibilityStatus] = Field(None, description="Visibility status")


class ProductResponse(BaseModel):
    """Response schema for product data."""

    id: str
    wa_number_id: Optional[str] = None
    name: str
    description: Optional[str]
    category: str
    base_price_cents: int
    currency: str
    sku: str
    status: str
    visibility: str
    display_price: float
    is_active: bool
    is_visible: bool
    created_at: Optional[str]
    updated_at: Optional[str]

    @classmethod
    def from_product(cls, product: Product) -> "ProductResponse":
        """Convert Product domain model to response schema."""
        return cls(
            id=product.id or "",
            wa_number_id=product.wa_number_id,
            name=product.name,
            description=product.description,
            category=product.category,
            base_price_cents=product.base_price_cents,
            currency=product.currency,
            sku=product.sku,
            status=product.status.value,
            visibility=product.visibility.value,
            display_price=product.display_price,
            is_active=product.is_active,
            is_visible=product.is_visible,
            created_at=product.created_at.isoformat() if product.created_at else None,
            updated_at=product.updated_at.isoformat() if product.updated_at else None,
        )


def get_product_repository() -> SQLiteProductRepository:
    """Dependency injection for product repository."""
    settings = get_settings()
    return SQLiteProductRepository(db_path=settings.database.db_file)


def get_variant_repository() -> SQLiteProductVariantRepository:
    """Dependency injection for variant repository."""
    settings = get_settings()
    return SQLiteProductVariantRepository(db_path=settings.database.db_file)


def get_inventory_repository() -> SQLiteInventoryRepository:
    """Dependency injection for inventory repository."""
    settings = get_settings()
    return SQLiteInventoryRepository(db_path=settings.database.db_file)


def get_image_service() -> ImageService:
    """Dependency injection for image service."""
    return ImageService(storage_base_path="data/products")


@router.get("", response_model=List[ProductResponse])
async def list_products(
    wa_number_id: str = Query(..., description="WhatsApp number ID to filter products"),
    query: Optional[str] = Query(None, description="Search query for product name/SKU"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    repo: SQLiteProductRepository = Depends(get_product_repository),
) -> List[ProductResponse]:
    """List all products for a WA number with optional search.

    Args:
        wa_number_id: WhatsApp number ID to filter products
        query: Optional search query for product name/SKU
        limit: Maximum number of results (default: 10, max: 100)
        repo: Product repository dependency

    Returns:
        List of products matching the criteria
    """
    try:
        if query:
            products = repo.search(wa_number_id=wa_number_id, query=query, limit=limit)
        else:
            products = repo.get_all(wa_number_id=wa_number_id)
            products = products[:limit]  # Apply limit to get_all results

        return [ProductResponse.from_product(p) for p in products]

    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/search", response_model=List[ProductResponse])
async def search_products(
    q: str = Query(..., min_length=1, description="Search query for product name, description, category, or SKU"),
    wa_number_id: Optional[str] = Query(None, description="WhatsApp number ID for effective values with overrides"),
    category: Optional[str] = Query(None, description="Filter by category"),
    stock_status: Optional[str] = Query(None, description="Filter by stock status (in_stock/out_of_stock)"),
    min_price: Optional[int] = Query(None, ge=0, description="Minimum price in cents"),
    max_price: Optional[int] = Query(None, ge=0, description="Maximum price in cents"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    repo: SQLiteProductRepository = Depends(get_product_repository),
    variant_repo: SQLiteProductVariantRepository = Depends(get_variant_repository),
    inventory_repo: SQLiteInventoryRepository = Depends(get_inventory_repository),
) -> List[ProductResponse]:
    """Search products with full-text search and filters.
    
    Searches across product name, description, category, and SKU using LIKE pattern matching.
    Supports filtering by category, stock status, and price range.
    Returns effective values (with overrides) when wa_number_id is provided.
    
    Args:
        q: Search query string
        wa_number_id: Optional WA number ID to apply overrides
        category: Optional category filter
        stock_status: Optional stock status filter (in_stock/out_of_stock)
        min_price: Optional minimum price filter in cents
        max_price: Optional maximum price filter in cents
        limit: Maximum number of results (default: 10, max: 100)
        offset: Number of results to skip for pagination
        repo: Product repository dependency
        variant_repo: Variant repository dependency
        inventory_repo: Inventory repository dependency
    
    Returns:
        List of products matching search criteria with filters applied
    """
    try:
        # If wa_number_id provided, search within that tenant's products
        # Otherwise, search across all products
        if wa_number_id:
            # Use repository search with tenant context
            products = repo.search(wa_number_id=wa_number_id, query=q, limit=1000)
        else:
            # Search across all products (no tenant filter)
            # Get all products and filter by search query
            conn = repo._connect()
            try:
                search_pattern = f"%{q}%"
                cursor = conn.execute(
                    """
                    SELECT * FROM products
                    WHERE name LIKE ? OR description LIKE ? OR category LIKE ? OR sku LIKE ?
                    ORDER BY 
                        CASE 
                            WHEN name LIKE ? THEN 1
                            WHEN sku LIKE ? THEN 2
                            WHEN category LIKE ? THEN 3
                            ELSE 4
                        END,
                        created_at DESC
                    LIMIT 1000
                """,
                    (search_pattern, search_pattern, search_pattern, search_pattern,
                     search_pattern, search_pattern, search_pattern),
                )
                rows = cursor.fetchall()
                products = [repo._row_to_product(row) for row in rows]
            finally:
                conn.close()
        
        # Apply category filter
        if category:
            products = [p for p in products if p.category == category]
        
        # Apply price filters
        if min_price is not None:
            products = [p for p in products if p.base_price_cents >= min_price]
        if max_price is not None:
            products = [p for p in products if p.base_price_cents <= max_price]
        
        # Apply stock status filter
        if stock_status:
            filtered_products = []
            for product in products:
                # Get variants for this product
                variants = variant_repo.get_all(product_id=product.id)
                
                if not variants:
                    # Product without variants - always consider in_stock
                    if stock_status == "in_stock":
                        filtered_products.append(product)
                else:
                    # Check if any variant has stock
                    has_stock = False
                    for variant in variants:
                        if variant.id:
                            inventory = inventory_repo.get_by_variant(variant_id=variant.id)
                            if inventory and inventory.is_in_stock:
                                has_stock = True
                                break
                    
                    if (stock_status == "in_stock" and has_stock) or \
                       (stock_status == "out_of_stock" and not has_stock):
                        filtered_products.append(product)
            
            products = filtered_products
        
        # Apply effective values if wa_number_id provided
        if wa_number_id:
            effective_products = []
            for product in products:
                effective = repo.get_effective_product(
                    wa_number_id=wa_number_id,
                    product_id=product.id
                )
                if effective:
                    effective_products.append(effective)
            products = effective_products
        
        # Apply pagination
        products = products[offset:offset + limit]
        
        return [ProductResponse.from_product(p) for p in products]
    
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/export")
async def export_products_csv(
    wa_number_id: str = Query(..., description="WhatsApp number ID to filter products"),
    category: Optional[str] = Query(None, description="Filter by category"),
    visibility: Optional[str] = Query(None, description="Filter by visibility (public/hidden/private)"),
    product_repo: SQLiteProductRepository = Depends(get_product_repository),
    variant_repo: SQLiteProductVariantRepository = Depends(get_variant_repository),
    inventory_repo: SQLiteInventoryRepository = Depends(get_inventory_repository),
) -> StreamingResponse:
    """Export products to CSV in Shopify format.
    
    Returns one row per variant with effective values (including overrides) when wa_number_id is provided.
    Supports filtering by category and visibility.
    
    Args:
        wa_number_id: WhatsApp number ID to filter products and apply overrides
        category: Optional category filter
        visibility: Optional visibility filter (public/hidden/private)
        product_repo: Product repository dependency
        variant_repo: Variant repository dependency
        inventory_repo: Inventory repository dependency
    
    Returns:
        CSV file with products and variants
    """
    try:
        # Generate filename with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"products_export_{timestamp}.csv"
        
        # Create streaming response
        return StreamingResponse(
            _generate_csv_rows(
                wa_number_id=wa_number_id,
                category=category,
                visibility=visibility,
                product_repo=product_repo,
                variant_repo=variant_repo,
                inventory_repo=inventory_repo,
            ),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    wa_number_id: Optional[str] = Query(None, description="WA number ID for effective product with overrides"),
    repo: SQLiteProductRepository = Depends(get_product_repository),
) -> ProductResponse:
    """Get a single product by ID.

    If wa_number_id is provided, returns the effective product with tenant-specific
    overrides applied (pricing, visibility).

    Args:
        product_id: Unique product identifier
        wa_number_id: Optional WA number ID to apply overrides
        repo: Product repository dependency

    Returns:
        Product details with overrides applied if wa_number_id provided
    """
    try:
        if wa_number_id:
            product = repo.get_effective_product(wa_number_id=wa_number_id, product_id=product_id)
        else:
            product = repo.get_by_id(product_id=product_id)

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

        return ProductResponse.from_product(product)

    except HTTPException:
        raise
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("", response_model=ProductResponse, status_code=201)
async def create_product(
    product_data: ProductCreate,
    repo: SQLiteProductRepository = Depends(get_product_repository),
) -> ProductResponse:
    """Create a new product.

    Args:
        product_data: Product creation data
        repo: Product repository dependency

    Returns:
        Created product with assigned ID
    """
    try:
        # Convert request schema to domain model
        product = Product(
            wa_number_id=product_data.wa_number_id,
            name=product_data.name,
            description=product_data.description,
            category=product_data.category,
            base_price_cents=product_data.base_price_cents,
            currency=product_data.currency,
            sku=product_data.sku,
            status=product_data.status,
            visibility=product_data.visibility,
        )

        # Save to database
        saved_product = repo.save(product)

        return ProductResponse.from_product(saved_product)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    repo: SQLiteProductRepository = Depends(get_product_repository),
) -> ProductResponse:
    """Update an existing product.

    Only provided fields will be updated. Omitted fields remain unchanged.

    Args:
        product_id: Unique product identifier
        product_data: Product update data (partial)
        repo: Product repository dependency

    Returns:
        Updated product
    """
    try:
        # Get existing product
        existing_product = repo.get_by_id(product_id=product_id)
        if not existing_product:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

        # Apply updates (only non-None fields)
        update_dict = product_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(existing_product, field, value)

        # Save updated product
        updated_product = repo.update(existing_product)

        return ProductResponse.from_product(updated_product)

    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: str,
    repo: SQLiteProductRepository = Depends(get_product_repository),
) -> None:
    """Delete a product by ID.

    Cascades to related variants, inventory, and overrides.

    Args:
        product_id: Unique product identifier
        repo: Product repository dependency

    Returns:
        No content on success
    """
    try:
        deleted = repo.delete(product_id=product_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    except HTTPException:
        raise
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# Variant Schemas
class VariantCreate(BaseModel):
    """Request schema for creating a variant."""

    sku: str = Field(..., min_length=1, max_length=100, description="Variant SKU")
    variant_name: str = Field(..., min_length=1, max_length=255, description="Variant name")
    price_cents: int = Field(..., gt=0, description="Variant price in cents")
    weight_grams: Optional[int] = Field(None, ge=0, description="Weight in grams")
    dimensions_json: Optional[str] = Field(None, description="Dimensions as JSON string")
    status: ProductStatus = Field(default=ProductStatus.ACTIVE, description="Variant status")


class VariantUpdate(BaseModel):
    """Request schema for updating a variant."""

    sku: Optional[str] = Field(None, min_length=1, max_length=100, description="Variant SKU")
    variant_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Variant name")
    price_cents: Optional[int] = Field(None, gt=0, description="Variant price in cents")
    weight_grams: Optional[int] = Field(None, ge=0, description="Weight in grams")
    dimensions_json: Optional[str] = Field(None, description="Dimensions as JSON string")
    status: Optional[ProductStatus] = Field(None, description="Variant status")


class InventoryData(BaseModel):
    """Inventory data for variant response."""

    on_hand: int
    reserved: int
    available: int
    sold: int
    reorder_level: int
    is_in_stock: bool
    is_low_stock: bool
    stock_status: str


class VariantResponse(BaseModel):
    """Response schema for variant data with inventory."""

    id: str
    product_id: str
    sku: str
    variant_name: str
    price_cents: int
    display_price: float
    weight_grams: Optional[int]
    dimensions_json: Optional[str]
    status: str
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]
    inventory: Optional[InventoryData]

    @classmethod
    def from_variant(cls, variant: ProductVariant, inventory: Optional[Inventory] = None) -> "VariantResponse":
        """Convert ProductVariant domain model to response schema."""
        inventory_data = None
        if inventory:
            inventory_data = InventoryData(
                on_hand=inventory.on_hand,
                reserved=inventory.reserved,
                available=inventory.available,
                sold=inventory.sold,
                reorder_level=inventory.reorder_level,
                is_in_stock=inventory.is_in_stock,
                is_low_stock=inventory.is_low_stock,
                stock_status=inventory.stock_status,
            )

        return cls(
            id=variant.id or "",
            product_id=variant.product_id,
            sku=variant.sku,
            variant_name=variant.variant_name,
            price_cents=variant.price_cents,
            display_price=variant.display_price,
            weight_grams=variant.weight_grams,
            dimensions_json=variant.dimensions_json,
            status=variant.status.value,
            is_active=variant.is_active,
            created_at=variant.created_at.isoformat() if variant.created_at else None,
            updated_at=variant.updated_at.isoformat() if variant.updated_at else None,
            inventory=inventory_data,
        )


class InventoryAdjustRequest(BaseModel):
    """Request schema for inventory adjustment."""

    delta: int = Field(..., description="Change in stock quantity (positive or negative)")
    reason: str = Field(..., min_length=1, description="Reason for adjustment")


# Variant Endpoints
@router.get("/{product_id}/variants", response_model=List[VariantResponse])
async def list_variants(
    product_id: str,
    variant_repo: SQLiteProductVariantRepository = Depends(get_variant_repository),
    inventory_repo: SQLiteInventoryRepository = Depends(get_inventory_repository),
) -> List[VariantResponse]:
    """List all variants for a product with inventory data."""
    try:
        variants = variant_repo.get_all(product_id=product_id)
        
        responses = []
        for variant in variants:
            inventory = None
            if variant.id:
                inventory = inventory_repo.get_by_variant(variant_id=variant.id)
            responses.append(VariantResponse.from_variant(variant, inventory))
        
        return responses

    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/{product_id}/variants", response_model=VariantResponse, status_code=201)
async def create_variant(
    product_id: str,
    variant_data: VariantCreate,
    product_repo: SQLiteProductRepository = Depends(get_product_repository),
    variant_repo: SQLiteProductVariantRepository = Depends(get_variant_repository),
    inventory_repo: SQLiteInventoryRepository = Depends(get_inventory_repository),
) -> VariantResponse:
    """Create a new variant for a product."""
    try:
        product = product_repo.get_by_id(product_id=product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

        variant = ProductVariant(
            product_id=product_id,
            sku=variant_data.sku,
            variant_name=variant_data.variant_name,
            price_cents=variant_data.price_cents,
            weight_grams=variant_data.weight_grams,
            dimensions_json=variant_data.dimensions_json,
            status=variant_data.status,
        )

        saved_variant = variant_repo.save(variant)

        inventory = Inventory(
            variant_id=saved_variant.id,
            on_hand=0,
            reserved=0,
            sold=0,
            reorder_level=10,
        )
        saved_inventory = inventory_repo.save(inventory)

        return VariantResponse.from_variant(saved_variant, saved_inventory)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.patch("/variants/{variant_id}", response_model=VariantResponse)
async def update_variant(
    variant_id: str,
    variant_data: VariantUpdate,
    variant_repo: SQLiteProductVariantRepository = Depends(get_variant_repository),
    inventory_repo: SQLiteInventoryRepository = Depends(get_inventory_repository),
) -> VariantResponse:
    """Update an existing variant."""
    try:
        existing_variant = variant_repo.get_by_id(variant_id=variant_id)
        if not existing_variant:
            raise HTTPException(status_code=404, detail=f"Variant {variant_id} not found")

        update_dict = variant_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(existing_variant, field, value)

        updated_variant = variant_repo.update(existing_variant)

        inventory = inventory_repo.get_by_variant(variant_id=variant_id)

        return VariantResponse.from_variant(updated_variant, inventory)

    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Variant {variant_id} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.delete("/variants/{variant_id}", status_code=204)
async def delete_variant(
    variant_id: str,
    variant_repo: SQLiteProductVariantRepository = Depends(get_variant_repository),
    inventory_repo: SQLiteInventoryRepository = Depends(get_inventory_repository),
) -> None:
    """Delete a variant by ID."""
    try:
        inventory = inventory_repo.get_by_variant(variant_id=variant_id)
        if inventory and inventory.id:
            inventory_repo.delete(inventory_id=inventory.id)

        deleted = variant_repo.delete(variant_id=variant_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Variant {variant_id} not found")

    except HTTPException:
        raise
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/variants/{variant_id}/inventory/adjust", response_model=VariantResponse)
async def adjust_inventory(
    variant_id: str,
    adjust_data: InventoryAdjustRequest,
    variant_repo: SQLiteProductVariantRepository = Depends(get_variant_repository),
    inventory_repo: SQLiteInventoryRepository = Depends(get_inventory_repository),
) -> VariantResponse:
    """Adjust inventory stock for a variant."""
    try:
        variant = variant_repo.get_by_id(variant_id=variant_id)
        if not variant:
            raise HTTPException(status_code=404, detail=f"Variant {variant_id} not found")

        updated_inventory = inventory_repo.adjust_stock(
            variant_id=variant_id,
            delta=adjust_data.delta,
            reason=adjust_data.reason,
        )

        return VariantResponse.from_variant(variant, updated_inventory)

    except HTTPException:
        raise
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


class ImageUploadResponse(BaseModel):
    """Response schema for image upload."""

    image_id: str
    product_id: str
    image_url: str
    thumbnail_url: str
    alt_text: Optional[str]
    is_primary: bool


@router.post("/{product_id}/images", response_model=ImageUploadResponse, status_code=201)
async def upload_product_image(
    product_id: str,
    file: UploadFile = File(...),
    alt_text: Optional[str] = Form(None),
    is_primary: bool = Form(False),
    product_repo: SQLiteProductRepository = Depends(get_product_repository),
    image_service: ImageService = Depends(get_image_service),
) -> ImageUploadResponse:
    """Upload and optimize product image with thumbnail generation."""
    try:
        product = product_repo.get_by_id(product_id=product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

        file_bytes = await file.read()

        image_service.validate_image_magic(file_bytes)

        optimized_bytes = image_service.optimize_image(file_bytes)
        thumbnail_bytes = image_service.create_thumbnail(file_bytes)

        image_filename = f"{uuid.uuid4()}.jpg"
        thumbnail_filename = f"{uuid.uuid4()}_thumb.jpg"

        image_service.save_image(optimized_bytes, product_id, image_filename)
        image_service.save_image(thumbnail_bytes, product_id, thumbnail_filename)

        image_url = f"/data/products/{product_id}/images/{image_filename}"
        thumbnail_url = f"/data/products/{product_id}/images/{thumbnail_filename}"

        image_id = product_repo.add_image(
            product_id=product_id,
            image_url=image_url,
            alt_text=alt_text,
            is_primary=is_primary,
        )

        return ImageUploadResponse(
            image_id=image_id,
            product_id=product_id,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            alt_text=alt_text,
            is_primary=is_primary,
        )

    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {e.reason}")
    except RepositoryError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


class CSVImportResponse(BaseModel):
    """Response schema for CSV import."""

    status: str
    message: str
    total_rows: int
    valid_rows: int
    imported_rows: int
    errors: List[dict]


@router.post("/import", response_model=CSVImportResponse, status_code=202)
async def import_products_csv(
    file: UploadFile = File(...),
    product_repo: SQLiteProductRepository = Depends(get_product_repository),
    variant_repo: SQLiteProductVariantRepository = Depends(get_variant_repository),
    inventory_repo: SQLiteInventoryRepository = Depends(get_inventory_repository),
) -> CSVImportResponse:
    try:
        if not file.filename or not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")

        content = await file.read()
        
        try:
            csv_content = content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")

        csv_file = StringIO(csv_content)
        reader = csv.DictReader(csv_file)
        validation_result: CSVValidationResult = validate_product_csv(reader, chunk_size=50000)

        if not validation_result["valid"]:
            return CSVImportResponse(
                status="validation_failed",
                message=f"CSV validation failed with {len(validation_result['errors'])} errors",
                total_rows=validation_result["total_rows"],
                valid_rows=validation_result["valid_rows"],
                imported_rows=0,
                errors=validation_result["errors"],
            )

        csv_file.seek(0)
        reader = csv.DictReader(csv_file)

        imported_count = 0
        import_errors = []

        for line_number, row in enumerate(reader, start=2):
            row_type = row.get("type", "").lower().strip()

            try:
                if row_type == "product":
                    _import_product_row(row, product_repo)
                    imported_count += 1
                elif row_type == "variant":
                    _import_variant_row(row, variant_repo, inventory_repo)
                    imported_count += 1
                elif row_type == "inventory":
                    _import_inventory_row(row, inventory_repo)
                    imported_count += 1
                elif row_type == "override":
                    pass
                elif row_type == "image":
                    _import_image_row(row, product_repo)
                    imported_count += 1
            except Exception as e:
                import_errors.append({
                    "line_number": line_number,
                    "field": "row",
                    "value": str(row),
                    "error": f"Import failed: {str(e)}",
                })

        return CSVImportResponse(
            status="accepted",
            message=f"CSV import completed. {imported_count} rows imported successfully.",
            total_rows=validation_result["total_rows"],
            valid_rows=validation_result["valid_rows"],
            imported_rows=imported_count,
            errors=import_errors,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import error: {str(e)}")


def _import_product_row(row: dict, repo: SQLiteProductRepository) -> None:
    product = Product(
        wa_number_id=row.get("wa_number_id", "").strip(),
        name=row.get("name", "").strip(),
        description=row.get("description", "").strip() or None,
        category=row.get("category", "general").strip(),
        base_price_cents=int(row.get("base_price_cents", "0").strip()),
        currency=row.get("currency", "IDR").strip(),
        sku=row.get("sku", "").strip().upper(),
        status=ProductStatus(row.get("status", "active").strip().lower()),
        visibility=VisibilityStatus(row.get("visibility", "public").strip().lower()),
    )
    repo.save(product)


def _import_variant_row(
    row: dict,
    variant_repo: SQLiteProductVariantRepository,
    inventory_repo: SQLiteInventoryRepository,
) -> None:
    variant = ProductVariant(
        product_id=row.get("product_id", "").strip(),
        sku=row.get("sku", "").strip().upper(),
        variant_name=row.get("variant_name", "").strip(),
        price_cents=int(row.get("price_cents", "0").strip()),
        weight_grams=int(row.get("weight_grams", "0").strip()) if row.get("weight_grams", "").strip() else None,
        dimensions_json=row.get("dimensions_json", "").strip() or None,
        status=ProductStatus(row.get("status", "active").strip().lower()),
    )
    saved_variant = variant_repo.save(variant)

    inventory = Inventory(
        variant_id=saved_variant.id,
        on_hand=0,
        reserved=0,
        sold=0,
        reorder_level=10,
    )
    inventory_repo.save(inventory)


def _import_inventory_row(row: dict, repo: SQLiteInventoryRepository) -> None:
    variant_id = row.get("variant_id", "").strip()
    existing = repo.get_by_variant(variant_id=variant_id)
    
    if existing and existing.id:
        existing.on_hand = int(row.get("on_hand", "0").strip())
        existing.reserved = int(row.get("reserved", "0").strip())
        existing.sold = int(row.get("sold", "0").strip())
        existing.reorder_level = int(row.get("reorder_level", "10").strip())
        repo.update(existing)
    else:
        inventory = Inventory(
            variant_id=variant_id,
            on_hand=int(row.get("on_hand", "0").strip()),
            reserved=int(row.get("reserved", "0").strip()),
            sold=int(row.get("sold", "0").strip()),
            reorder_level=int(row.get("reorder_level", "10").strip()),
        )
        repo.save(inventory)


def _import_image_row(row: dict, repo: SQLiteProductRepository) -> None:
    product_id = row.get("product_id", "").strip()
    image_url = row.get("image_url", "").strip()
    alt_text = row.get("alt_text", "").strip() or None
    is_primary_str = row.get("is_primary", "0").strip().lower()
    is_primary = is_primary_str in ["1", "true"]

    repo.add_image(
        product_id=product_id,
        image_url=image_url,
        alt_text=alt_text,
        is_primary=is_primary,
    )


def _generate_csv_rows(
    wa_number_id: Optional[str],
    category: Optional[str],
    visibility: Optional[str],
    product_repo: SQLiteProductRepository,
    variant_repo: SQLiteProductVariantRepository,
    inventory_repo: SQLiteInventoryRepository,
):
    """Generator function to stream CSV rows for export.
    
    Yields CSV rows in Shopify format (one row per variant).
    Includes effective values when wa_number_id is provided.
    """
    import io
    
    # CSV Header (Shopify-inspired format)
    header = [
        "Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags",
        "Published", "Option1 Name", "Option1 Value", "Variant SKU",
        "Variant Grams", "Variant Inventory Tracker", "Variant Inventory Qty",
        "Variant Inventory Policy", "Variant Fulfillment Service",
        "Variant Price", "Variant Compare At Price", "Variant Requires Shipping",
        "Variant Taxable", "Variant Barcode", "Image Src", "Image Position",
        "Image Alt Text", "Gift Card", "SEO Title", "SEO Description",
        "Google Shopping / Google Product Category", "Google Shopping / Gender",
        "Google Shopping / Age Group", "Google Shopping / MPN",
        "Google Shopping / AdWords Grouping", "Google Shopping / AdWords Labels",
        "Google Shopping / Condition", "Google Shopping / Custom Product",
        "Google Shopping / Custom Label 0", "Google Shopping / Custom Label 1",
        "Google Shopping / Custom Label 2", "Google Shopping / Custom Label 3",
        "Google Shopping / Custom Label 4", "Variant Image", "Variant Weight Unit",
        "Variant Tax Code", "Cost per item", "Status"
    ]
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)
    
    # Get products based on filters
    if wa_number_id:
        products = product_repo.get_all(wa_number_id=wa_number_id)
    else:
        # If no wa_number_id, we can't filter properly, so return empty
        return
    
    # Apply category filter
    if category:
        products = [p for p in products if p.category == category]
    
    # Apply visibility filter
    if visibility:
        visibility_enum = VisibilityStatus(visibility.lower())
        products = [p for p in products if p.visibility == visibility_enum]
    
    for product in products:
        # Get effective product if wa_number_id provided
        if wa_number_id:
            effective_product = product_repo.get_effective_product(
                wa_number_id=wa_number_id,
                product_id=product.id
            )
            if effective_product:
                product = effective_product
        
        # Get variants for this product
        variants = variant_repo.get_all(product_id=product.id)
        
        if not variants:
            # Product without variants - export as single row
            row = [
                product.sku,  # Handle
                product.name,  # Title
                product.description or "",  # Body (HTML)
                "",  # Vendor
                product.category,  # Type
                "",  # Tags
                "TRUE" if product.is_visible else "FALSE",  # Published
                "",  # Option1 Name
                "",  # Option1 Value
                product.sku,  # Variant SKU
                "",  # Variant Grams
                "",  # Variant Inventory Tracker
                "",  # Variant Inventory Qty
                "deny",  # Variant Inventory Policy
                "manual",  # Variant Fulfillment Service
                f"{product.display_price:.2f}",  # Variant Price
                "",  # Variant Compare At Price
                "TRUE",  # Variant Requires Shipping
                "TRUE",  # Variant Taxable
                "",  # Variant Barcode
                "",  # Image Src
                "",  # Image Position
                "",  # Image Alt Text
                "FALSE",  # Gift Card
                "",  # SEO Title
                "",  # SEO Description
                "",  # Google Shopping / Google Product Category
                "",  # Google Shopping / Gender
                "",  # Google Shopping / Age Group
                "",  # Google Shopping / MPN
                "",  # Google Shopping / AdWords Grouping
                "",  # Google Shopping / AdWords Labels
                "new",  # Google Shopping / Condition
                "FALSE",  # Google Shopping / Custom Product
                "",  # Google Shopping / Custom Label 0
                "",  # Google Shopping / Custom Label 1
                "",  # Google Shopping / Custom Label 2
                "",  # Google Shopping / Custom Label 3
                "",  # Google Shopping / Custom Label 4
                "",  # Variant Image
                "g",  # Variant Weight Unit
                "",  # Variant Tax Code
                "",  # Cost per item
                product.status.value,  # Status
            ]
            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
        else:
            # Product with variants - one row per variant
            for idx, variant in enumerate(variants):
                # Get inventory for this variant
                inventory = inventory_repo.get_by_variant(variant_id=variant.id)
                
                row = [
                    product.sku,  # Handle (same for all variants)
                    product.name if idx == 0 else "",  # Title (only first row)
                    product.description if idx == 0 else "",  # Body (HTML)
                    "",  # Vendor
                    product.category if idx == 0 else "",  # Type
                    "",  # Tags
                    "TRUE" if product.is_visible else "FALSE" if idx == 0 else "",  # Published
                    "Variant" if idx == 0 else "",  # Option1 Name
                    variant.variant_name,  # Option1 Value
                    variant.sku,  # Variant SKU
                    str(variant.weight_grams) if variant.weight_grams else "",  # Variant Grams
                    "shopify",  # Variant Inventory Tracker
                    str(inventory.on_hand) if inventory else "0",  # Variant Inventory Qty
                    "deny",  # Variant Inventory Policy
                    "manual",  # Variant Fulfillment Service
                    f"{variant.display_price:.2f}",  # Variant Price
                    "",  # Variant Compare At Price
                    "TRUE",  # Variant Requires Shipping
                    "TRUE",  # Variant Taxable
                    "",  # Variant Barcode
                    "",  # Image Src
                    "",  # Image Position
                    "",  # Image Alt Text
                    "FALSE",  # Gift Card
                    "",  # SEO Title
                    "",  # SEO Description
                    "",  # Google Shopping / Google Product Category
                    "",  # Google Shopping / Gender
                    "",  # Google Shopping / Age Group
                    "",  # Google Shopping / MPN
                    "",  # Google Shopping / AdWords Grouping
                    "",  # Google Shopping / AdWords Labels
                    "new",  # Google Shopping / Condition
                    "FALSE",  # Google Shopping / Custom Product
                    "",  # Google Shopping / Custom Label 0
                    "",  # Google Shopping / Custom Label 1
                    "",  # Google Shopping / Custom Label 2
                    "",  # Google Shopping / Custom Label 3
                    "",  # Google Shopping / Custom Label 4
                    "",  # Variant Image
                    "g",  # Variant Weight Unit
                    "",  # Variant Tax Code
                    "",  # Cost per item
                    variant.status.value,  # Status
                ]
                writer.writerow(row)
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)


