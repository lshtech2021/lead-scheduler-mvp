import hmac
import hashlib
import json
from fastapi import APIRouter, Request, Header, Response, HTTPException
from ..db import SessionLocal
from ..models import Lead, Client, Message, Stop, EventLog, Call
from loguru import logger
from ..services import lead_handler, twilio_webhook
from ..services.followups import leads_queue
from ..utils.phone import normalize_phone
from sqlalchemy.exc import IntegrityError
import os

router = APIRouter()


def _verify_webhook_signature(body_bytes: bytes, signature_header: str | None, secret: str | None) -> bool:
    """Verify HMAC-SHA256 of body with WEBHOOK_SECRET. If secret not set, allow (dev)."""
    if not secret:
        return True
    if not signature_header:
        return False
    # Support "sha256=hexdigest" or raw hex
    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    if signature_header.startswith("sha256="):
        provided = signature_header[7:].strip().lower()
    else:
        provided = signature_header.strip().lower()
    return hmac.compare_digest(expected, provided)


@router.post("/lead")
async def receive_lead(req: Request, x_signature: str | None = Header(None, alias="X-Signature")):
    raw_body = await req.body()
    if not raw_body:
        raise HTTPException(status_code=400, detail="Body required")
    secret = os.getenv("WEBHOOK_SECRET")
    if not _verify_webhook_signature(raw_body, x_signature, secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    body = json.loads(raw_body.decode("utf-8"))
    session = SessionLocal()
    try:
        client_id = body.get("client_id")
        external_id = body.get("external_id")
        phone_raw = body.get("phone")
        phone = normalize_phone(phone_raw) or phone_raw
        payload = body.get("payload", {})
        if not phone:
            raise HTTPException(status_code=400, detail="phone required")
        lead = Lead(client_id=client_id, external_id=external_id, phone=phone, payload=payload)
        session.add(lead)
        session.commit()
        session.refresh(lead)
        logger.info("Lead ingested", id=lead.id, client_id=client_id, external_id=external_id)
        evt = EventLog(
            lead_id=lead.id,
            client_id=client_id,
            event_type="lead_ingest",
            payload={"external_id": external_id, "phone": phone},
        )
        session.add(evt)
        session.commit()
        leads_queue.enqueue(lead_handler.handle_lead, lead.id)
        return {"ok": True, "lead_id": lead.id}
    except IntegrityError:
        session.rollback()
        logger.info("Duplicate lead ignored", client_id=body.get("client_id"), external_id=body.get("external_id"))
        return {"ok": True, "note": "duplicate ignored"}
    finally:
        session.close()

@router.post("/twilio/sms")
async def twilio_sms(request: Request, x_twilio_signature: str = Header(None)):
    form = await request.form()
    from_number = form.get("From")
    to_number = form.get("To")
    body = form.get("Body")
    sid = form.get("MessageSid")
    logger.info("Twilio SMS inbound", from_number=from_number, body=body)
    url = str(request.url)
    headers = dict(request.headers) if request.headers else {}
    result = await twilio_webhook.handle_inbound_sms(
        {"from": from_number, "to": to_number, "body": body, "sid": sid, "raw": dict(form)},
        headers=headers,
        url=url,
    )
    if result is False:
        return Response(content="", status_code=403)
    return Response(content="<Response></Response>", media_type="application/xml")

@router.post("/twilio/voice")
async def twilio_voice(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid")
    from_number = form.get("From")
    logger.info("Twilio Voice inbound", call_sid=call_sid, from_number=from_number)
    query_params = dict(request.query_params) if request.query_params else {}
    twiml = twilio_webhook.handle_inbound_voice(
        {"call_sid": call_sid, "from": from_number, "raw": dict(form)},
        request_url=str(request.url),
        query_params=query_params,
    )
    return Response(content=twiml, media_type="application/xml")

@router.post("/twilio/status")
async def twilio_status(request: Request):
    form = await request.form()
    form_dict = dict(form)
    sid = form_dict.get("MessageSid") or form_dict.get("CallSid")
    status = form_dict.get("MessageStatus") or form_dict.get("CallStatus")
    logger.info("Twilio status callback", sid=sid, status=status)
    session = SessionLocal()
    try:
        if sid:
            msg = session.query(Message).filter(Message.provider_id == sid).first()
            if msg:
                msg.status = status or msg.status
            else:
                call_row = session.query(Call).filter(Call.provider_id == sid).first()
                if call_row:
                    call_row.status = status or call_row.status
            session.commit()
        event = EventLog(lead_id=None, client_id=None, event_type="twilio_status", payload=form_dict)
        session.add(event)
        session.commit()
    finally:
        session.close()
    return Response(content="", status_code=200)