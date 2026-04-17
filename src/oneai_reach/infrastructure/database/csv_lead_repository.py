"""CSV implementation of LeadRepository for backward compatibility."""

import csv
import os
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


class CSVLeadRepository(LeadRepository):
    """CSV implementation of LeadRepository.

    Provides backward compatibility with existing CSV-based lead storage.
    Reads and writes leads.csv file maintaining existing format.
    """

    def __init__(self, csv_path: str):
        """Initialize repository with CSV file path.

        Args:
            csv_path: Path to CSV file
        """
        self.csv_path = csv_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.csv_path):
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self._get_fieldnames())
                writer.writeheader()

    def _get_fieldnames(self) -> List[str]:
        """Get CSV column names."""
        return [
            "id",
            "displayName",
            "formattedAddress",
            "internationalPhoneNumber",
            "phone",
            "websiteUri",
            "primaryType",
            "type",
            "source",
            "status",
            "contacted_at",
            "email",
            "linkedin",
            "followup_at",
            "replied_at",
            "research",
            "review_score",
            "review_issues",
            "reply_text",
            "created_at",
            "updated_at",
        ]

    def _read_all(self) -> List[dict]:
        """Read all rows from CSV."""
        if not os.path.exists(self.csv_path):
            return []

        with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _write_all(self, rows: List[dict]):
        """Write all rows to CSV."""
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._get_fieldnames())
            writer.writeheader()
            writer.writerows(rows)

    def _row_to_lead(self, row: dict) -> Lead:
        """Convert CSV row to Lead domain model."""
        data = row.copy()

        for field in [
            "contacted_at",
            "followup_at",
            "replied_at",
            "created_at",
            "updated_at",
        ]:
            if data.get(field) and data[field].strip():
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None
            else:
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

        for key in data:
            if data[key] == "" or data[key] == "None":
                data[key] = None

        return Lead(**data)

    def _lead_to_row(self, lead: Lead) -> dict:
        """Convert Lead domain model to CSV row."""
        row = {}
        for field in self._get_fieldnames():
            value = getattr(lead, field, None)

            if isinstance(value, datetime):
                row[field] = value.isoformat()
            elif isinstance(value, LeadStatus):
                row[field] = value.value
            elif value is None:
                row[field] = ""
            else:
                row[field] = str(value)

        return row

    def get_by_id(self, lead_id: str) -> Optional[Lead]:
        """Get lead by ID."""
        try:
            rows = self._read_all()
            for row in rows:
                if row.get("id") == lead_id:
                    return self._row_to_lead(row)
            return None
        except Exception as e:
            raise RepositoryError(f"Failed to get lead by id: {e}")

    def get_all(self) -> List[Lead]:
        """Get all leads."""
        try:
            rows = self._read_all()
            return [self._row_to_lead(row) for row in rows]
        except Exception as e:
            raise RepositoryError(f"Failed to get all leads: {e}")

    def save(self, lead: Lead) -> Lead:
        """Save new lead."""
        if lead.id:
            raise ValueError("Lead already has an ID, use update() instead")

        try:
            now = datetime.now()
            lead.created_at = now
            lead.updated_at = now

            rows = self._read_all()
            rows.append(self._lead_to_row(lead))
            self._write_all(rows)

            return lead
        except Exception as e:
            raise RepositoryError(f"Failed to save lead: {e}")

    def update(self, lead: Lead) -> Lead:
        """Update existing lead."""
        if not lead.id:
            raise ValueError("Lead must have an ID to update")

        try:
            lead.updated_at = datetime.now()

            rows = self._read_all()
            found = False
            for i, row in enumerate(rows):
                if row.get("id") == lead.id:
                    rows[i] = self._lead_to_row(lead)
                    found = True
                    break

            if not found:
                raise NotFoundError(f"Lead not found: {lead.id}")

            self._write_all(rows)
            return lead
        except NotFoundError:
            raise
        except Exception as e:
            raise RepositoryError(f"Failed to update lead: {e}")

    def delete(self, lead_id: str) -> bool:
        """Delete lead by ID."""
        try:
            rows = self._read_all()
            original_count = len(rows)
            rows = [row for row in rows if row.get("id") != lead_id]

            if len(rows) == original_count:
                return False

            self._write_all(rows)
            return True
        except Exception as e:
            raise RepositoryError(f"Failed to delete lead: {e}")

    def find_by_status(self, status: LeadStatus) -> List[Lead]:
        """Find leads by status."""
        try:
            rows = self._read_all()
            matching = [row for row in rows if row.get("status") == status.value]
            return [self._row_to_lead(row) for row in matching]
        except Exception as e:
            raise RepositoryError(f"Failed to find leads by status: {e}")

    def find_by_email(self, email: str) -> Optional[Lead]:
        """Find lead by email address."""
        try:
            rows = self._read_all()
            for row in rows:
                if row.get("email") == email:
                    return self._row_to_lead(row)
            return None
        except Exception as e:
            raise RepositoryError(f"Failed to find lead by email: {e}")

    def find_by_phone(self, phone: str) -> Optional[Lead]:
        """Find lead by phone number."""
        try:
            rows = self._read_all()
            for row in rows:
                if (
                    row.get("phone") == phone
                    or row.get("internationalPhoneNumber") == phone
                ):
                    return self._row_to_lead(row)
            return None
        except Exception as e:
            raise RepositoryError(f"Failed to find lead by phone: {e}")

    def find_by_website(self, website: str) -> Optional[Lead]:
        """Find lead by website URL."""
        try:
            rows = self._read_all()
            for row in rows:
                if row.get("websiteUri") == website:
                    return self._row_to_lead(row)
            return None
        except Exception as e:
            raise RepositoryError(f"Failed to find lead by website: {e}")

    def find_warm_leads(self) -> List[Lead]:
        """Find all warm leads (replied or meeting booked)."""
        try:
            rows = self._read_all()
            warm_statuses = [LeadStatus.REPLIED.value, LeadStatus.MEETING_BOOKED.value]
            matching = [row for row in rows if row.get("status") in warm_statuses]
            return [self._row_to_lead(row) for row in matching]
        except Exception as e:
            raise RepositoryError(f"Failed to find warm leads: {e}")

    def find_cold_leads(self) -> List[Lead]:
        """Find all cold leads (cold, lost, or unsubscribed)."""
        try:
            rows = self._read_all()
            cold_statuses = [
                LeadStatus.COLD.value,
                LeadStatus.LOST.value,
                LeadStatus.UNSUBSCRIBED.value,
            ]
            matching = [row for row in rows if row.get("status") in cold_statuses]
            return [self._row_to_lead(row) for row in matching]
        except Exception as e:
            raise RepositoryError(f"Failed to find cold leads: {e}")

    def find_needs_followup(self) -> List[Lead]:
        """Find leads that need follow-up."""
        try:
            rows = self._read_all()
            now = datetime.now()
            matching = []

            for row in rows:
                status = row.get("status")
                if status not in [
                    LeadStatus.CONTACTED.value,
                    LeadStatus.FOLLOWED_UP.value,
                ]:
                    continue

                followup_at = row.get("followup_at")
                contacted_at = row.get("contacted_at")
                replied_at = row.get("replied_at")

                if followup_at and followup_at.strip():
                    try:
                        followup_dt = datetime.fromisoformat(followup_at)
                        if now >= followup_dt:
                            matching.append(row)
                            continue
                    except (ValueError, TypeError):
                        pass

                if (
                    contacted_at
                    and contacted_at.strip()
                    and (not replied_at or not replied_at.strip())
                ):
                    try:
                        contacted_dt = datetime.fromisoformat(contacted_at)
                        days_since = (now - contacted_dt).days
                        if days_since >= 3:
                            matching.append(row)
                    except (ValueError, TypeError):
                        pass

            return [self._row_to_lead(row) for row in matching]
        except Exception as e:
            raise RepositoryError(f"Failed to find leads needing followup: {e}")

    def count_by_status(self) -> dict[LeadStatus, int]:
        """Count leads by status."""
        try:
            rows = self._read_all()
            counts = {}
            for row in rows:
                status_str = row.get("status")
                if status_str:
                    try:
                        status = LeadStatus(status_str)
                        counts[status] = counts.get(status, 0) + 1
                    except ValueError:
                        pass
            return counts
        except Exception as e:
            raise RepositoryError(f"Failed to count leads by status: {e}")

    def search(self, query: str) -> List[Lead]:
        """Search leads by name, email, or company."""
        try:
            rows = self._read_all()
            query_lower = query.lower()
            matching = []

            for row in rows:
                display_name = (row.get("displayName") or "").lower()
                email = (row.get("email") or "").lower()
                address = (row.get("formattedAddress") or "").lower()

                if (
                    query_lower in display_name
                    or query_lower in email
                    or query_lower in address
                ):
                    matching.append(row)

            return [self._row_to_lead(row) for row in matching]
        except Exception as e:
            raise RepositoryError(f"Failed to search leads: {e}")
