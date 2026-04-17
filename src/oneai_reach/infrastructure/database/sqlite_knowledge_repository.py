"""SQLite implementation of KnowledgeRepository."""

import sqlite3
from datetime import datetime
from typing import List, Optional

from oneai_reach.domain.models.knowledge import (
    KnowledgeEntry,
    KnowledgeCategory,
)
from oneai_reach.domain.repositories.knowledge_repository import (
    KnowledgeRepository,
)


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class NotFoundError(RepositoryError):
    """Exception raised when entity not found."""

    pass


class SQLiteKnowledgeRepository(KnowledgeRepository):
    """SQLite implementation of KnowledgeRepository.

    Provides data access for KnowledgeEntry entities using SQLite database.
    Maintains schema compatibility with existing 1ai_reach.db structure.
    Supports FTS5 full-text search for knowledge base queries.
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
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wa_number_id TEXT,
                    category TEXT,
                    question TEXT,
                    answer TEXT,
                    content TEXT,
                    tags TEXT,
                    priority INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (wa_number_id) REFERENCES wa_numbers(id)
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts 
                USING fts5(question, answer, content, content='knowledge_base', content_rowid='id')
            """)
            conn.commit()
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    def _row_to_entry(self, row: sqlite3.Row) -> KnowledgeEntry:
        """Convert database row to KnowledgeEntry domain model."""
        data = dict(row)

        for field in ["created_at", "updated_at"]:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None

        if data.get("category"):
            data["category"] = KnowledgeCategory(data["category"])

        return KnowledgeEntry(**data)

    def _sync_fts_row(
        self, conn: sqlite3.Connection, entry_id: int, is_new: bool = False
    ):
        """Sync FTS5 index for a knowledge entry."""
        if not is_new:
            try:
                conn.execute(
                    """
                    INSERT INTO kb_fts(kb_fts, rowid, question, answer, content) 
                    SELECT 'delete', id, question, answer, content 
                    FROM knowledge_base WHERE id = ?
                """,
                    (entry_id,),
                )
            except sqlite3.DatabaseError:
                conn.execute("INSERT INTO kb_fts(kb_fts) VALUES('rebuild')")

        conn.execute(
            """
            INSERT INTO kb_fts(rowid, question, answer, content) 
            SELECT id, question, answer, content 
            FROM knowledge_base WHERE id = ?
        """,
            (entry_id,),
        )

    def _sync_fts_delete(
        self,
        conn: sqlite3.Connection,
        entry_id: int,
        question: str,
        answer: str,
        content: str,
    ):
        """Remove FTS5 row for deleted entry."""
        conn.execute(
            """
            INSERT INTO kb_fts(kb_fts, rowid, question, answer, content) 
            VALUES('delete', ?, ?, ?, ?)
        """,
            (entry_id, question, answer, content),
        )

    def get_by_id(self, entry_id: int) -> Optional[KnowledgeEntry]:
        """Get knowledge entry by ID."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM knowledge_base WHERE id = ?", (entry_id,)
            )
            row = cursor.fetchone()
            return self._row_to_entry(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get knowledge entry by id: {e}")
        finally:
            conn.close()

    def get_all(self, wa_number_id: str) -> List[KnowledgeEntry]:
        """Get all knowledge entries for a WA number."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM knowledge_base 
                WHERE wa_number_id = ?
                ORDER BY priority DESC, created_at DESC
            """,
                (wa_number_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get all knowledge entries: {e}")
        finally:
            conn.close()

    def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """Save new knowledge entry."""
        if entry.id is not None:
            raise ValueError("Entry already has an ID, use update() instead")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            now = datetime.now()
            entry.created_at = now
            entry.updated_at = now

            cursor = conn.execute(
                """
                INSERT INTO knowledge_base (
                    wa_number_id, category, question, answer, content,
                    tags, priority, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.wa_number_id,
                    entry.category.value,
                    entry.question,
                    entry.answer,
                    entry.content,
                    entry.tags,
                    entry.priority,
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat(),
                ),
            )

            entry.id = cursor.lastrowid
            self._sync_fts_row(conn, entry.id, is_new=True)
            conn.commit()
            return entry
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to save knowledge entry: {e}")
        finally:
            conn.close()

    def update(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """Update existing knowledge entry."""
        if entry.id is None:
            raise ValueError("Entry must have an ID to update")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            entry.updated_at = datetime.now()

            cursor = conn.execute(
                """
                UPDATE knowledge_base SET
                    wa_number_id = ?, category = ?, question = ?,
                    answer = ?, content = ?, tags = ?, priority = ?,
                    updated_at = ?
                WHERE id = ?
            """,
                (
                    entry.wa_number_id,
                    entry.category.value,
                    entry.question,
                    entry.answer,
                    entry.content,
                    entry.tags,
                    entry.priority,
                    entry.updated_at.isoformat(),
                    entry.id,
                ),
            )

            if cursor.rowcount == 0:
                conn.rollback()
                raise NotFoundError(f"Knowledge entry not found: {entry.id}")

            self._sync_fts_row(conn, entry.id)
            conn.commit()
            return entry
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to update knowledge entry: {e}")
        finally:
            conn.close()

    def delete(self, entry_id: int) -> bool:
        """Delete knowledge entry by ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                """
                SELECT question, answer, content 
                FROM knowledge_base WHERE id = ?
            """,
                (entry_id,),
            ).fetchone()

            if not row:
                conn.rollback()
                return False

            self._sync_fts_delete(
                conn, entry_id, row["question"], row["answer"], row["content"] or ""
            )
            conn.execute("DELETE FROM knowledge_base WHERE id = ?", (entry_id,))
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to delete knowledge entry: {e}")
        finally:
            conn.close()

    def find_by_category(
        self, wa_number_id: str, category: KnowledgeCategory
    ) -> List[KnowledgeEntry]:
        """Find knowledge entries by category."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM knowledge_base 
                WHERE wa_number_id = ? AND category = ?
                ORDER BY priority DESC, created_at DESC
            """,
                (wa_number_id, category.value),
            )
            rows = cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find entries by category: {e}")
        finally:
            conn.close()

    def search(
        self, wa_number_id: str, query: str, limit: int = 5
    ) -> List[KnowledgeEntry]:
        """Full-text search knowledge entries."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT kb.*, bm25(kb_fts) as rank
                FROM knowledge_base kb
                JOIN kb_fts ON kb.id = kb_fts.rowid
                WHERE kb.wa_number_id = ? AND kb_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """,
                (wa_number_id, query, limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to search knowledge entries: {e}")
        finally:
            conn.close()

    def search_with_outcome_weighting(
        self, wa_number_id: str, query: str, limit: int = 5
    ) -> List[KnowledgeEntry]:
        """Search knowledge entries weighted by historical effectiveness."""
        conn = self._connect()
        try:
            base_results = self.search(wa_number_id, query, limit * 3)
            if not base_results:
                return []

            entry_ids = [str(e.id) for e in base_results]
            placeholders = ",".join(["?"] * len(entry_ids))

            effectiveness = {}
            try:
                cursor = conn.execute(
                    f"""
                    SELECT 
                        CAST(json_extract(kb_entry_ids, '$[0]') AS INTEGER) as kb_id,
                        AVG(outcome_score) as avg_score,
                        COUNT(*) as uses
                    FROM response_outcomes
                    WHERE kb_entry_ids IS NOT NULL
                    AND kb_entry_ids != '[]'
                    GROUP BY kb_id
                    HAVING kb_id IN ({placeholders}) AND uses >= 2
                """,
                    entry_ids,
                )

                for row in cursor.fetchall():
                    if row["kb_id"]:
                        effectiveness[row["kb_id"]] = row["avg_score"] or 0.5
            except sqlite3.Error:
                pass

            weighted = []
            for entry in base_results:
                outcome_boost = effectiveness.get(entry.id, 0.5)
                combined_score = (1.0 / (entry.priority + 1)) * (0.5 + outcome_boost)
                weighted.append((combined_score, entry))

            weighted.sort(reverse=True, key=lambda x: x[0])
            return [entry for _, entry in weighted[:limit]]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to search with outcome weighting: {e}")
        finally:
            conn.close()

    def find_high_priority(self, wa_number_id: str) -> List[KnowledgeEntry]:
        """Find high-priority knowledge entries (priority >= 7)."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM knowledge_base 
                WHERE wa_number_id = ? AND priority >= 7
                ORDER BY priority DESC, created_at DESC
            """,
                (wa_number_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find high priority entries: {e}")
        finally:
            conn.close()

    def find_by_tag(self, wa_number_id: str, tag: str) -> List[KnowledgeEntry]:
        """Find knowledge entries by tag."""
        conn = self._connect()
        try:
            tag_pattern = f"%{tag}%"
            cursor = conn.execute(
                """
                SELECT * FROM knowledge_base 
                WHERE wa_number_id = ? AND tags LIKE ?
                ORDER BY priority DESC, created_at DESC
            """,
                (wa_number_id, tag_pattern),
            )
            rows = cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find entries by tag: {e}")
        finally:
            conn.close()

    def find_learned_entries(
        self, wa_number_id: str, limit: int = 20
    ) -> List[KnowledgeEntry]:
        """Find auto-learned knowledge entries."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM knowledge_base 
                WHERE wa_number_id = ? AND tags LIKE '%learned%'
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (wa_number_id, limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find learned entries: {e}")
        finally:
            conn.close()

    def count_by_category(self, wa_number_id: str) -> dict[KnowledgeCategory, int]:
        """Count knowledge entries by category."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT category, COUNT(*) as count 
                FROM knowledge_base 
                WHERE wa_number_id = ?
                GROUP BY category
            """,
                (wa_number_id,),
            )
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                try:
                    category = KnowledgeCategory(row["category"])
                    result[category] = row["count"]
                except ValueError:
                    pass
            return result
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to count entries by category: {e}")
        finally:
            conn.close()

    def count_total(self, wa_number_id: str) -> int:
        """Count total knowledge entries for a WA number."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM knowledge_base 
                WHERE wa_number_id = ?
            """,
                (wa_number_id,),
            )
            row = cursor.fetchone()
            return row["count"] if row else 0
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to count total entries: {e}")
        finally:
            conn.close()

    def import_entries(self, wa_number_id: str, entries: List[dict]) -> int:
        """Bulk-import knowledge entries."""
        count = 0
        for entry_dict in entries:
            try:
                entry = KnowledgeEntry(
                    wa_number_id=wa_number_id,
                    category=KnowledgeCategory(entry_dict["category"]),
                    question=entry_dict["question"],
                    answer=entry_dict["answer"],
                    content=entry_dict.get("content", ""),
                    tags=entry_dict.get("tags", ""),
                    priority=entry_dict.get("priority", 0),
                )
                self.save(entry)
                count += 1
            except (KeyError, ValueError):
                continue

        return count

    def export_entries(self, wa_number_id: str) -> List[dict]:
        """Export all knowledge entries for a WA number."""
        entries = self.get_all(wa_number_id)
        export_keys = [
            "id",
            "category",
            "question",
            "answer",
            "content",
            "tags",
            "priority",
        ]

        result = []
        for entry in entries:
            exported = {}
            for key in export_keys:
                value = getattr(entry, key, "")
                if isinstance(value, KnowledgeCategory):
                    exported[key] = value.value
                else:
                    exported[key] = value or ""
            result.append(exported)

        return result
