"""SQLite implementation of ConversationRepository."""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from oneai_reach.domain.models.conversation import (
    Conversation,
    ConversationStatus,
    EngineMode,
)
from oneai_reach.domain.repositories.conversation_repository import (
    ConversationRepository,
)


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class NotFoundError(RepositoryError):
    """Exception raised when entity not found."""

    pass


class SQLiteConversationRepository(ConversationRepository):
    """SQLite implementation of ConversationRepository.

    Provides data access for Conversation entities using SQLite database.
    Maintains schema compatibility with existing 1ai_reach.db structure.
    """

    def __init__(self, db_path: str):
        """Initialize repository with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """Create database connection with row factory."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self):
        """Initialize database schema if tables don't exist."""
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wa_number_id TEXT,
                    contact_phone TEXT NOT NULL,
                    contact_name TEXT,
                    lead_id TEXT,
                    engine_mode TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    stage TEXT DEFAULT 'discovery',
                    manual_mode INTEGER DEFAULT 0,
                    test_mode INTEGER DEFAULT 0,
                    last_message_at TEXT,
                    message_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id)
                )
            """)
            conn.commit()
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    def _row_to_conversation(self, row: sqlite3.Row) -> Conversation:
        """Convert database row to Conversation domain model."""
        data = dict(row)

        for field in ["last_message_at", "created_at", "updated_at"]:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None

        if data.get("engine_mode"):
            data["engine_mode"] = EngineMode(data["engine_mode"])

        if data.get("status"):
            data["status"] = ConversationStatus(data["status"])

        data["manual_mode"] = bool(data.get("manual_mode", 0))
        data["test_mode"] = bool(data.get("test_mode", 0))

        return Conversation(**data)

    def get_by_id(self, conversation_id: int) -> Optional[Conversation]:
        """Get conversation by ID."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            )
            row = cursor.fetchone()
            return self._row_to_conversation(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get conversation by id: {e}")
        finally:
            conn.close()

    def get_all(self) -> List[Conversation]:
        """Get all conversations."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM conversations ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
            return [self._row_to_conversation(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get all conversations: {e}")
        finally:
            conn.close()

    def save(self, conversation: Conversation) -> Conversation:
        """Save new conversation."""
        if conversation.id is not None:
            raise ValueError("Conversation already has an ID, use update() instead")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            now = datetime.now()
            conversation.created_at = now
            conversation.updated_at = now

            cursor = conn.execute(
                """
                INSERT INTO conversations (
                    wa_number_id, contact_phone, contact_name, lead_id,
                    engine_mode, status, manual_mode, test_mode,
                    last_message_at, message_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    conversation.wa_number_id,
                    conversation.contact_phone,
                    conversation.contact_name,
                    conversation.lead_id,
                    conversation.engine_mode.value,
                    conversation.status.value,
                    1 if conversation.manual_mode else 0,
                    1 if conversation.test_mode else 0,
                    conversation.last_message_at.isoformat()
                    if conversation.last_message_at
                    else None,
                    conversation.message_count,
                    conversation.created_at.isoformat(),
                    conversation.updated_at.isoformat(),
                ),
            )

            conversation.id = cursor.lastrowid
            conn.commit()
            return conversation
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to save conversation: {e}")
        finally:
            conn.close()

    def update(self, conversation: Conversation) -> Conversation:
        """Update existing conversation."""
        if conversation.id is None:
            raise ValueError("Conversation must have an ID to update")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            conversation.updated_at = datetime.now()

            cursor = conn.execute(
                """
                UPDATE conversations SET
                    wa_number_id = ?, contact_phone = ?, contact_name = ?,
                    lead_id = ?, engine_mode = ?, status = ?,
                    manual_mode = ?, test_mode = ?, last_message_at = ?,
                    message_count = ?, updated_at = ?
                WHERE id = ?
            """,
                (
                    conversation.wa_number_id,
                    conversation.contact_phone,
                    conversation.contact_name,
                    conversation.lead_id,
                    conversation.engine_mode.value,
                    conversation.status.value,
                    1 if conversation.manual_mode else 0,
                    1 if conversation.test_mode else 0,
                    conversation.last_message_at.isoformat()
                    if conversation.last_message_at
                    else None,
                    conversation.message_count,
                    conversation.updated_at.isoformat(),
                    conversation.id,
                ),
            )

            if cursor.rowcount == 0:
                conn.rollback()
                raise NotFoundError(f"Conversation not found: {conversation.id}")

            conn.commit()
            return conversation
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to update conversation: {e}")
        finally:
            conn.close()

    def delete(self, conversation_id: int) -> bool:
        """Delete conversation by ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to delete conversation: {e}")
        finally:
            conn.close()

    def find_by_phone(
        self, wa_number_id: str, contact_phone: str
    ) -> Optional[Conversation]:
        """Find active conversation by WA number and contact phone."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM conversations 
                WHERE wa_number_id = ? AND contact_phone = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (wa_number_id, contact_phone, ConversationStatus.ACTIVE.value),
            )
            row = cursor.fetchone()
            return self._row_to_conversation(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find conversation by phone: {e}")
        finally:
            conn.close()

    def find_by_status(self, status: ConversationStatus) -> List[Conversation]:
        """Find conversations by status."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM conversations 
                WHERE status = ?
                ORDER BY last_message_at DESC
            """,
                (status.value,),
            )
            rows = cursor.fetchall()
            return [self._row_to_conversation(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find conversations by status: {e}")
        finally:
            conn.close()

    def find_active(self, wa_number_id: Optional[str] = None) -> List[Conversation]:
        """Find all active conversations."""
        conn = self._connect()
        try:
            if wa_number_id:
                cursor = conn.execute(
                    """
                    SELECT * FROM conversations 
                    WHERE status = ? AND wa_number_id = ?
                    ORDER BY last_message_at DESC
                """,
                    (ConversationStatus.ACTIVE.value, wa_number_id),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM conversations 
                    WHERE status = ?
                    ORDER BY last_message_at DESC
                """,
                    (ConversationStatus.ACTIVE.value,),
                )

            rows = cursor.fetchall()
            return [self._row_to_conversation(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find active conversations: {e}")
        finally:
            conn.close()

    def find_by_lead_id(self, lead_id: str) -> List[Conversation]:
        """Find conversations linked to a lead."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM conversations 
                WHERE lead_id = ?
                ORDER BY created_at DESC
            """,
                (lead_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_conversation(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find conversations by lead_id: {e}")
        finally:
            conn.close()

    def find_stale(self, hours: int = 48) -> List[Conversation]:
        """Find stale conversations (inactive for specified hours)."""
        conn = self._connect()
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            cursor = conn.execute(
                """
                SELECT * FROM conversations 
                WHERE status = ? AND last_message_at < ?
                ORDER BY last_message_at ASC
            """,
                (ConversationStatus.ACTIVE.value, cutoff.isoformat()),
            )
            rows = cursor.fetchall()
            return [self._row_to_conversation(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find stale conversations: {e}")
        finally:
            conn.close()

    def find_by_engine_mode(self, engine_mode: EngineMode) -> List[Conversation]:
        """Find conversations by engine mode."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM conversations 
                WHERE engine_mode = ?
                ORDER BY created_at DESC
            """,
                (engine_mode.value,),
            )
            rows = cursor.fetchall()
            return [self._row_to_conversation(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find conversations by engine_mode: {e}")
        finally:
            conn.close()

    def count_by_status(self) -> dict[ConversationStatus, int]:
        """Count conversations by status."""
        conn = self._connect()
        try:
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count 
                FROM conversations 
                GROUP BY status
            """)
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                try:
                    status = ConversationStatus(row["status"])
                    result[status] = row["count"]
                except ValueError:
                    pass
            return result
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to count conversations by status: {e}")
        finally:
            conn.close()

    def count_by_wa_number(self, wa_number_id: str) -> int:
        """Count conversations for a specific WA number."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM conversations 
                WHERE wa_number_id = ?
            """,
                (wa_number_id,),
            )
            row = cursor.fetchone()
            return row["count"] if row else 0
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to count conversations by wa_number: {e}")
        finally:
            conn.close()
