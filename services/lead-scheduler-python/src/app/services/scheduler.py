"""
Deterministic scheduling: load client config, fetch calendar slots, propose slot, enqueue follow-ups.
Only books when explicit confirmation is received (handled in twilio_webhook).
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from loguru import logger

from ..db import SessionLocal
from ..models import Lead, EventLog, Proposal
from .config_loader import get_client_config
from .followups import enqueue_followup, cancel_followups_for_lead
from .calendar.base import list_free_slots, CalendarAdapterError, _get_adapter

import os


def _get_tz(tz_str: str):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_str)
    except Exception:
        return None


def _slot_to_iso(slot_start: datetime) -> str:
    """Format slot for CONFIRM token (e.g. 2026-03-25T10:00)."""
    return slot_start.strftime("%Y-%m-%dT%H:%M")


def process_lead_for_scheduling(lead: Lead) -> None:
    """
    Load client config, get free slots from calendar, propose first slot, send SMS, enqueue follow-ups.
    If no calendar or no slots, send fallback SMS and log.
    """
    session = SessionLocal()
    try:
        config = get_client_config(lead.client_id)
        if not config:
            logger.warning("No client config for lead", lead_id=lead.id, client_id=lead.client_id)
            _log_event(session, lead.id, lead.client_id, "scheduling_skipped", {"reason": "no_config"})
            _send_fallback_sms(lead, "We received your request. Our team will contact you shortly.")
            return

        tz_str = config.get("timezone", "UTC")
        tz = _get_tz(tz_str)
        now = datetime.now(tz) if tz else datetime.now()
        start_date = now
        end_date = now + timedelta(days=7)
        if tz:
            start_date = start_date.replace(tzinfo=tz)
            end_date = end_date.replace(tzinfo=tz)

        if not _get_adapter(config):
            _log_event(session, lead.id, lead.client_id, "scheduling_skipped", {"reason": "no_calendar_configured"})
            _send_fallback_sms(lead, "We received your request. Our team will contact you shortly.")
            return

        try:
            slots = list_free_slots(config, start_date, end_date, tz_str)
        except CalendarAdapterError as e:
            logger.warning("Calendar adapter error", lead_id=lead.id, error=str(e))
            _log_event(session, lead.id, lead.client_id, "scheduling_failed", {"reason": str(e)})
            _send_fallback_sms(lead, "We couldn't check availability right now. We'll contact you shortly.")
            return

        if not slots:
            _log_event(session, lead.id, lead.client_id, "no_availability", {})
            _send_fallback_sms(lead, "We're fully booked at the moment. We'll be in touch with alternatives.")
            return

        slot_start, slot_end = slots[0]
        iso_slot = _slot_to_iso(slot_start)

        # Persist proposal for confirmation handling
        prop = Proposal(lead_id=lead.id, slot_start=slot_start, slot_end=slot_end)
        session.add(prop)
        lead.state = "proposed"
        session.commit()
        session.refresh(lead)

        token_format = config.get("confirmation_requirement", {}).get("token_format", "CONFIRM {ISO_DATETIME}")
        proposal_body = f"Proposed slot: {iso_slot}. Reply {token_format.replace('{ISO_DATETIME}', iso_slot)} to book or STOP to opt-out."
        status_callback = f"{os.getenv('PUBLIC_URL', '')}/webhook/twilio/status"
        from .twilio_client import send_sms
        send_sms(
            to=lead.phone,
            body=proposal_body,
            lead_id=lead.id,
            status_callback=status_callback,
            idempotency_key="proposal_1",
            message_type="proposal",
        )
        _log_event(session, lead.id, lead.client_id, "scheduling_proposed", {"slot": iso_slot})

        followups = config.get("followups", [])
        for i, fu in enumerate(followups):
            after = int(fu.get("after_minutes", 15))
            msg = (fu.get("message") or "Reminder: reply CONFIRM {ISO_DATETIME} to book.").replace("{ISO_DATETIME}", iso_slot)
            delay = after * 60
            enqueue_followup(lead_id=lead.id, to=lead.phone, body=msg, delay_seconds=delay, idempotency_key=f"followup_{i+1}")

    finally:
        session.close()


def _send_fallback_sms(lead: Lead, body: str) -> None:
    from .twilio_client import send_sms
    send_sms(to=lead.phone, body=body, lead_id=lead.id)


def _log_event(session, lead_id: Optional[int], client_id: Optional[int], event_type: str, payload: Dict[str, Any]) -> None:
    session.add(EventLog(lead_id=lead_id, client_id=client_id, event_type=event_type, payload=payload))
    session.commit()
