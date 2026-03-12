from loguru import logger
from ..db import SessionLocal
from ..models import Message, Lead, Stop, EventLog
import re
import os
from twilio.request_validator import RequestValidator

STOP_TOKENS = {"STOP", "UNSUBSCRIBE", "CANCEL", "END"}

validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN", ""))

async def handle_inbound_sms(payload: dict, headers: dict = None, url: str = None):
    """
    Inbound SMS handler with signature verification and idempotency.
    - headers: request headers for Twilio signature verification
    - url: full URL Twilio posted to (needed for validation)
    """
    # Verify Twilio signature if headers/url provided
    if headers and url:
        signature = headers.get("X-Twilio-Signature")
        if signature:
            params = payload.get('raw', {}) if isinstance(payload.get('raw', {}), dict) else {}
            if not validator.validate(url, params, signature):
                logger.warning("Invalid Twilio signature", signature=signature)
                return

    session = SessionLocal()
    try:
        from_phone = payload.get("from")
        body = (payload.get("body") or "").strip()
        sid = payload.get("sid")
        # idempotency: ignore if message SID already stored
        if sid:
            existing = session.query(Message).filter(Message.provider_id == sid).first()
            if existing:
                logger.info("Duplicate Twilio message SID ignored", sid=sid)
                return
        # persist message
        msg = Message(provider_id=sid, direction="inbound", body=body, status="received", metadata=payload)
        session.add(msg)
        session.commit()
        # check for STOP
        if body.upper() in STOP_TOKENS:
            # create stop entry if not exists
            st = session.query(Stop).filter(Stop.phone == from_phone).first()
            if not st:
                st = Stop(phone=from_phone)
                session.add(st)
                session.commit()
                logger.info("Recorded STOP for phone", phone=from_phone)
                evt = EventLog(lead_id=None, client_id=None, event_type="stop_event", payload={"phone": from_phone, "body": body})
                session.add(evt)
                session.commit()
            return
        # naive confirmation detection: look for "CONFIRM"
        if re.search(r"\bCONFIRM\b", body.upper()):
            # In a real implementation: parse datetime token, validate against proposed slots, then book
            logger.info("Confirmation token detected (placeholder)", body=body)
            evt = EventLog(lead_id=None, client_id=None, event_type="confirmation_received", payload={"body": body})
            session.add(evt)
            session.commit()
            return
        # otherwise generic inbound
        evt = EventLog(lead_id=None, client_id=None, event_type="inbound_sms", payload={"body": body})
        session.add(evt)
        session.commit()
    finally:
        session.close()