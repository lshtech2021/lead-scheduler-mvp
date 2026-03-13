from twilio.rest import Client
from loguru import logger
import os
from ..db import SessionLocal
from ..models import Message, OutboundSend, EventLog

_twilio_client = None

def get_twilio_client():
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    return _twilio_client

def send_sms(
    to: str,
    body: str,
    lead_id: int = None,
    status_callback: str = None,
    idempotency_key: str = None,
    message_type: str = "sms",
):
    """
    Send SMS with idempotency: (lead_id, message_type, idempotency_key) prevents duplicate sends.
    If idempotency_key is not provided, falls back to checking recent same body for lead.
    """
    session = SessionLocal()
    try:
        if lead_id and idempotency_key:
            existing = session.query(OutboundSend).filter(
                OutboundSend.lead_id == lead_id,
                OutboundSend.message_type == message_type,
                OutboundSend.idempotency_key == idempotency_key,
            ).first()
            if existing:
                logger.info(
                    "Duplicate outbound SMS prevented by idempotency key",
                    lead_id=lead_id,
                    message_type=message_type,
                    idempotency_key=idempotency_key,
                )
                session.add(EventLog(lead_id=lead_id, client_id=None, event_type="duplicate_prevention", payload={"reason": "idempotency_key", "message_type": message_type, "idempotency_key": idempotency_key}))
                session.commit()
                return None
        elif lead_id:
            recent = session.query(Message).filter(
                Message.lead_id == lead_id,
                Message.direction == "outbound",
                Message.body == body,
            ).first()
            if recent:
                logger.info("Duplicate outbound SMS prevented (same body)", lead_id=lead_id, to=to)
                session.add(EventLog(lead_id=lead_id, client_id=None, event_type="duplicate_prevention", payload={"reason": "same_body", "to": to}))
                session.commit()
                return None

        client = get_twilio_client()
        from_number = os.getenv("TWILIO_PHONE_NUMBER")
        logger.info("Sending SMS", to=to, body=body)
        message = client.messages.create(
            to=to,
            from_=from_number,
            body=body,
            status_callback=status_callback,
        )
        msg = Message(
            lead_id=lead_id,
            provider_id=message.sid,
            direction="outbound",
            body=body,
            status=message.status,
            metadata={},
        )
        session.add(msg)
        session.flush()
        if lead_id and idempotency_key:
            ob = OutboundSend(
                lead_id=lead_id,
                message_type=message_type,
                idempotency_key=idempotency_key,
                message_id=msg.id,
            )
            session.add(ob)
        session.commit()
        return message
    finally:
        session.close()