from loguru import logger
from ..db import SessionLocal
from ..models import Message, Lead, Stop, EventLog
import re

STOP_TOKENS = {"STOP", "UNSUBSCRIBE", "CANCEL", "END"}

async def handle_inbound_sms(payload: dict):
    """
    Minimal inbound SMS handler:
    - Normalize phone
    - If STOP token -> record stop and cancel follow-ups
    - Otherwise, find lead and append message
    - For confirmation grammar, placeholder implementation
    """
    session = SessionLocal()
    try:
        from_phone = payload.get("from")
        body = (payload.get("body") or "").strip()
        sid = payload.get("sid")
        # persist message
        msg = Message(provider_id=sid, direction="inbound", body=body, status="received", metadata=payload)
        session.add(msg)
        session.commit()
        # check for STOP
        if body.upper() in STOP_TOKENS:
            # create stop entry
            st = Stop(phone=from_phone)
            session.add(st)
            session.commit()
            logger.info("Recorded STOP for phone", phone=from_phone)
            # log event
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

def handle_inbound_voice(payload: dict) -> str:
    """
    Return TwiML for voice. Placeholder returns a simple prompt.
    Real implementation will generate TwiML that gathers digits / records, then POSTs to a callback endpoint.
    """
    # Simple TwiML: ask for best time and record
    twiml = """
<Response>
  <Say>Hi, thanks for calling. Please say the date and time you prefer after the beep. Then press the pound key.</Say>
  <Record action="/webhook/twilio/voice/recording" method="POST" maxLength="30" finishOnKey="#"/>
</Response>
"""
    return twiml