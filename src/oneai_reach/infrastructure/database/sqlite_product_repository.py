"""SQLite implementation of ProductRepository."""

import sqlite3
from datetime import datetime
from typing import List, Optional

from oneai_reach.domain.models.product import Product, ProductStatus, VisibilityStatus
from oneai_reach.domain.repositories.product_repository import ProductRepository


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class NotFoundError(RepositoryError):
    """Exception raised when entity not found."""

    pass


class SQLiteProductRepository(ProductRepository):
    """SQLite implementation of ProductRepository.

    Provides data access for Product entities using SQLite database.
    Supports FTS5 full-text search for product catalog queries.
    Implements multi-tenant product management with override support.
    """

    def __init__(self, db_path: str):
        """Initialize repository with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema if tables don't exist."""
        conn = self._connect()
        try:
            # wa_numbers table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wa_numbers (
                    id TEXT PRIMARY KEY,
                    session_name TEXT UNIQUE NOT NULL,
                    phone TEXT,
                    label TEXT,
                    mode TEXT DEFAULT 'cs',
                    kb_enabled INTEGER DEFAULT 1,
                    auto_reply INTEGER DEFAULT 1,
                    persona TEXT,
                    status TEXT DEFAULT 'inactive',
                    webhook_url TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            
            # products table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    wa_number_id TEXT,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    base_price_cents INTEGER NOT NULL,
                    currency TEXT DEFAULT 'IDR',
                    sku TEXT UNIQUE,
                    status TEXT DEFAULT 'active',
                    visibility TEXT DEFAULT 'public',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            
            # product_variants table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_variants (
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    sku TEXT UNIQUE,
                    variant_name TEXT NOT NULL,
                    price_cents INTEGER NOT NULL,
                    weight_grams INTEGER,
                    dimensions_json TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
                )
            """)
            
            # inventory table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id TEXT PRIMARY KEY,
                    variant_id TEXT NOT NULL UNIQUE,
                    quantity_available INTEGER DEFAULT 0,
                    quantity_reserved INTEGER DEFAULT 0,
                    quantity_sold INTEGER DEFAULT 0,
                    reorder_level INTEGER DEFAULT 10,
                    last_restocked_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (variant_id) REFERENCES product_variants(id) ON DELETE CASCADE
                )
            """)
            
            # product_overrides table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_overrides (
                    id TEXT PRIMARY KEY,
                    wa_number_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    override_price_cents INTEGER,
                    override_stock_quantity INTEGER,
                    is_hidden INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(wa_number_id, product_id),
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
                )
            """)
            
            # product_images table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_images (
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    alt_text TEXT,
                    display_order INTEGER DEFAULT 0,
                    is_primary INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_variants_product ON product_variants(product_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_variants_sku ON product_variants(sku)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_variant ON inventory(variant_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_overrides_tenant_product ON product_overrides(wa_number_id, product_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_images_product ON product_images(product_id)")
            
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        """Create database connection with row factory."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _row_to_product(self, row: sqlite3.Row) -> Product:
        """Convert database row to Product domain model."""
        data = dict(row)

        # Convert timestamps
        for field in ["created_at", "updated_at"]:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None

        # Convert enums
        if data.get("status"):
            data["status"] = ProductStatus(data["status"])
        if data.get("visibility"):
            data["visibility"] = VisibilityStatus(data["visibility"])

        return Product(**data)

    def get_by_id(self, product_id: str) -> Optional[Product]:
        """Get product by ID."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            )
            row = cursor.fetchone()
            return self._row_to_product(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get product by id: {e}")
        finally:
            conn.close()

    def get_all(self, wa_number_id: str) -> List[Product]:
        """Get all visible products for a WA number."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT p.* FROM products p
                LEFT JOIN product_overrides po
                    ON p.id = po.product_id AND po.wa_number_id = ?
                WHERE (p.wa_number_id = ? OR po.wa_number_id = ?)
                  AND COALESCE(po.is_hidden, 0) = 0
                ORDER BY p.created_at DESC
            """,
                (wa_number_id, wa_number_id, wa_number_id),
            )
            rows = cursor.fetchall()
            return [self._row_to_product(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get all products: {e}")
        finally:
            conn.close()

    def save(self, product: Product) -> Product:
        """Save new product."""
        if product.id is not None:
            raise ValueError("Product already has an ID, use update() instead")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            now = datetime.now()
            product.created_at = now
            product.updated_at = now

            # Generate UUID for product ID
            import uuid
            product.id = str(uuid.uuid4())

            conn.execute(
                """
                INSERT INTO products (
                    id, wa_number_id, name, description, category,
                    base_price_cents, currency, sku, status, visibility,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    product.id,
                    product.wa_number_id,
                    product.name,
                    product.description,
                    product.category,
                    product.base_price_cents,
                    product.currency,
                    product.sku,
                    product.status.value,
                    product.visibility.value,
                    product.created_at.isoformat(),
                    product.updated_at.isoformat(),
                ),
            )

            conn.commit()
            return product
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Product with SKU {product.sku} already exists")
            raise RepositoryError(f"Failed to save product: {e}")
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to save product: {e}")
        finally:
            conn.close()

    def update(self, product: Product) -> Product:
        """Update existing product."""
        if product.id is None:
            raise ValueError("Product must have an ID to update")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            product.updated_at = datetime.now()

            cursor = conn.execute(
                """
                UPDATE products SET
                    wa_number_id = ?, name = ?, description = ?,
                    category = ?, base_price_cents = ?, currency = ?,
                    sku = ?, status = ?, visibility = ?,
                    updated_at = ?
                WHERE id = ?
            """,
                (
                    product.wa_number_id,
                    product.name,
                    product.description,
                    product.category,
                    product.base_price_cents,
                    product.currency,
                    product.sku,
                    product.status.value,
                    product.visibility.value,
                    product.updated_at.isoformat(),
                    product.id,
                ),
            )

            if cursor.rowcount == 0:
                conn.rollback()
                raise NotFoundError(f"Product not found: {product.id}")

            conn.commit()
            return product
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Product with SKU {product.sku} already exists")
            raise RepositoryError(f"Failed to update product: {e}")
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to update product: {e}")
        finally:
            conn.close()

    def delete(self, product_id: str) -> bool:
        """Delete product by ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            
            if cursor.rowcount == 0:
                conn.rollback()
                return False

            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to delete product: {e}")
        finally:
            conn.close()

    def search(
        self, wa_number_id: str, query: str, limit: int = 10
    ) -> List[Product]:
        """Search products by name, description, category, or SKU using LIKE."""
        conn = self._connect()
        try:
            search_pattern = f"%{query}%"
            cursor = conn.execute(
                """
                SELECT * FROM products
                WHERE wa_number_id = ?
                AND visibility != 'hidden'
                AND (
                    name LIKE ? OR 
                    description LIKE ? OR 
                    category LIKE ? OR 
                    sku LIKE ?
                )
                ORDER BY 
                    CASE 
                        WHEN name LIKE ? THEN 1
                        WHEN sku LIKE ? THEN 2
                        WHEN category LIKE ? THEN 3
                        ELSE 4
                    END,
                    created_at DESC
                LIMIT ?
            """,
                (
                    wa_number_id,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    limit,
                ),
            )
            rows = cursor.fetchall()
            return [self._row_to_product(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to search products: {e}")
        finally:
            conn.close()

    def get_effective_product(
        self, wa_number_id: str, product_id: str
    ) -> Optional[Product]:
        """Get product with overrides merged for multi-tenancy.

        Retrieves the base product and applies any ProductOverride
        entries for the given WA number, returning the merged result.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT 
                    p.*,
                    COALESCE(po.override_price_cents, p.base_price_cents) as effective_price_cents,
                    COALESCE(po.is_hidden, 0) as is_hidden
                FROM products p
                LEFT JOIN product_overrides po 
                    ON p.id = po.product_id AND po.wa_number_id = ?
                WHERE p.id = ?
            """,
                (wa_number_id, product_id),
            )
            row = cursor.fetchone()
            if not row:
                return None

            # Convert row to product
            product = self._row_to_product(row)

            # Apply override price if present
            if row["effective_price_cents"] != product.base_price_cents:
                product.base_price_cents = row["effective_price_cents"]

            # Apply visibility override if hidden
            if row["is_hidden"] == 1:
                product.visibility = VisibilityStatus.HIDDEN

            return product
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get effective product: {e}")
        finally:
            conn.close()

    def add_image(
        self,
        product_id: str,
        image_url: str,
        alt_text: Optional[str] = None,
        is_primary: bool = False,
    ) -> str:
        """Add image metadata to product_images table.

        Args:
            product_id: Product identifier
            image_url: URL/path to the image file
            alt_text: Optional alt text for accessibility
            is_primary: Whether this is the primary product image

        Returns:
            Image ID

        Raises:
            RepositoryError: If image cannot be saved
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            # Generate UUID for image ID
            import uuid
            image_id = str(uuid.uuid4())

            # Get next display order
            cursor = conn.execute(
                "SELECT COALESCE(MAX(display_order), -1) + 1 FROM product_images WHERE product_id = ?",
                (product_id,),
            )
            display_order = cursor.fetchone()[0]

            # If this is primary, unset other primary images
            if is_primary:
                conn.execute(
                    "UPDATE product_images SET is_primary = 0 WHERE product_id = ?",
                    (product_id,),
                )

            # Insert image metadata
            conn.execute(
                """
                INSERT INTO product_images (
                    id, product_id, image_url, alt_text, display_order, is_primary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    image_id,
                    product_id,
                    image_url,
                    alt_text,
                    display_order,
                    1 if is_primary else 0,
                    datetime.now().isoformat(),
                ),
            )

            conn.commit()
            return image_id

        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to add image: {e}")
        finally:
            conn.close()
