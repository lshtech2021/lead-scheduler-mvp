from loguru import logger
from ..db import SessionLocal
from ..models import Lead, EventLog
from .followups import enqueue_followup
import datetime
import os

def process_lead_for_scheduling(lead: Lead):
    """
    Deterministic scheduling engine placeholder.
    For SMS foundational flows: propose a slot via SMS and schedule follow-ups.
    """
    logger.info("process_lead_for_scheduling placeholder", lead_id=lead.id)
    session = SessionLocal()
    try:
        # example: send an initial proposal SMS (dummy slot) and schedule follow-ups
        proposal = "Proposed slot: 2026-03-25T10:00. Reply CONFIRM 2026-03-25T10:00 to book or STOP to opt-out."
        # send SMS via twilio client (avoid circular import by lazy import)
        from .twilio_client import send_sms
        send_sms(to=lead.phone, body=proposal, lead_id=lead.id, status_callback=f"{os.getenv('PUBLIC_URL')}/webhook/twilio/status")
        # schedule follow-ups after 15 minutes and 60 minutes (dummy)
        enqueue_followup(lead_id=lead.id, to=lead.phone, body="Reminder: Reply CONFIRM 2026-03-25T10:00 to book.", delay_seconds=15*60)
        enqueue_followup(lead_id=lead.id, to=lead.phone, body="Final reminder: Reply CONFIRM 2026-03-25T10:00 to book.", delay_seconds=60*60)
        evt = EventLog(lead_id=lead.id, client_id=lead.client_id, event_type="scheduling_proposed", payload={"proposal": "2026-03-25T10:00"})
        session.add(evt)
        session.commit()
    finally:
        session.close()