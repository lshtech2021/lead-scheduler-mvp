"""
Abstract calendar interface: list free slots and create bookings.
"""
from datetime import datetime
from typing import Any, Dict, List, Tuple

class CalendarAdapterError(Exception):
    """Raised when calendar operations fail (e.g. conflict, auth)."""
    pass


def _get_adapter(client_config: Dict[str, Any]):  # exported for scheduler
    """Return the appropriate adapter based on config."""
    if client_config.get("google_calendar_id"):
        from .google_calendar import GoogleCalendarAdapter
        return GoogleCalendarAdapter()
    if client_config.get("calendly_token") and client_config.get("calendly_event_type"):
        from .calendly_adapter import CalendlyAdapter
        return CalendlyAdapter()
    return None


def list_free_slots(
    client_config: Dict[str, Any],
    start_date: datetime,
    end_date: datetime,
    timezone: str = "UTC",
) -> List[Tuple[datetime, datetime]]:
    """
    Return list of (start, end) free slots within business hours.
    Uses client_config to select adapter (Google Calendar or Calendly).
    """
    adapter = _get_adapter(client_config)
    if not adapter:
        return []
    return adapter.list_free_slots(client_config, start_date, end_date, timezone)


def create_booking(
    client_config: Dict[str, Any],
    start: datetime,
    end: datetime,
    lead_id: int,
    metadata: Dict[str, Any],
) -> str:
    """
    Create a calendar event. Returns provider_booking_id.
    Raises CalendarAdapterError on conflict or failure.
    """
    adapter = _get_adapter(client_config)
    if not adapter:
        raise CalendarAdapterError("No calendar adapter configured for client")
    return adapter.create_booking(client_config, start, end, lead_id, metadata)
