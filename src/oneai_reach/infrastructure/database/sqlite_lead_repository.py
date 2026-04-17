"""SQLite implementation of LeadRepository."""

import sqlite3
from datetime import datetime
from typing import List, Optional

from oneai_reach.domain.models.lead import Lead, LeadStatus
from oneai_reach.domain.repositories.lead_repository import LeadRepository


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class NotFoundError(RepositoryError):
    """Exception raised when entity not found."""

    pass


class SQLiteLeadRepository(LeadRepository):
    """SQLite implementation of LeadRepository.

    Provides data access for Lead entities using SQLite database.
    Maintains schema compatibility with existing leads.db structure.
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
        return conn

    def _row_to_lead(self, row: sqlite3.Row) -> Lead:
        """Convert database row to Lead domain model."""
        data = dict(row)

        for field in [
            "contacted_at",
            "followup_at",
            "replied_at",
            "created_at",
            "updated_at",
        ]:
            if data.get(field):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None

        if data.get("status"):
            data["status"] = LeadStatus(data["status"])

        if data.get("email"):
            email = data["email"].strip()
            if not email or email.lower() in ("none", "nan") or "@" not in email:
                data["email"] = None
            elif (
                any(char in email for char in ["%", " "])
                or email.startswith(".")
                or ".@" in email
            ):
                data["email"] = None
            else:
                data["email"] = email

        return Lead(**data)

    def get_by_id(self, lead_id: str) -> Optional[Lead]:
        """Get lead by ID."""
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
            row = cursor.fetchone()
            return self._row_to_lead(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get lead by id: {e}")
        finally:
            conn.close()

    def get_all(self) -> List[Lead]:
        """Get all leads."""
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT * FROM leads ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [self._row_to_lead(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to get all leads: {e}")
        finally:
            conn.close()

    def save(self, lead: Lead) -> Lead:
        """Save new lead."""
        if lead.id:
            raise ValueError("Lead already has an ID, use update() instead")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            # Set timestamps
            now = datetime.now()
            lead.created_at = now
            lead.updated_at = now

            # Insert lead
            cursor = conn.execute(
                """
                INSERT INTO leads (
                    id, displayName, formattedAddress, internationalPhoneNumber,
                    phone, websiteUri, primaryType, type, source, status,
                    contacted_at, email, linkedin, followup_at, replied_at,
                    research, review_score, review_issues, reply_text,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    lead.id,
                    lead.displayName,
                    lead.formattedAddress,
                    lead.internationalPhoneNumber,
                    lead.phone,
                    lead.websiteUri,
                    lead.primaryType,
                    lead.type,
                    lead.source,
                    lead.status.value,
                    lead.contacted_at.isoformat() if lead.contacted_at else None,
                    lead.email,
                    lead.linkedin,
                    lead.followup_at.isoformat() if lead.followup_at else None,
                    lead.replied_at.isoformat() if lead.replied_at else None,
                    lead.research,
                    lead.review_score,
                    lead.review_issues,
                    lead.reply_text,
                    lead.created_at.isoformat(),
                    lead.updated_at.isoformat(),
                ),
            )

            conn.commit()
            return lead
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to save lead: {e}")
        finally:
            conn.close()

    def update(self, lead: Lead) -> Lead:
        """Update existing lead."""
        if not lead.id:
            raise ValueError("Lead must have an ID to update")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")

            # Update timestamp
            lead.updated_at = datetime.now()

            cursor = conn.execute(
                """
                UPDATE leads SET
                    displayName = ?, formattedAddress = ?, internationalPhoneNumber = ?,
                    phone = ?, websiteUri = ?, primaryType = ?, type = ?, source = ?,
                    status = ?, contacted_at = ?, email = ?, linkedin = ?,
                    followup_at = ?, replied_at = ?, research = ?, review_score = ?,
                    review_issues = ?, reply_text = ?, updated_at = ?
                WHERE id = ?
            """,
                (
                    lead.displayName,
                    lead.formattedAddress,
                    lead.internationalPhoneNumber,
                    lead.phone,
                    lead.websiteUri,
                    lead.primaryType,
                    lead.type,
                    lead.source,
                    lead.status.value,
                    lead.contacted_at.isoformat() if lead.contacted_at else None,
                    lead.email,
                    lead.linkedin,
                    lead.followup_at.isoformat() if lead.followup_at else None,
                    lead.replied_at.isoformat() if lead.replied_at else None,
                    lead.research,
                    lead.review_score,
                    lead.review_issues,
                    lead.reply_text,
                    lead.updated_at.isoformat(),
                    lead.id,
                ),
            )

            if cursor.rowcount == 0:
                conn.rollback()
                raise NotFoundError(f"Lead not found: {lead.id}")

            conn.commit()
            return lead
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to update lead: {e}")
        finally:
            conn.close()

    def delete(self, lead_id: str) -> bool:
        """Delete lead by ID."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        except sqlite3.Error as e:
            conn.rollback()
            raise RepositoryError(f"Failed to delete lead: {e}")
        finally:
            conn.close()

    def find_by_status(self, status: LeadStatus) -> List[Lead]:
        """Find leads by status."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM leads WHERE status = ? ORDER BY created_at DESC",
                (status.value,),
            )
            rows = cursor.fetchall()
            return [self._row_to_lead(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find leads by status: {e}")
        finally:
            conn.close()

    def find_by_email(self, email: str) -> Optional[Lead]:
        """Find lead by email address."""
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT * FROM leads WHERE email = ?", (email,))
            row = cursor.fetchone()
            return self._row_to_lead(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find lead by email: {e}")
        finally:
            conn.close()

    def find_by_phone(self, phone: str) -> Optional[Lead]:
        """Find lead by phone number."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM leads WHERE phone = ? OR internationalPhoneNumber = ?",
                (phone, phone),
            )
            row = cursor.fetchone()
            return self._row_to_lead(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find lead by phone: {e}")
        finally:
            conn.close()

    def find_by_website(self, website: str) -> Optional[Lead]:
        """Find lead by website URL."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM leads WHERE websiteUri = ?", (website,)
            )
            row = cursor.fetchone()
            return self._row_to_lead(row) if row else None
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find lead by website: {e}")
        finally:
            conn.close()

    def find_warm_leads(self) -> List[Lead]:
        """Find all warm leads (replied or meeting booked)."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM leads 
                WHERE status IN (?, ?)
                ORDER BY replied_at DESC
            """,
                (LeadStatus.REPLIED.value, LeadStatus.MEETING_BOOKED.value),
            )
            rows = cursor.fetchall()
            return [self._row_to_lead(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find warm leads: {e}")
        finally:
            conn.close()

    def find_cold_leads(self) -> List[Lead]:
        """Find all cold leads (cold, lost, or unsubscribed)."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM leads 
                WHERE status IN (?, ?, ?)
                ORDER BY updated_at DESC
            """,
                (
                    LeadStatus.COLD.value,
                    LeadStatus.LOST.value,
                    LeadStatus.UNSUBSCRIBED.value,
                ),
            )
            rows = cursor.fetchall()
            return [self._row_to_lead(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find cold leads: {e}")
        finally:
            conn.close()

    def find_needs_followup(self) -> List[Lead]:
        """Find leads that need follow-up."""
        conn = self._connect()
        try:
            now = datetime.now().isoformat()
            cursor = conn.execute(
                """
                SELECT * FROM leads 
                WHERE status IN (?, ?)
                AND (
                    (followup_at IS NOT NULL AND followup_at <= ?)
                    OR (contacted_at IS NOT NULL AND replied_at IS NULL 
                        AND datetime(contacted_at, '+3 days') <= ?)
                )
                ORDER BY followup_at ASC, contacted_at ASC
            """,
                (LeadStatus.CONTACTED.value, LeadStatus.FOLLOWED_UP.value, now, now),
            )
            rows = cursor.fetchall()
            return [self._row_to_lead(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to find leads needing followup: {e}")
        finally:
            conn.close()

    def count_by_status(self) -> dict[LeadStatus, int]:
        """Count leads by status."""
        conn = self._connect()
        try:
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count 
                FROM leads 
                GROUP BY status
            """)
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                try:
                    status = LeadStatus(row["status"])
                    result[status] = row["count"]
                except ValueError:
                    # Skip invalid status values
                    pass
            return result
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to count leads by status: {e}")
        finally:
            conn.close()

    def search(self, query: str) -> List[Lead]:
        """Search leads by name, email, or company."""
        conn = self._connect()
        try:
            search_pattern = f"%{query}%"
            cursor = conn.execute(
                """
                SELECT * FROM leads 
                WHERE displayName LIKE ? 
                   OR email LIKE ? 
                   OR formattedAddress LIKE ?
                ORDER BY created_at DESC
            """,
                (search_pattern, search_pattern, search_pattern),
            )
            rows = cursor.fetchall()
            return [self._row_to_lead(row) for row in rows]
        except sqlite3.Error as e:
            raise RepositoryError(f"Failed to search leads: {e}")
        finally:
            conn.close()
