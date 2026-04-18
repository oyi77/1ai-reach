"""SQLite implementation of InventoryRepository."""

import sqlite3
from datetime import datetime
from typing import List, Optional

from oneai_reach.domain.models.product import Inventory
from oneai_reach.domain.repositories.product_repository import InventoryRepository


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class NotFoundError(RepositoryError):
    """Exception raised when entity not found."""

    pass


class SQLiteInventoryRepository(InventoryRepository):
    """SQLite implementation of InventoryRepository.

    Provides data access for Inventory entities using SQLite database.
    Supports stock adjustment, reservation, and release operations.
    Implements atomic inventory tracking with transaction safety.
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

    def _row_to_inventory(self, row: sqlite3.Row) -> Inventory:
        """Convert database row to Inventory domain model."""
        data = dict(row)

        if "quantity_available" in data:
            data["on_hand"] = data.pop("quantity_available")
        if "quantity_reserved" in data:
            data["reserved"] = data.pop("quantity_reserved")
        if "quantity_sold" in data:
            data["sold"] = data.pop("quantity_sold")

        for field in ["created_at", "updated_at", "last_restocked_at"]:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None

        data.pop("last_restocked_at", None)

        return Inventory(**data)

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        """Get inventory record by ID."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM inventory WHERE id = ?", (inventory_id,)
            )
            row = cursor.fetchone()
            return self._row_to_inventory(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get inventory by id: {e}")
        finally:
            conn.close()

    def get_all(self, wa_number_id: str) -> List[Inventory]:
        """Get all inventory records for a WA number.

        Joins with product_variants and products to filter by wa_number_id.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT i.* FROM inventory i
                INNER JOIN product_variants pv ON i.variant_id = pv.id
                INNER JOIN products p ON pv.product_id = p.id
                WHERE p.wa_number_id = ?
                ORDER BY i.created_at DESC
            """,
                (wa_number_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_inventory(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get all inventory: {e}")
        finally:
            conn.close()

    def save(self, inventory: Inventory) -> Inventory:
        """Save new inventory record."""
        if inventory.id is not None:
            raise ValueError("Inventory already has an ID, use update() instead")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            now = datetime.now()
            inventory.created_at = now
            inventory.updated_at = now

            import uuid
            inventory.id = str(uuid.uuid4())

            conn.execute(
                """
                INSERT INTO inventory (
                    id, variant_id, quantity_available, quantity_reserved,
                    quantity_sold, reorder_level, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    inventory.id,
                    inventory.variant_id,
                    inventory.on_hand,
                    inventory.reserved,
                    inventory.sold,
                    inventory.reorder_level,
                    inventory.created_at.isoformat(),
                    inventory.updated_at.isoformat(),
                ),
            )

            conn.commit()
            return inventory
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Inventory for variant {inventory.variant_id} already exists")
            raise RepositoryError(f"Failed to save inventory: {e}")
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to save inventory: {e}")
        finally:
            conn.close()

    def update(self, inventory: Inventory) -> Inventory:
        """Update existing inventory record."""
        if inventory.id is None:
            raise ValueError("Inventory must have an ID to update")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            inventory.updated_at = datetime.now()

            cursor = conn.execute(
                """
                UPDATE inventory SET
                    variant_id = ?, quantity_available = ?, quantity_reserved = ?,
                    quantity_sold = ?, reorder_level = ?, updated_at = ?
                WHERE id = ?
            """,
                (
                    inventory.variant_id,
                    inventory.on_hand,
                    inventory.reserved,
                    inventory.sold,
                    inventory.reorder_level,
                    inventory.updated_at.isoformat(),
                    inventory.id,
                ),
            )

            if cursor.rowcount == 0:
                conn.rollback()
                raise NotFoundError(f"Inventory not found: {inventory.id}")

            conn.commit()
            return inventory
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Inventory for variant {inventory.variant_id} already exists")
            raise RepositoryError(f"Failed to update inventory: {e}")
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to update inventory: {e}")
        finally:
            conn.close()

    def delete(self, inventory_id: str) -> bool:
        """Delete inventory record by ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute("DELETE FROM inventory WHERE id = ?", (inventory_id,))
            
            if cursor.rowcount == 0:
                conn.rollback()
                return False

            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to delete inventory: {e}")
        finally:
            conn.close()

    def get_by_variant(self, variant_id: str) -> Optional[Inventory]:
        """Get inventory record for a product variant."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM inventory WHERE variant_id = ?", (variant_id,)
            )
            row = cursor.fetchone()
            return self._row_to_inventory(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get inventory by variant: {e}")
        finally:
            conn.close()

    def search(
        self, wa_number_id: str, query: str, limit: int = 10
    ) -> List[Inventory]:
        """Search inventory records by product name or SKU.

        Joins with product_variants and products to search across related data.
        """
        conn = self._connect()
        try:
            search_pattern = f"%{query}%"
            cursor = conn.execute(
                """
                SELECT i.* FROM inventory i
                INNER JOIN product_variants pv ON i.variant_id = pv.id
                INNER JOIN products p ON pv.product_id = p.id
                WHERE p.wa_number_id = ? 
                AND (
                    p.name LIKE ? OR 
                    p.sku LIKE ? OR 
                    pv.sku LIKE ? OR
                    pv.variant_name LIKE ?
                )
                ORDER BY 
                    CASE 
                        WHEN p.name LIKE ? THEN 1
                        WHEN pv.sku LIKE ? THEN 2
                        WHEN p.sku LIKE ? THEN 3
                        ELSE 4
                    END,
                    i.created_at DESC
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
            return [self._row_to_inventory(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to search inventory: {e}")
        finally:
            conn.close()

    def adjust_stock(self, variant_id: str, delta: int, reason: str) -> Inventory:
        """Adjust stock quantity for a variant.

        Args:
            variant_id: Product variant ID
            delta: Change in stock quantity (positive for increase, negative for decrease)
            reason: Reason for adjustment (e.g., "sale", "restock", "damage")

        Returns:
            Updated Inventory object

        Raises:
            NotFoundError: If inventory record not found
            ValueError: If adjustment would result in negative stock
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute(
                "SELECT * FROM inventory WHERE variant_id = ?", (variant_id,)
            )
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                raise NotFoundError(f"Inventory not found for variant: {variant_id}")

            inventory = self._row_to_inventory(row)

            new_on_hand = inventory.on_hand + delta
            if new_on_hand < 0:
                conn.rollback()
                raise ValueError(
                    f"Adjustment would result in negative stock: {inventory.on_hand} + {delta} = {new_on_hand}"
                )

            inventory.on_hand = new_on_hand
            inventory.updated_at = datetime.now()

            conn.execute(
                """
                UPDATE inventory SET
                    quantity_available = ?, updated_at = ?
                WHERE variant_id = ?
            """,
                (
                    inventory.on_hand,
                    inventory.updated_at.isoformat(),
                    variant_id,
                ),
            )

            conn.commit()
            return inventory
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to adjust stock: {e}")
        finally:
            conn.close()

    def reserve_stock(self, variant_id: str, quantity: int) -> Inventory:
        """Reserve stock for a variant (e.g., for pending orders).

        Args:
            variant_id: Product variant ID
            quantity: Quantity to reserve (must be positive)

        Returns:
            Updated Inventory object

        Raises:
            NotFoundError: If inventory record not found
            ValueError: If insufficient available stock
        """
        if quantity <= 0:
            raise ValueError("Reserve quantity must be positive")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute(
                "SELECT * FROM inventory WHERE variant_id = ?", (variant_id,)
            )
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                raise NotFoundError(f"Inventory not found for variant: {variant_id}")

            inventory = self._row_to_inventory(row)

            if inventory.available < quantity:
                conn.rollback()
                raise ValueError(
                    f"Insufficient available stock: requested {quantity}, available {inventory.available}"
                )

            inventory.reserved += quantity
            inventory.updated_at = datetime.now()

            conn.execute(
                """
                UPDATE inventory SET
                    quantity_reserved = ?, updated_at = ?
                WHERE variant_id = ?
            """,
                (
                    inventory.reserved,
                    inventory.updated_at.isoformat(),
                    variant_id,
                ),
            )

            conn.commit()
            return inventory
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to reserve stock: {e}")
        finally:
            conn.close()

    def release_stock(self, variant_id: str, quantity: int) -> Inventory:
        """Release reserved stock for a variant (e.g., cancelled order).

        Args:
            variant_id: Product variant ID
            quantity: Quantity to release (must be positive)

        Returns:
            Updated Inventory object

        Raises:
            NotFoundError: If inventory record not found
            ValueError: If release quantity exceeds reserved stock
        """
        if quantity <= 0:
            raise ValueError("Release quantity must be positive")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute(
                "SELECT * FROM inventory WHERE variant_id = ?", (variant_id,)
            )
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                raise NotFoundError(f"Inventory not found for variant: {variant_id}")

            inventory = self._row_to_inventory(row)

            if inventory.reserved < quantity:
                conn.rollback()
                raise ValueError(
                    f"Release quantity exceeds reserved stock: requested {quantity}, reserved {inventory.reserved}"
                )

            inventory.reserved -= quantity
            inventory.updated_at = datetime.now()

            conn.execute(
                """
                UPDATE inventory SET
                    quantity_reserved = ?, updated_at = ?
                WHERE variant_id = ?
            """,
                (
                    inventory.reserved,
                    inventory.updated_at.isoformat(),
                    variant_id,
                ),
            )

            conn.commit()
            return inventory
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to release stock: {e}")
        finally:
            conn.close()
