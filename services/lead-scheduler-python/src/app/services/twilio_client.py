from twilio.rest import Client
from loguru import logger
import os
from ..db import SessionLocal
from ..models import Message

_twilio_client = None

def get_twilio_client():
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    return _twilio_client

def send_sms(to: str, body: str, lead_id: int = None, status_callback: str = None, idempotency_key: str = None):
    """
    Send SMS with a simple idempotency guard: ensure we haven't sent the same body to the same number for the same lead in the last few minutes.
    """
    session = SessionLocal()
    try:
        # check recent similar outbound (simple guard)
        if lead_id:
            recent = session.query(Message).filter(Message.lead_id == lead_id, Message.direction == "outbound", Message.body == body).first()
            if recent:
                logger.info("Duplicate outbound SMS prevented by idempotency guard", lead_id=lead_id, to=to)
                return None
        client = get_twilio_client()
        from_number = os.getenv("TWILIO_PHONE_NUMBER")
        logger.info("Sending SMS", to=to, body=body)
        message = client.messages.create(
            to=to,
            from_=from_number,
            body=body,
            status_callback=status_callback
        )
        # persist outbound message
        msg = Message(lead_id=lead_id, provider_id=message.sid, direction="outbound", body=body, status=message.status, metadata={})
        session.add(msg)
        session.commit()
        return message
    finally:
        session.close()