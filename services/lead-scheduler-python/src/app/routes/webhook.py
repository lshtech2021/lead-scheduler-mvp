from fastapi import APIRouter, Request, Header, Response
from ..db import SessionLocal
from ..models import Lead, Client, Message, Stop, EventLog
from loguru import logger
from ..services import lead_handler, twilio_webhook
from sqlalchemy.exc import IntegrityError

router = APIRouter()

@router.post("/lead")
async def receive_lead(req: Request):
    body = await req.json()
    session = SessionLocal()
    try:
        client_id = body.get("client_id")
        external_id = body.get("external_id")
        phone = body.get("phone")
        payload = body.get("payload", {})
        # basic ingest with idempotency by unique constraint
        lead = Lead(client_id=client_id, external_id=external_id, phone=phone, payload=payload)
        session.add(lead)
        session.commit()
        session.refresh(lead)
        logger.info("Lead ingested", id=lead.id)
        # hand to lead handler (async background allowed)
        lead_handler.handle_lead(lead.id)
        return {"ok": True, "lead_id": lead.id}
    except IntegrityError:
        session.rollback()
        logger.info("Duplicate lead ignored", client_id=body.get("client_id"), external_id=body.get("external_id"))
        return {"ok": True, "note": "duplicate ignored"}
    finally:
        session.close()

@router.post("/twilio/sms")
async def twilio_sms(request: Request, x_twilio_signature: str = Header(None)):
    # For now, accept inbound; in later milestones verify signature
    form = await request.form()
    from_number = form.get("From")
    to_number = form.get("To")
    body = form.get("Body")
    sid = form.get("MessageSid")
    logger.info("Twilio SMS inbound", from_number=from_number, body=body)
    # call twilio webhook handler
    await twilio_webhook.handle_inbound_sms({
        "from": from_number,
        "to": to_number,
        "body": body,
        "sid": sid,
        "raw": dict(form)
    })
    # respond with empty TwiML
    return Response(content="<Response></Response>", media_type="application/xml")

@router.post("/twilio/voice")
async def twilio_voice(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid")
    from_number = form.get("From")
    logger.info("Twilio Voice inbound", call_sid=call_sid, from_number=from_number)
    # placeholder TwiML response created by handler
    twiml = twilio_webhook.handle_inbound_voice({
        "call_sid": call_sid,
        "from": from_number,
        "raw": dict(form)
    })
    return Response(content=twiml, media_type="application/xml")

@router.post("/twilio/status")
async def twilio_status(request: Request):
    form = await request.form()
    sid = form.get("MessageSid") or form.get("CallSid")
    status = form.get("MessageStatus") or form.get("CallStatus")
    logger.info("Twilio status callback", sid=sid, status=status)
    # store status update
    session = SessionLocal()
    try:
        # naive store into event logs (improve later)
        event = EventLog(lead_id=None, client_id=None, event_type="twilio_status", payload=dict(form))
        session.add(event)
        session.commit()
    finally:
        session.close()
    return {"ok": True}