"""
Per-client configuration loader. Returns validated config with safe defaults.
No code changes required when updating client settings; config lives in Client.config JSON.
"""
from typing import Any, Dict, List, Optional
from ..db import SessionLocal
from ..models import Client

DEFAULT_BUSINESS_HOURS = {
    "monday": ["09:00-17:00"],
    "tuesday": ["09:00-17:00"],
    "wednesday": ["09:00-17:00"],
    "thursday": ["09:00-17:00"],
    "friday": ["09:00-17:00"],
    "saturday": [],
    "sunday": [],
}

DEFAULT_CONFIRMATION = {
    "type": "explicit_token",
    "token_format": "CONFIRM {ISO_DATETIME}",
}

DEFAULT_FOLLOWUPS: List[Dict[str, Any]] = [
    {"after_minutes": 15, "message": "Reminder: reply CONFIRM {ISO_DATETIME} to book."},
    {"after_minutes": 60, "message": "Final reminder: reply CONFIRM {ISO_DATETIME}."},
]


def get_client_config(client_id: int) -> Optional[Dict[str, Any]]:
    """
    Load client by id and return validated config with defaults for missing keys.
    Returns None if client not found.
    """
    session = SessionLocal()
    try:
        client = session.query(Client).filter(Client.id == client_id).first()
        if not client or not client.config:
            return None
        raw = client.config if isinstance(client.config, dict) else {}
        return _apply_defaults(raw)
    finally:
        session.close()


def _apply_defaults(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Merge raw config with safe defaults."""
    business_hours = raw.get("business_hours")
    if not isinstance(business_hours, dict):
        business_hours = DEFAULT_BUSINESS_HOURS.copy()
    else:
        for day in DEFAULT_BUSINESS_HOURS:
            if day not in business_hours:
                business_hours[day] = DEFAULT_BUSINESS_HOURS[day]

    confirmation = raw.get("confirmation_requirement")
    if not isinstance(confirmation, dict):
        confirmation = DEFAULT_CONFIRMATION.copy()
    else:
        confirmation = {**DEFAULT_CONFIRMATION, **confirmation}

    followups = raw.get("followups")
    if not isinstance(followups, list) or len(followups) == 0:
        followups = list(DEFAULT_FOLLOWUPS)
    else:
        followups = [
            {
                "after_minutes": f.get("after_minutes", 15),
                "message": f.get("message", "Reminder: reply CONFIRM {ISO_DATETIME} to book."),
            }
            for f in followups
            if isinstance(f, dict)
        ]

    stop_policy = raw.get("stop_policy")
    if not isinstance(stop_policy, dict):
        stop_policy = {"global": True}
    else:
        stop_policy = {"global": True, **stop_policy}

    return {
        "business_hours": business_hours,
        "slot_length_minutes": int(raw.get("slot_length_minutes", 30)),
        "min_lead_time_minutes": int(raw.get("min_lead_time_minutes", 60)),
        "max_proposals": int(raw.get("max_proposals", 3)),
        "confirmation_requirement": confirmation,
        "followups": followups,
        "stop_policy": stop_policy,
        "timezone": raw.get("timezone", "UTC"),
        "google_calendar_id": raw.get("google_calendar_id"),
        "calendly_token": raw.get("calendly_token"),
        "calendly_event_type": raw.get("calendly_event_type"),
    }
