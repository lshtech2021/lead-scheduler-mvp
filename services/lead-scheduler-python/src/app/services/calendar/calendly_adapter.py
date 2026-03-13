"""
Calendly adapter: availability and scheduling via Calendly API.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple
import httpx

from .base import CalendarAdapterError

CALENDLY_API_BASE = "https://api.calendly.com"


class CalendlyAdapter:
    """Calendly API: list available times and create scheduled events."""

    def list_free_slots(
        self,
        client_config: Dict[str, Any],
        start_date: datetime,
        end_date: datetime,
        timezone: str = "UTC",
    ) -> List[Tuple[datetime, datetime]]:
        token = client_config.get("calendly_token")
        event_type_uri = client_config.get("calendly_event_type")
        if not token or not event_type_uri:
            return []
        # Calendly event type can be full URI or UUID
        if not event_type_uri.startswith("http"):
            event_type_uri = f"https://api.calendly.com/event_types/{event_type_uri}"
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = f"{CALENDLY_API_BASE}/event_type_available_times"
        params = {
            "event_type": event_type_uri,
            "start_time": start_str,
            "end_time": end_str,
        }
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with httpx.Client() as client:
                r = client.get(url, params=params, headers=headers, timeout=10.0)
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, Exception) as e:
            raise CalendarAdapterError(f"Calendly availability failed: {e}")
        collection = data.get("collection", [])
        out = []
        for item in collection:
            start_s = item.get("start_time")
            end_s = item.get("end_time")
            if start_s and end_s:
                try:
                    start_dt = datetime.fromisoformat(start_s.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end_s.replace("Z", "+00:00"))
                    out.append((start_dt, end_dt))
                except (ValueError, TypeError):
                    pass
        return out[: client_config.get("max_proposals", 3) * 2]

    def create_booking(
        self,
        client_config: Dict[str, Any],
        start: datetime,
        end: datetime,
        lead_id: int,
        metadata: Dict[str, Any],
    ) -> str:
        token = client_config.get("calendly_token")
        event_type_uri = client_config.get("calendly_event_type")
        if not token or not event_type_uri:
            raise CalendarAdapterError("Calendly not configured")
        if not event_type_uri.startswith("http"):
            event_type_uri = f"https://api.calendly.com/event_types/{event_type_uri}"
        # Calendly Scheduling API: create invitee
        url = f"{CALENDLY_API_BASE}/scheduled_events"
        start_str = start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        payload = {
            "event_type": event_type_uri,
            "start_time": start_str,
            "invitee": {
                "email": metadata.get("email", f"lead-{lead_id}@placeholder.local"),
                "name": metadata.get("name", f"Lead {lead_id}"),
            },
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            with httpx.Client() as client:
                r = client.post(url, json=payload, headers=headers, timeout=10.0)
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, Exception) as e:
            raise CalendarAdapterError(f"Calendly booking failed: {e}")
        event_uri = data.get("resource", {}).get("uri") or data.get("uri")
        if event_uri:
            return event_uri
        return data.get("resource", {}).get("uuid", str(lead_id))
