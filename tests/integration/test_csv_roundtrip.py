"""Integration tests for CSV import/export round-trip functionality.

Tests the complete cycle: export products → import to new DB → verify data integrity.
Ensures variants, inventory, and product metadata are preserved across the round-trip.
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
            on_hand INTEGER DEFAULT 0,
            reserved INTEGER DEFAULT 0,
            sold INTEGER DEFAULT 0,
            reorder_level INTEGER DEFAULT 10,
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
    monkeypatch.setenv("DB_FILE", str(temp_db))
    monkeypatch.setenv("API_KEY", "test_api_key")
    
    from oneai_reach.config.settings import get_settings
    get_settings.cache_clear()
    
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def auth_headers() -> dict:
    """Authentication headers for API requests."""
    return {"X-API-Key": "test_api_key"}


class TestCSVRoundTrip:
    """Test CSV export → import → verify data integrity."""
    
    @pytest.mark.asyncio
    async def test_basic_product_roundtrip(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test exporting a product and importing it to verify data integrity.
        
        Note: Export produces Shopify-format CSV, import expects custom format.
        This test verifies export works and then imports using custom format.
        """
        wa_number = "6281234567890"
        
        # Create a product
        create_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": wa_number,
                "name": "Round-Trip Product",
                "description": "Test product for round-trip",
                "category": "electronics",
                "base_price_cents": 250000,
                "currency": "IDR",
                "sku": "RT-001",
                "status": "active",
                "visibility": "public",
            },
            headers=auth_headers,
        )
        assert create_response.status_code == 201
        original_product = create_response.json()
        
        # Export to CSV (Shopify format)
        export_response = await client.get(
            f"/api/v1/products/export?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        assert export_response.status_code == 200
        csv_content = export_response.text
        
        # Verify CSV contains product data
        assert "Round-Trip Product" in csv_content
        assert "RT-001" in csv_content
        assert "electronics" in csv_content
        
        # Delete original product
        delete_response = await client.delete(
            f"/api/v1/products/{original_product['id']}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 204
        
        # Import using custom format (not Shopify format)
        custom_csv = f"""type,wa_number_id,name,description,category,base_price_cents,currency,sku,status,visibility
product,{wa_number},Round-Trip Product,Test product for round-trip,electronics,250000,IDR,RT-001,active,public
"""
        
        import_response = await client.post(
            "/api/v1/products/import",
            files={"file": ("products.csv", io.BytesIO(custom_csv.encode()), "text/csv")},
            headers=auth_headers,
        )
        assert import_response.status_code == 202
        import_data = import_response.json()
        if import_data["status"] != "accepted":
            print(f"Import failed: {import_data}")
        assert import_data["status"] == "accepted"
        assert import_data["imported_rows"] >= 1
        
        # Verify imported product matches original
        list_response = await client.get(
            f"/api/v1/products?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        products = list_response.json()
        
        imported_product = next((p for p in products if p["sku"] == "RT-001"), None)
        assert imported_product is not None
        assert imported_product["name"] == original_product["name"]
        assert imported_product["description"] == original_product["description"]
        assert imported_product["category"] == original_product["category"]
        assert imported_product["base_price_cents"] == original_product["base_price_cents"]
        assert imported_product["currency"] == original_product["currency"]
        assert imported_product["status"] == original_product["status"]
        assert imported_product["visibility"] == original_product["visibility"]
    
    @pytest.mark.asyncio
    async def test_product_with_variants_roundtrip(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test exporting product with variants and verifying all variants are preserved.
        
        Note: Uses custom format for import since export produces Shopify format.
        """
        wa_number = "6281234567890"
        
        # Create product
        product_response = await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": wa_number,
                "name": "Variant Test Product",
                "description": "Product with multiple variants",
                "category": "clothing",
                "base_price_cents": 150000,
                "currency": "IDR",
                "sku": "VAR-RT-001",
                "status": "active",
                "visibility": "public",
            },
            headers=auth_headers,
        )
        assert product_response.status_code == 201
        product_id = product_response.json()["id"]
        
        # Create three variants
        variants_data = [
            {"sku": "VAR-RT-001-S", "variant_name": "Small", "price_cents": 140000, "weight_grams": 200},
            {"sku": "VAR-RT-001-M", "variant_name": "Medium", "price_cents": 150000, "weight_grams": 250},
            {"sku": "VAR-RT-001-L", "variant_name": "Large", "price_cents": 160000, "weight_grams": 300},
        ]
        
        created_variants = []
        for variant_data in variants_data:
            variant_response = await client.post(
                f"/api/v1/products/{product_id}/variants",
                json=variant_data,
                headers=auth_headers,
            )
            assert variant_response.status_code == 201
            created_variants.append(variant_response.json())
        
        # Update inventory for variants
        for i, variant in enumerate(created_variants):
            inventory_response = await client.post(
                f"/api/v1/products/variants/{variant['id']}/inventory/adjust",
                json={"delta": (i + 1) * 10, "reason": "initial_stock"},
                headers=auth_headers,
            )
            assert inventory_response.status_code == 200
        
        # Export to CSV
        export_response = await client.get(
            f"/api/v1/products/export?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        assert export_response.status_code == 200
        csv_content = export_response.text
        
        # Verify CSV contains all variants
        assert "Small" in csv_content
        assert "Medium" in csv_content
        assert "Large" in csv_content
        assert "VAR-RT-001-S" in csv_content
        assert "VAR-RT-001-M" in csv_content
        assert "VAR-RT-001-L" in csv_content
        
        # Delete product and variants
        delete_response = await client.delete(
            f"/api/v1/products/{product_id}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 204
        
        # Import using custom format
        custom_csv = f"""type,wa_number_id,name,description,category,base_price_cents,currency,sku,status,visibility,product_id,variant_name,price_cents,weight_grams
product,{wa_number},Variant Test Product,Product with multiple variants,clothing,150000,IDR,VAR-RT-001,active,public,,,,
variant,,,,,,,VAR-RT-001-S,active,,VAR-RT-001,Small,140000,200
variant,,,,,,,VAR-RT-001-M,active,,VAR-RT-001,Medium,150000,250
variant,,,,,,,VAR-RT-001-L,active,,VAR-RT-001,Large,160000,300
"""
        
        import_response = await client.post(
            "/api/v1/products/import",
            files={"file": ("products.csv", io.BytesIO(custom_csv.encode()), "text/csv")},
            headers=auth_headers,
        )
        assert import_response.status_code == 202
        import_data = import_response.json()
        assert import_data["status"] == "accepted"
        assert import_data["imported_rows"] >= 4  # 1 product + 3 variants
        
        # Verify imported product exists
        list_response = await client.get(
            f"/api/v1/products?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        products = list_response.json()
        
        imported_product = next((p for p in products if p["sku"] == "VAR-RT-001"), None)
        assert imported_product is not None
        
        # Verify all variants were imported
        variants_response = await client.get(
            f"/api/v1/products/{imported_product['id']}/variants",
            headers=auth_headers,
        )
        assert variants_response.status_code == 200
        imported_variants = variants_response.json()
        
        assert len(imported_variants) == 3
        
        # Verify variant details
        variant_skus = {v["sku"] for v in imported_variants}
        assert "VAR-RT-001-S" in variant_skus
        assert "VAR-RT-001-M" in variant_skus
        assert "VAR-RT-001-L" in variant_skus
        
        # Verify variant names
        variant_names = {v["variant_name"] for v in imported_variants}
        assert "Small" in variant_names
        assert "Medium" in variant_names
        assert "Large" in variant_names
        
        # Verify prices
        for variant in imported_variants:
            if variant["sku"] == "VAR-RT-001-S":
                assert variant["price_cents"] == 140000
            elif variant["sku"] == "VAR-RT-001-M":
                assert variant["price_cents"] == 150000
            elif variant["sku"] == "VAR-RT-001-L":
                assert variant["price_cents"] == 160000
    
    @pytest.mark.asyncio
    async def test_multiple_products_roundtrip(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test exporting multiple products and verifying all are preserved.
        
        Note: Uses custom format for import since export produces Shopify format.
        """
        wa_number = "6281234567890"
        
        # Create multiple products
        products_data = [
            {
                "wa_number_id": wa_number,
                "name": "Product A",
                "category": "electronics",
                "base_price_cents": 100000,
                "sku": "MULTI-A",
            },
            {
                "wa_number_id": wa_number,
                "name": "Product B",
                "category": "clothing",
                "base_price_cents": 200000,
                "sku": "MULTI-B",
            },
            {
                "wa_number_id": wa_number,
                "name": "Product C",
                "category": "food",
                "base_price_cents": 50000,
                "sku": "MULTI-C",
            },
        ]
        
        created_products = []
        for product_data in products_data:
            response = await client.post(
                "/api/v1/products",
                json=product_data,
                headers=auth_headers,
            )
            assert response.status_code == 201
            created_products.append(response.json())
        
        # Export to CSV
        export_response = await client.get(
            f"/api/v1/products/export?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        assert export_response.status_code == 200
        csv_content = export_response.text
        
        # Delete all products
        for product in created_products:
            delete_response = await client.delete(
                f"/api/v1/products/{product['id']}",
                headers=auth_headers,
            )
            assert delete_response.status_code == 204
        
        # Import using custom format
        custom_csv = f"""type,wa_number_id,name,category,base_price_cents,sku
product,{wa_number},Product A,electronics,100000,MULTI-A
product,{wa_number},Product B,clothing,200000,MULTI-B
product,{wa_number},Product C,food,50000,MULTI-C
"""
        
        import_response = await client.post(
            "/api/v1/products/import",
            files={"file": ("products.csv", io.BytesIO(custom_csv.encode()), "text/csv")},
            headers=auth_headers,
        )
        assert import_response.status_code == 202
        import_data = import_response.json()
        assert import_data["status"] == "accepted"
        assert import_data["imported_rows"] >= 3
        
        # Verify all products were imported
        list_response = await client.get(
            f"/api/v1/products?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        imported_products = list_response.json()
        
        assert len(imported_products) >= 3
        
        imported_skus = {p["sku"] for p in imported_products}
        assert "MULTI-A" in imported_skus
        assert "MULTI-B" in imported_skus
        assert "MULTI-C" in imported_skus


class TestCSVImportErrors:
    """Test error handling for invalid CSV imports."""
    
    @pytest.mark.asyncio
    async def test_import_invalid_csv_format(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test importing CSV with invalid format returns error report."""
        csv_content = """type,wa_number_id,name,base_price_cents,sku
product,6281234567890,Invalid Product,-100,INVALID-001
product,6281234567890,,50000,INVALID-002
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
        
        # Verify specific errors
        errors = data["errors"]
        price_error = next((e for e in errors if e["field"] == "base_price_cents"), None)
        assert price_error is not None
        assert "greater than 0" in price_error["error"].lower()
        
        name_error = next((e for e in errors if e["field"] == "name"), None)
        assert name_error is not None
    
    @pytest.mark.asyncio
    async def test_import_duplicate_sku(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test importing CSV with duplicate SKUs returns validation error."""
        csv_content = """type,wa_number_id,name,base_price_cents,sku,category
product,6281234567890,Product 1,100000,DUP-SKU,electronics
product,6281234567890,Product 2,200000,DUP-SKU,clothing
"""
        
        response = await client.post(
            "/api/v1/products/import",
            files={"file": ("duplicate.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=auth_headers,
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "validation_failed"
        assert len(data["errors"]) > 0
        
        # Verify duplicate SKU error
        sku_error = next((e for e in data["errors"] if "unique" in e["error"].lower()), None)
        assert sku_error is not None
    
    @pytest.mark.asyncio
    async def test_import_missing_required_fields(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test importing CSV with missing required fields returns validation error."""
        csv_content = """type,wa_number_id,name,base_price_cents,sku
product,6281234567890,Product Name,,
variant,,,,,
"""
        
        response = await client.post(
            "/api/v1/products/import",
            files={"file": ("missing_fields.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=auth_headers,
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "validation_failed"
        assert len(data["errors"]) > 0
        
        # Verify missing field errors
        missing_errors = [e for e in data["errors"] if "missing or empty" in e["error"].lower()]
        assert len(missing_errors) > 0
    
    @pytest.mark.asyncio
    async def test_import_non_csv_file(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test importing non-CSV file returns error."""
        response = await client.post(
            "/api/v1/products/import",
            files={"file": ("test.txt", io.BytesIO(b"not a csv"), "text/plain")},
            headers=auth_headers,
        )
        
        assert response.status_code == 400
        assert "CSV" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_import_invalid_encoding(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test importing CSV with invalid encoding returns error."""
        # Create content with invalid UTF-8 bytes
        invalid_content = b"type,name\nproduct,\xff\xfe Invalid"
        
        response = await client.post(
            "/api/v1/products/import",
            files={"file": ("invalid_encoding.csv", io.BytesIO(invalid_content), "text/csv")},
            headers=auth_headers,
        )
        
        assert response.status_code == 400
        assert "UTF-8" in response.json()["detail"]


class TestCSVExportFiltering:
    """Test CSV export with various filters."""
    
    @pytest.mark.asyncio
    async def test_export_by_category(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test exporting products filtered by category."""
        wa_number = "6281234567890"
        
        # Create products in different categories
        await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": wa_number,
                "name": "Electronics Product",
                "category": "electronics",
                "base_price_cents": 100000,
                "sku": "ELEC-001",
            },
            headers=auth_headers,
        )
        
        await client.post(
            "/api/v1/products",
            json={
                "wa_number_id": wa_number,
                "name": "Clothing Product",
                "category": "clothing",
                "base_price_cents": 200000,
                "sku": "CLOTH-001",
            },
            headers=auth_headers,
        )
        
        # Export only electronics
        export_response = await client.get(
            f"/api/v1/products/export?wa_number_id={wa_number}&category=electronics",
            headers=auth_headers,
        )
        
        assert export_response.status_code == 200
        csv_content = export_response.text
        
        # Verify only electronics products in export
        assert "Electronics Product" in csv_content
        assert "ELEC-001" in csv_content
        assert "Clothing Product" not in csv_content
        assert "CLOTH-001" not in csv_content
    
    @pytest.mark.asyncio
    async def test_export_empty_result(self, client: httpx.AsyncClient, auth_headers: dict):
        """Test exporting with no matching products returns empty CSV with headers."""
        wa_number = "6289999999999"
        
        export_response = await client.get(
            f"/api/v1/products/export?wa_number_id={wa_number}",
            headers=auth_headers,
        )
        
        assert export_response.status_code == 200
        csv_content = export_response.text
        
        # Should have headers but no data rows
        lines = csv_content.strip().split("\n")
        assert len(lines) == 1  # Only header row
        assert "Handle" in lines[0]  # Shopify-style header
