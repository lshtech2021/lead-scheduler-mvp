from ..db import SessionLocal
from ..models import Lead, EventLog, Stop
from loguru import logger
from .scheduler import process_lead_for_scheduling

def handle_lead(lead_id: int):
    """
    Entrypoint: called when a lead is ingested.
    Will:
      - load lead
      - check for stop
      - enqueue/process scheduling
    """
    session = SessionLocal()
    try:
        lead = session.query(Lead).get(lead_id)
        if not lead:
            logger.error("Lead not found", lead_id=lead_id)
            return
        # check stop list
        stop = session.query(Stop).filter(Stop.phone == lead.phone).first()
        if stop:
            logger.info("Lead phone is on stop list; aborting processing", phone=lead.phone)
            evt = EventLog(lead_id=lead.id, client_id=lead.client_id, event_type="stop_detected", payload={"phone": lead.phone})
            session.add(evt)
            session.commit()
            return
        # process scheduling (sync for now; replace with background worker)
        process_lead_for_scheduling(lead)
    finally:
        session.close()