"""SQLite implementation of ProductVariantRepository."""

import sqlite3
from datetime import datetime
from typing import List, Optional

from oneai_reach.domain.models.product import ProductVariant, ProductStatus
from oneai_reach.domain.repositories.product_repository import ProductVariantRepository


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class NotFoundError(RepositoryError):
    """Exception raised when entity not found."""

    pass


class SQLiteProductVariantRepository(ProductVariantRepository):
    """SQLite implementation of ProductVariantRepository.

    Provides data access for ProductVariant entities using SQLite database.
    Supports variant-specific queries including SKU lookup and product filtering.
    Handles physical properties (weight, dimensions) and pricing per variant.
    """

    def __init__(self, db_path: str):
        """Initialize repository with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Create database connection with row factory."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _row_to_variant(self, row: sqlite3.Row) -> ProductVariant:
        """Convert database row to ProductVariant domain model."""
        data = dict(row)

        # Convert timestamps
        for field in ["created_at", "updated_at"]:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None

        # Convert enum
        if data.get("status"):
            data["status"] = ProductStatus(data["status"])

        return ProductVariant(**data)

    def get_by_id(self, variant_id: str) -> Optional[ProductVariant]:
        """Get product variant by ID."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM product_variants WHERE id = ?", (variant_id,)
            )
            row = cursor.fetchone()
            return self._row_to_variant(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get variant by id: {e}")
        finally:
            conn.close()

    def get_all(self, product_id: str) -> List[ProductVariant]:
        """Get all variants for a product."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM product_variants 
                WHERE product_id = ?
                ORDER BY created_at DESC
            """,
                (product_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_variant(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get all variants: {e}")
        finally:
            conn.close()

    def save(self, variant: ProductVariant) -> ProductVariant:
        """Save new product variant."""
        if variant.id is not None:
            raise ValueError("Variant already has an ID, use update() instead")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            now = datetime.now()
            variant.created_at = now
            variant.updated_at = now

            # Generate UUID for variant ID
            import uuid
            variant.id = str(uuid.uuid4())

            conn.execute(
                """
                INSERT INTO product_variants (
                    id, product_id, sku, variant_name, price_cents,
                    weight_grams, dimensions_json, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    variant.id,
                    variant.product_id,
                    variant.sku,
                    variant.variant_name,
                    variant.price_cents,
                    variant.weight_grams,
                    variant.dimensions_json,
                    variant.status.value,
                    variant.created_at.isoformat(),
                    variant.updated_at.isoformat(),
                ),
            )

            conn.commit()
            return variant
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Variant with SKU {variant.sku} already exists")
            raise RepositoryError(f"Failed to save variant: {e}")
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to save variant: {e}")
        finally:
            conn.close()

    def update(self, variant: ProductVariant) -> ProductVariant:
        """Update existing product variant."""
        if variant.id is None:
            raise ValueError("Variant must have an ID to update")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            variant.updated_at = datetime.now()

            cursor = conn.execute(
                """
                UPDATE product_variants SET
                    product_id = ?, sku = ?, variant_name = ?,
                    price_cents = ?, weight_grams = ?, dimensions_json = ?,
                    status = ?, updated_at = ?
                WHERE id = ?
            """,
                (
                    variant.product_id,
                    variant.sku,
                    variant.variant_name,
                    variant.price_cents,
                    variant.weight_grams,
                    variant.dimensions_json,
                    variant.status.value,
                    variant.updated_at.isoformat(),
                    variant.id,
                ),
            )

            if cursor.rowcount == 0:
                conn.rollback()
                raise NotFoundError(f"Variant not found: {variant.id}")

            conn.commit()
            return variant
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Variant with SKU {variant.sku} already exists")
            raise RepositoryError(f"Failed to update variant: {e}")
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to update variant: {e}")
        finally:
            conn.close()

    def delete(self, variant_id: str) -> bool:
        """Delete product variant by ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute("DELETE FROM product_variants WHERE id = ?", (variant_id,))
            
            if cursor.rowcount == 0:
                conn.rollback()
                return False

            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to delete variant: {e}")
        finally:
            conn.close()

    def search(
        self, product_id: str, query: str, limit: int = 10
    ) -> List[ProductVariant]:
        """Search variants within a product by name or SKU using LIKE."""
        conn = self._connect()
        try:
            search_pattern = f"%{query}%"
            cursor = conn.execute(
                """
                SELECT * FROM product_variants
                WHERE product_id = ? 
                AND (
                    variant_name LIKE ? OR 
                    sku LIKE ?
                )
                ORDER BY 
                    CASE 
                        WHEN variant_name LIKE ? THEN 1
                        WHEN sku LIKE ? THEN 2
                        ELSE 3
                    END,
                    created_at DESC
                LIMIT ?
            """,
                (
                    product_id,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    limit,
                ),
            )
            rows = cursor.fetchall()
            return [self._row_to_variant(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to search variants: {e}")
        finally:
            conn.close()

    def find_by_product(self, product_id: str) -> List[ProductVariant]:
        """Find all variants for a specific product.

        This is an alias for get_all() for semantic clarity.

        Args:
            product_id: Product ID to filter by

        Returns:
            List of ProductVariant objects for this product
        """
        return self.get_all(product_id)

    def find_by_sku(self, sku: str) -> Optional[ProductVariant]:
        """Find variant by SKU.

        Args:
            sku: Unique SKU identifier

        Returns:
            ProductVariant object if found, None otherwise
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM product_variants WHERE sku = ?", (sku,)
            )
            row = cursor.fetchone()
            return self._row_to_variant(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find variant by SKU: {e}")
        finally:
            conn.close()
