"""
Google Calendar adapter: freebusy query for free slots, events.insert for booking.
"""
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from .base import CalendarAdapterError

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

# Required scope for calendar read + write
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _parse_time(s: str):
    """Parse 'HH:MM' to (hour, minute)."""
    parts = s.strip().split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def _business_hours_to_ranges(
    business_hours: Dict[str, List[str]],
    day_start: datetime,
    timezone_offset_hours: int = 0,
) -> List[Tuple[datetime, datetime]]:
    """Convert business_hours for a given day to (start, end) datetime ranges on that day."""
    weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day_name = weekday_names[day_start.weekday()]
    windows = business_hours.get(day_name, [])
    ranges = []
    for w in windows:
        if not w or "-" not in w:
            continue
        start_str, end_str = w.split("-", 1)
        h1, m1 = _parse_time(start_str)
        h2, m2 = _parse_time(end_str)
        start = day_start.replace(hour=h1, minute=m1, second=0, microsecond=0)
        end = day_start.replace(hour=h2, minute=m2, second=0, microsecond=0)
        if start < end:
            ranges.append((start, end))
    return ranges


class GoogleCalendarAdapter:
    """Google Calendar API: list free slots and create events."""

    def _get_service(self, client_config: Dict[str, Any]):
        if not HAS_GOOGLE:
            raise CalendarAdapterError("google-api-python-client not installed")
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or client_config.get("google_credentials_path")
        if not creds_path or not os.path.isfile(creds_path):
            raise CalendarAdapterError("GOOGLE_APPLICATION_CREDENTIALS or google_credentials_path not set")
        credentials = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        return build("calendar", "v3", credentials=credentials)

    def list_free_slots(
        self,
        client_config: Dict[str, Any],
        start_date: datetime,
        end_date: datetime,
        timezone: str = "UTC",
    ) -> List[Tuple[datetime, datetime]]:
        calendar_id = client_config.get("google_calendar_id")
        if not calendar_id:
            return []
        slot_minutes = client_config.get("slot_length_minutes", 30)
        min_lead_minutes = client_config.get("min_lead_time_minutes", 60)
        business_hours = client_config.get("business_hours", {})

        service = self._get_service(client_config)
        time_min = start_date.isoformat() + "Z" if start_date.tzinfo is None else start_date.isoformat()
        time_max = end_date.isoformat() + "Z" if end_date.tzinfo is None else end_date.isoformat()
        try:
            freebusy = service.freebusy().query(
                body={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "items": [{"id": calendar_id}],
                }
            ).execute()
        except HttpError as e:
            raise CalendarAdapterError(f"Google Calendar freebusy failed: {e}")

        busy_list = freebusy.get("calendars", {}).get(calendar_id, {}).get("busy", [])
        busy_ranges = []
        for b in busy_list:
            s = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(b["end"].replace("Z", "+00:00"))
            if s.tzinfo is None:
                s = s.replace(tzinfo=datetime.now().astimezone().tzinfo)
            if e.tzinfo is None:
                e = e.replace(tzinfo=datetime.now().astimezone().tzinfo)
            busy_ranges.append((s, e))

        # Build candidate slots from business hours, then exclude busy
        slot_delta = timedelta(minutes=slot_minutes)
        min_lead = timedelta(minutes=min_lead_minutes)
        tz = start_date.tzinfo
        now = datetime.now(tz) if tz else datetime.now()
        free_slots = []
        day = start_date.date()
        end_day = end_date.date()
        while day <= end_day:
            day_start = datetime.combine(day, datetime.min.time())
            if tz:
                day_start = day_start.replace(tzinfo=tz)
            for range_start, range_end in _business_hours_to_ranges(business_hours, day_start):
                if range_end <= start_date or range_start >= end_date:
                    continue
                slot_start = max(start_date, range_start)
                while slot_start + slot_delta <= range_end and slot_start + slot_delta <= end_date:
                    slot_end = slot_start + slot_delta
                    if slot_start >= now + min_lead:
                        is_busy = any(
                            (slot_start < be and slot_end > bs)
                            for bs, be in busy_ranges
                        )
                        if not is_busy:
                            free_slots.append((slot_start, slot_end))
                    slot_start = slot_end
            day += timedelta(days=1)

        return free_slots[: client_config.get("max_proposals", 3) * 2]

    def create_booking(
        self,
        client_config: Dict[str, Any],
        start: datetime,
        end: datetime,
        lead_id: int,
        metadata: Dict[str, Any],
    ) -> str:
        calendar_id = client_config.get("google_calendar_id")
        if not calendar_id:
            raise CalendarAdapterError("google_calendar_id not in config")
        service = self._get_service(client_config)
        event = {
            "summary": metadata.get("summary", "Scheduled appointment"),
            "description": metadata.get("description", f"Lead ID: {lead_id}"),
            "start": {"dateTime": start.isoformat(), "timeZone": client_config.get("timezone", "UTC")},
            "end": {"dateTime": end.isoformat(), "timeZone": client_config.get("timezone", "UTC")},
        }
        try:
            created = service.events().insert(calendarId=calendar_id, body=event).execute()
            return created.get("id", "")
        except HttpError as e:
            raise CalendarAdapterError(f"Google Calendar insert failed: {e}")
