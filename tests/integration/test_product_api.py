"""Integration tests for Product API endpoints.

Tests full CRUD flow, multi-tenancy with overrides, image upload,
and CSV import functionality.
"""

import io
import sqlite3
import tempfile
from pathlib import Path
from typing import Generator

import httpx
import pytest

from oneai_reach.api.main import app


@pytest.fixture
def temp_db() -> Generator[Path, None, None]:
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
# Initialize database schema
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            wa_number_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT DEFAULT 'general',
            base_price_cents INTEGER NOT NULL,
            currency TEXT DEFAULT 'IDR',
            sku TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'active',
            visibility TEXT DEFAULT 'public',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            variant_name TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            weight_grams INTEGER,
            dimensions_json TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id TEXT PRIMARY KEY,
            variant_id TEXT NOT NULL UNIQUE,
            quantity_available INTEGER DEFAULT 0,
            quantity_reserved INTEGER DEFAULT 0,
            quantity_sold INTEGER DEFAULT 0,
            reorder_level INTEGER DEFAULT 10,
            last_restocked_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (variant_id) REFERENCES product_variants(id) ON DELETE CASCADE
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_overrides (
            id TEXT PRIMARY KEY,
            wa_number_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            override_price_cents INTEGER,
            override_stock_quantity INTEGER,
            is_hidden INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(wa_number_id, product_id),
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_images (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            image_url TEXT NOT NULL,
            alt_text TEXT,
            display_order INTEGER DEFAULT 0,
            is_primary INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    db_path.unlink(missing_ok=True)


@pytest.fixture
def client(temp_db: Path, monkeypatch):
    """Create test client with temporary database."""
    # Must use DB_ prefix to override nested settings
    monkeypatch.setenv("DB_DB_FILE", str(temp_db))
    monkeypatch.setenv("DB_API_KEYS", "test_api_key")
    
    # Force reload settings
    from oneai_reach.config.settings import get_settings
    get_settings.cache_clear()
    
    # Import AFTER monkeypatch to ensure correct db is used
    import importlib
    import oneai_reach.api.v1.products
    importlib.reload(oneai_reach.api.v1.products)
    
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def auth_headers() -> dict:
    """Authentication headers for API requests."""
    return {"X-API-Key": "test_api_key"}


class TestProductCRUD:
    """Test full CRUD flow for products."""
    
    @pytest.mark.asyncio
    async def test_create_product(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test creating a new product."""
        response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "6281234567890",
                "name": "Test Product",
                "description": "A test product",
                "category": "electronics",
                "base_price_cents": 100000,
                "currency": "IDR",
                "sku": "TEST-001",
                "status": "active",
                "visibility": "public",
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Product"
        assert data["sku"] == "TEST-001"
        assert data["base_price_cents"] == 100000
        assert data["display_price"] == 1000.0
        assert data["is_active"] is True
        assert data["is_visible"] is True
        assert "id" in data
    
    @pytest.mark.asyncio
    async def test_get_product(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test retrieving a product by ID."""
        create_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "6281234567890",
                "name": "Test Product",
                "description": "A test product",
                "category": "electronics",
                "base_price_cents": 100000,
                "currency": "IDR",
                "sku": "TEST-002",
            },
            headers=auth_headers,
        )
        product_id = create_response.json()["id"]
        
        response = await client.get(
            f"/api/v1/products/{product_id}",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == product_id
        assert data["name"] == "Test Product"
    
    @pytest.mark.asyncio
    async def test_update_product(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test updating a product."""
        create_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "6281234567890",
                "name": "Original Name",
                "category": "electronics",
                "base_price_cents": 100000,
                "sku": "TEST-003",
            },
            headers=auth_headers,
        )
        product_id = create_response.json()["id"]
        
        response = await client.patch(
            f"/api/v1/products/{product_id}",
            json={
                "name": "Updated Name",
                "base_price_cents": 150000,
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["base_price_cents"] == 150000
        assert data["sku"] == "TEST-003"
    
    @pytest.mark.asyncio
    async def test_delete_product(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test deleting a product."""
        create_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "6281234567890",
                "name": "To Delete",
                "category": "electronics",
                "base_price_cents": 100000,
                "sku": "TEST-004",
            },
            headers=auth_headers,
        )
        product_id = create_response.json()["id"]
        
        response = await client.delete(
            f"/api/v1/products/{product_id}",
            headers=auth_headers,
        )
        
        assert response.status_code == 204
        
        get_response = await client.get(
            f"/api/v1/products/{product_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_list_products(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test listing products for a WA number."""
        wa_number = "6281234567890"
        
        for i in range(3):
            await client.post(
                "/api/v1/products",
                json={
                    "wa_number_id": wa_number,
                    "name": f"Product {i}",
                    "category": "electronics",
                    "base_price_cents": 100000 + (i * 10000),
                    "sku": f"TEST-LIST-{i}",
                },
                headers=auth_headers,
            )
        
        response = await client.get(
            f"/api/v1/products?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert all(p["wa_number_id"] == wa_number for p in data)


class TestProductVariants:
    """Test variant CRUD operations."""
    
    @pytest.mark.asyncio
    async def test_create_variant_with_inventory(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test creating a variant automatically creates inventory."""
        product_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "6281234567890",
                "name": "Variant Test Product",
                "category": "clothing",
                "base_price_cents": 100000,
                "sku": "VAR-PROD-001",
            },
            headers=auth_headers,
        )
        product_id = product_response.json()["id"]
        
        response = await client.post(
            f"/api/v1/products/{product_id}/variants",
            json={
                "sku": "VAR-001-S",
                "variant_name": "Small",
                "price_cents": 95000,
                "weight_grams": 200,
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["variant_name"] == "Small"
        assert data["sku"] == "VAR-001-S"
        assert data["price_cents"] == 95000
        assert data["inventory"] is not None
        assert data["inventory"]["on_hand"] == 0
        assert data["inventory"]["reorder_level"] == 10
    
    @pytest.mark.asyncio
    async def test_update_inventory(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test adjusting inventory stock."""
        product_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "6281234567890",
                "name": "Inventory Test",
                "category": "electronics",
                "base_price_cents": 100000,
                "sku": "INV-PROD-001",
            },
            headers=auth_headers,
        )
        product_id = product_response.json()["id"]
        
        variant_response = await client.post(
            f"/api/v1/products/{product_id}/variants",
            json={
                "sku": "INV-VAR-001",
                "variant_name": "Default",
                "price_cents": 100000,
            },
            headers=auth_headers,
        )
        variant_id = variant_response.json()["id"]
        
        response = await client.post(
            f"/api/v1/products/variants/{variant_id}/inventory/adjust",
            json={
                "delta": 50,
                "reason": "restock",
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["inventory"]["on_hand"] == 50
        assert data["inventory"]["available"] == 50
        assert data["inventory"]["is_in_stock"] is True


class TestMultiTenancy:
    """Test multi-tenancy with product overrides."""
    
    @pytest.mark.asyncio
    async def test_global_product_with_wa_override(self, client: httpx.AsyncClient, auth_headers: dict, temp_db: Path):
        """Test COALESCE query returns override values for specific WA number."""
        product_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "global",
                "name": "Global Product",
                "category": "electronics",
                "base_price_cents": 100000,
                "sku": "GLOBAL-001",
            },
            headers=auth_headers,
        )
        product_id = product_response.json()["id"]
        
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            """
            INSERT INTO product_overrides (id, wa_number_id, product_id, override_price_cents)
            VALUES (?, ?, ?, ?)
            """,
            ("override-1", "6281234567890", product_id, 80000),
        )
        conn.commit()
        conn.close()
        
        response = await client.get(
            f"/api/v1/products/{product_id}?wa_number_id=6281234567890",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["base_price_cents"] == 80000
        assert data["display_price"] == 800.0
    
    @pytest.mark.asyncio
    async def test_product_without_override(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test product returns base values when no override exists."""
        product_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "global",
                "name": "No Override Product",
                "category": "electronics",
                "base_price_cents": 100000,
                "sku": "NO-OVERRIDE-001",
            },
            headers=auth_headers,
        )
        product_id = product_response.json()["id"]
        
        response = await client.get(
            f"/api/v1/products/{product_id}?wa_number_id=6289999999999",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["base_price_cents"] == 100000


class TestImageUpload:
    """Test image upload and optimization."""
    
    @pytest.mark.asyncio
    async def test_upload_image(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test uploading and optimizing product image."""
        product_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": "6281234567890",
                "name": "Image Test Product",
                "category": "electronics",
                "base_price_cents": 100000,
                "sku": "IMG-001",
            },
            headers=auth_headers,
        )
        product_id = product_response.json()["id"]
        
        jpeg_bytes = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46,
            0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01,
            0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08,
            0x07, 0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C,
            0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D,
            0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20,
            0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27,
            0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
            0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4,
            0x00, 0x14, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x03, 0xFF, 0xDA, 0x00, 0x08,
            0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x37, 0xFF,
            0xD9
        ])
        
        response = await client.post(
            f"/api/v1/products/{product_id}/images",
            files={"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
            data={"alt_text": "Test image", "is_primary": "true"},
            headers=auth_headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["product_id"] == product_id
        assert data["image_url"].startswith("/data/products/")
        assert data["thumbnail_url"].startswith("/data/products/")
        assert data["alt_text"] == "Test image"
        assert data["is_primary"] is True


class TestCSVImport:
    """Test CSV import functionality."""
    
    @pytest.mark.asyncio
    async def test_import_valid_csv(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test importing valid CSV with products and variants."""
        csv_content = """type,wa_number_id,name,description,category,base_price_cents,currency,sku,status,visibility,product_id,variant_name,price_cents,weight_grams
product,6281234567890,CSV Product 1,Test product,electronics,100000,IDR,CSV-001,active,public,,,,
variant,,,,,,,CSV-001-S,active,,CSV-001,Small,95000,200
product,6281234567890,CSV Product 2,Another product,clothing,150000,IDR,CSV-002,active,public,,,,
"""
        
        response = await client.post(
            "/api/v1/products/import",
            files={"file": ("products.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=auth_headers,
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["total_rows"] >= 3
        assert data["imported_rows"] >= 2
    
    @pytest.mark.asyncio
    async def test_import_invalid_csv(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test importing CSV with validation errors."""
        csv_content = """type,wa_number_id,name,base_price_cents,sku
product,6281234567890,Invalid Product,-100,INVALID-001
"""
        
        response = await client.post(
            "/api/v1/products/import",
            files={"file": ("invalid.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=auth_headers,
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "validation_failed"
        assert len(data["errors"]) > 0


class TestEndToEndFlow:
    """Test complete end-to-end product management flow."""
    
    @pytest.mark.asyncio
    async def test_full_crud_flow(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test complete flow: create product → add variants → update inventory → get effective product."""
        wa_number = "6281234567890"
        
        product_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": wa_number,
                "name": "E2E Test Product",
                "description": "End-to-end test",
                "category": "electronics",
                "base_price_cents": 200000,
                "currency": "IDR",
                "sku": "E2E-001",
                "status": "active",
                "visibility": "public",
            },
            headers=auth_headers,
        )
        assert product_response.status_code == 201
        product_id = product_response.json()["id"]
        
        variant_response = await client.post(
            f"/api/v1/products/{product_id}/variants",
            json={
                "sku": "E2E-001-M",
                "variant_name": "Medium",
                "price_cents": 195000,
                "weight_grams": 300,
            },
            headers=auth_headers,
        )
        assert variant_response.status_code == 201
        variant_id = variant_response.json()["id"]
        
        inventory_response = await client.post(
            f"/api/v1/products/variants/{variant_id}/inventory/adjust",
            json={"delta": 100, "reason": "restock"},
            headers=auth_headers,
        )
        assert inventory_response.status_code == 200
        assert inventory_response.json()["inventory"]["on_hand"] == 100
        
        get_response = await client.get(
            f"/api/v1/products/{product_id}?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        assert get_response.status_code == 200
        product_data = get_response.json()
        assert product_data["name"] == "E2E Test Product"
        assert product_data["base_price_cents"] == 200000
        
        variants_response = await client.get(
            f"/api/v1/products/{product_id}/variants",
            headers=auth_headers,
        )
        assert variants_response.status_code == 200
        variants = variants_response.json()
        assert len(variants) == 1
        assert variants[0]["inventory"]["on_hand"] == 100
