"""Meeting scheduler integration for auto-booking from positive replies.

Integrates with:
- Calendly API
- Google Calendar
- Microsoft Calendar

Features:
- Auto-detect positive intent from replies
- Send meeting link with available slots
- Auto-book when prospect selects time
- Add to CRM and send confirmation
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
import logging

from oneai_reach.config.settings import Settings
from oneai_reach.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MeetingSlot:
    """Available meeting slot."""
    start_time: str  # ISO format
    duration_minutes: int
    meeting_url: str


@dataclass
class MeetingBooking:
    """Confirmed meeting booking."""
    id: str
    lead_id: str
    contact_email: str
    contact_name: str
    scheduled_time: str
    duration_minutes: int
    meeting_url: str
    calendar_event_id: Optional[str] = None
    status: str = "confirmed"  # confirmed, cancelled, rescheduled


class MeetingScheduler:
    """Meeting scheduling service."""

    def __init__(self, config: Settings):
        self.config = config
        self.calendly_api_key = config.external_api.calendly_api_key if hasattr(config.external_api, 'calendly_api_key') else ""
        self.calendly_base_url = "https://api.calendly.com"

    def get_available_slots(self, meeting_type_uuid: str, start_date: datetime, end_date: datetime) -> List[MeetingSlot]:
        """Get available meeting slots from Calendly."""
        if not self.calendly_api_key:
            logger.warning("Calendly API key not configured")
            return []

        headers = {
            "Authorization": f"Bearer {self.calendly_api_key}",
            "Content-Type": "application/json"
        }

        params = {
            "meeting_type": meeting_type_uuid,
            "start_time": start_date.isoformat(),
            "end_time": end_date.isoformat(),
        }

        try:
            response = requests.get(
                f"{self.calendly_base_url}/scheduled_meetings/available_times",
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            slots = []
            for slot in data.get("available_times", []):
                slots.append(MeetingSlot(
                    start_time=slot["start_time"],
                    duration_minutes=slot["duration_minutes"],
                    meeting_url=slot["meeting_url"]
                ))
            return slots
        except Exception as e:
            logger.error(f"Failed to get Calendly slots: {e}")
            return []

    def book_meeting(self, slot: MeetingSlot, invitee_data: Dict) -> Optional[MeetingBooking]:
        """Book a meeting slot."""
        if not self.calendly_api_key:
            return None

        headers = {
            "Authorization": f"Bearer {self.calendly_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "meeting_type": slot.meeting_url,
            "invitee_email": invitee_data.get("email"),
            "invitee_name": invitee_data.get("name"),
            "timezone": invitee_data.get("timezone", "Asia/Jakarta"),
        }

        try:
            response = requests.post(
                f"{self.calendly_base_url}/scheduled_meetings",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            booking = MeetingBooking(
                id=data["resource"]["uri"].split("/")[-1],
                lead_id=invitee_data.get("lead_id", ""),
                contact_email=invitee_data["email"],
                contact_name=invitee_data["name"],
                scheduled_time=slot.start_time,
                duration_minutes=slot.duration_minutes,
                meeting_url=data["resource"]["location"]["location"],
                status="confirmed"
            )
            logger.info(f"Booked meeting: {booking.contact_name} at {booking.scheduled_time}")
            return booking
        except Exception as e:
            logger.error(f"Failed to book meeting: {e}")
            return None

    def cancel_meeting(self, booking_id: str, reason: str = "") -> bool:
        """Cancel a meeting booking."""
        if not self.calendly_api_key:
            return False

        headers = {
            "Authorization": f"Bearer {self.calendly_api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.delete(
                f"{self.calendly_base_url}/scheduled_meetings/{booking_id}",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Cancelled meeting: {booking_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel meeting: {e}")
            return False

    def generate_meeting_link(self, meeting_type: str = "15min") -> str:
        """Generate a Calendly meeting link for manual sharing."""
        # Default Calendly link format
        if hasattr(self.config.booking, 'calendly_link'):
            return self.config.booking.calendly_link
        return f"https://calendly.com/berkahkarya/{meeting_type}"


def get_meeting_scheduler(config: Settings) -> MeetingScheduler:
    """Get or create meeting scheduler."""
    return MeetingScheduler(config)
