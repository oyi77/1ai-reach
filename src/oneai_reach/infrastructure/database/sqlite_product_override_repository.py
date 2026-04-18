"""SQLite implementation of ProductOverrideRepository."""

import sqlite3
from datetime import datetime
from typing import List, Optional

from oneai_reach.domain.models.product import ProductOverride
from oneai_reach.domain.repositories.product_repository import ProductOverrideRepository


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class NotFoundError(RepositoryError):
    """Exception raised when entity not found."""

    pass


class SQLiteProductOverrideRepository(ProductOverrideRepository):
    """SQLite implementation of ProductOverrideRepository.

    Provides data access for ProductOverride entities using SQLite database.
    Implements multi-tenant product override management for per-tenant pricing
    and visibility customization.
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

    def _row_to_override(self, row: sqlite3.Row) -> ProductOverride:
        """Convert database row to ProductOverride domain model."""
        data = dict(row)

        # Convert timestamps
        for field in ["created_at", "updated_at"]:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None

        # Convert boolean
        if "is_hidden" in data:
            data["is_hidden"] = bool(data["is_hidden"])

        return ProductOverride(**data)

    def get_by_id(self, override_id: str) -> Optional[ProductOverride]:
        """Get product override by ID."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM product_overrides WHERE id = ?", (override_id,)
            )
            row = cursor.fetchone()
            return self._row_to_override(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get override by id: {e}")
        finally:
            conn.close()

    def get_all(self, wa_number_id: str) -> List[ProductOverride]:
        """Get all product overrides for a WA number."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM product_overrides 
                WHERE wa_number_id = ?
                ORDER BY created_at DESC
            """,
                (wa_number_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_override(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get all overrides: {e}")
        finally:
            conn.close()

    def save(self, override: ProductOverride) -> ProductOverride:
        """Save new product override."""
        if override.id is not None:
            raise ValueError("Override already has an ID, use update() instead")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            now = datetime.now()
            override.created_at = now
            override.updated_at = now

            # Generate UUID for override ID
            import uuid
            override.id = str(uuid.uuid4())

            conn.execute(
                """
                INSERT INTO product_overrides (
                    id, wa_number_id, product_id, override_price_cents,
                    override_stock_quantity, is_hidden, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    override.id,
                    override.wa_number_id,
                    override.product_id,
                    override.override_price_cents,
                    override.override_stock_quantity,
                    1 if override.is_hidden else 0,
                    override.created_at.isoformat(),
                    override.updated_at.isoformat(),
                ),
            )

            conn.commit()
            return override
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(
                    f"Override for wa_number_id={override.wa_number_id} and product_id={override.product_id} already exists"
                )
            raise RepositoryError(f"Failed to save override: {e}")
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to save override: {e}")
        finally:
            conn.close()

    def update(self, override: ProductOverride) -> ProductOverride:
        """Update existing product override."""
        if override.id is None:
            raise ValueError("Override must have an ID to update")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            override.updated_at = datetime.now()

            cursor = conn.execute(
                """
                UPDATE product_overrides SET
                    wa_number_id = ?, product_id = ?, override_price_cents = ?,
                    override_stock_quantity = ?, is_hidden = ?, updated_at = ?
                WHERE id = ?
            """,
                (
                    override.wa_number_id,
                    override.product_id,
                    override.override_price_cents,
                    override.override_stock_quantity,
                    1 if override.is_hidden else 0,
                    override.updated_at.isoformat(),
                    override.id,
                ),
            )

            if cursor.rowcount == 0:
                conn.rollback()
                raise NotFoundError(f"Override not found: {override.id}")

            conn.commit()
            return override
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(
                    f"Override for wa_number_id={override.wa_number_id} and product_id={override.product_id} already exists"
                )
            raise RepositoryError(f"Failed to update override: {e}")
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to update override: {e}")
        finally:
            conn.close()

    def delete(self, override_id: str) -> bool:
        """Delete product override by ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute(
                "DELETE FROM product_overrides WHERE id = ?", (override_id,)
            )

            if cursor.rowcount == 0:
                conn.rollback()
                return False

            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to delete override: {e}")
        finally:
            conn.close()

    def get_by_product(
        self, wa_number_id: str, product_id: str
    ) -> Optional[ProductOverride]:
        """Get override for a specific product and WA number.

        This is the primary lookup method for tenant-specific overrides.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM product_overrides 
                WHERE wa_number_id = ? AND product_id = ?
            """,
                (wa_number_id, product_id),
            )
            row = cursor.fetchone()
            return self._row_to_override(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get override by product: {e}")
        finally:
            conn.close()

    def search(
        self, wa_number_id: str, query: str, limit: int = 10
    ) -> List[ProductOverride]:
        """Search product overrides by product name or override fields.

        Joins with products table to enable search by product name.
        """
        conn = self._connect()
        try:
            search_pattern = f"%{query}%"
            cursor = conn.execute(
                """
                SELECT po.* FROM product_overrides po
                JOIN products p ON po.product_id = p.id
                WHERE po.wa_number_id = ? 
                AND (
                    p.name LIKE ? OR 
                    p.sku LIKE ? OR
                    p.category LIKE ?
                )
                ORDER BY 
                    CASE 
                        WHEN p.name LIKE ? THEN 1
                        WHEN p.sku LIKE ? THEN 2
                        ELSE 3
                    END,
                    po.created_at DESC
                LIMIT ?
            """,
                (
                    wa_number_id,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    limit,
                ),
            )
            rows = cursor.fetchall()
            return [self._row_to_override(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to search overrides: {e}")
        finally:
            conn.close()
