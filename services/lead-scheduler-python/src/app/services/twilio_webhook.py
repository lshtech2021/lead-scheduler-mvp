"""
Twilio inbound SMS and Voice webhook handlers: STOP, confirmation parsing, booking, logging.
"""
import re
from datetime import datetime

from loguru import logger

from ..db import SessionLocal
from ..models import Message, Lead, Stop, EventLog, Booking, Proposal, Call
from ..utils.phone import normalize_phone
from .followups import cancel_followups_for_lead
from .config_loader import get_client_config
from .calendar.base import list_free_slots, create_booking, CalendarAdapterError, _get_adapter
from .twilio_client import send_sms

import os

STOP_TOKENS = {"STOP", "UNSUBSCRIBE", "CANCEL", "END", "UNSUB", "STOPALL"}

try:
    from twilio.request_validator import RequestValidator
    _validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN", ""))
except Exception:
    _validator = None


def _validate_twilio_signature(url: str, params: dict, signature: str) -> bool:
    if not _validator or not signature:
        return True
    return _validator.validate(url, params, signature)


# Regex for CONFIRM <ISO_DATETIME> (e.g. CONFIRM 2026-03-25T10:00 or CONFIRM 2026-03-25 10:00)
CONFIRM_PATTERN = re.compile(
    r"\bCONFIRM\s+(\d{4}-\d{2}-\d{2})[T\s](\d{1,2}):(\d{2})(?:\s*(\d{2}))?",
    re.IGNORECASE,
)


def _parse_confirm_datetime(body: str):
    """Extract (date, time) from body if it matches CONFIRM <date>T<time> or CONFIRM <date> <time>. Returns (date_str, hour, min) or None."""
    m = CONFIRM_PATTERN.search(body)
    if not m:
        return None
    date_str, hour, minute = m.group(1), int(m.group(2)), int(m.group(3))
    return (date_str, hour, minute)


async def handle_inbound_sms(payload: dict, headers: dict = None, url: str = None):
    """
    Inbound SMS: verify signature, persist, link to lead, handle STOP or CONFIRM, else log.
    Returns False if signature invalid (caller should return 403).
    """
    if headers and url:
        signature = headers.get("X-Twilio-Signature")
        if signature:
            params = payload.get("raw") or {}
            if isinstance(params, dict) and not _validate_twilio_signature(url, params, signature):
                logger.warning("Invalid Twilio signature")
                return False

    session = SessionLocal()
    try:
        from_phone = payload.get("from")
        body = (payload.get("body") or "").strip()
        sid = payload.get("sid")
        from_phone_norm = normalize_phone(from_phone) or from_phone

        if sid:
            existing = session.query(Message).filter(Message.provider_id == sid).first()
            if existing:
                logger.info("Duplicate Twilio message SID ignored", sid=sid)
                return

        # Link to lead: latest lead for this phone (any client)
        lead = session.query(Lead).filter(Lead.phone == from_phone_norm).order_by(Lead.id.desc()).first()
        if not lead:
            lead = session.query(Lead).filter(Lead.phone == from_phone).order_by(Lead.id.desc()).first()
        lead_id = lead.id if lead else None

        msg = Message(
            lead_id=lead_id,
            provider_id=sid,
            direction="inbound",
            body=body,
            status="received",
            metadata=payload,
        )
        session.add(msg)
        session.commit()

        # STOP: hard stop, cancel follow-ups
        if body.upper().strip() in STOP_TOKENS:
            st = session.query(Stop).filter(Stop.phone == from_phone_norm).first()
            if not st:
                st = session.query(Stop).filter(Stop.phone == from_phone).first()
            if not st:
                st = Stop(phone=from_phone_norm or from_phone)
                session.add(st)
                session.commit()
            logger.info("Recorded STOP for phone", phone=from_phone_norm or from_phone)
            session.add(
                EventLog(
                    lead_id=lead_id,
                    client_id=lead.client_id if lead else None,
                    event_type="stop_event",
                    payload={"phone": from_phone_norm or from_phone, "body": body},
                )
            )
            session.commit()
            # Cancel pending follow-ups for any lead with this phone
            if lead_id:
                cancel_followups_for_lead(lead_id)
            for other in session.query(Lead).filter(Lead.phone == (from_phone_norm or from_phone)).all():
                if other.id != lead_id:
                    cancel_followups_for_lead(other.id)
            return

        # CONFIRM: parse datetime, find proposal, book if slot free
        parsed = _parse_confirm_datetime(body)
        if parsed and lead_id and lead:
            date_str, hour, minute = parsed
            config = get_client_config(lead.client_id)
            if not config:
                _send_clarification(lead, "We couldn't verify your booking. Please reply with CONFIRM and the exact time we sent you, or call us.")
                session.add(
                    EventLog(lead_id=lead_id, client_id=lead.client_id, event_type="confirmation_failed", payload={"reason": "no_config", "body": body})
                )
                session.commit()
                return
            # Latest proposal for this lead
            prop = session.query(Proposal).filter(Proposal.lead_id == lead_id).order_by(Proposal.proposed_at.desc()).first()
            if not prop:
                _send_clarification(lead, "We don't have a proposed slot for you. Reply with the exact time we sent, e.g. CONFIRM 2026-03-25T10:00, or call us.")
                session.add(EventLog(lead_id=lead_id, client_id=lead.client_id, event_type="confirmation_failed", payload={"reason": "no_proposal", "body": body}))
                session.commit()
                return
            slot_start = prop.slot_start
            # Normalize to date and compare hour/minute
            if slot_start.strftime("%Y-%m-%d") != date_str or slot_start.hour != hour or slot_start.minute != minute:
                _send_clarification(lead, f"We expected CONFIRM {slot_start.strftime('%Y-%m-%dT%H:%M')}. Please reply with that exact time or call us.")
                session.add(EventLog(lead_id=lead_id, client_id=lead.client_id, event_type="confirmation_mismatch", payload={"body": body, "expected": slot_start.isoformat()}))
                session.commit()
                return
            # Re-check calendar and book
            try:
                provider_booking_id = create_booking(
                    config,
                    prop.slot_start,
                    prop.slot_end,
                    lead_id,
                    {"summary": f"Appointment Lead {lead_id}", "description": f"Lead ID: {lead_id}"},
                )
            except CalendarAdapterError as e:
                logger.warning("Booking failed", lead_id=lead_id, error=str(e))
                session.add(
                    EventLog(lead_id=lead_id, client_id=lead.client_id, event_type="booking_failed", payload={"reason": str(e), "slot": slot_start.isoformat()})
                )
                session.commit()
                _send_clarification(lead, "That slot is no longer available. We'll send you a new option shortly or call us.")
                return
            booking = Booking(
                lead_id=lead_id,
                provider=config.get("google_calendar_id") and "google_calendar" or "calendly",
                provider_booking_id=provider_booking_id,
                start=prop.slot_start,
                end=prop.slot_end,
                status="booked",
                reason=None,
                metadata={},
            )
            session.add(booking)
            lead.state = "booked"
            session.commit()
            confirm_msg = f"Your appointment is confirmed for {slot_start.strftime('%Y-%m-%d at %H:%M')}. We'll see you then."
            send_sms(to=lead.phone, body=confirm_msg, lead_id=lead_id, idempotency_key="confirmation_sms", message_type="confirmation")
            session.add(
                EventLog(lead_id=lead_id, client_id=lead.client_id, event_type="booking_confirmed", payload={"booking_id": booking.id, "provider_id": provider_booking_id})
            )
            session.commit()
            return

        if parsed and not lead_id:
            session.add(EventLog(lead_id=None, client_id=None, event_type="confirmation_received_no_lead", payload={"body": body}))
            session.commit()
            return

        session.add(EventLog(lead_id=lead_id, client_id=lead.client_id if lead else None, event_type="inbound_sms", payload={"body": body, "provider_id": sid}))
        session.commit()
    finally:
        session.close()


def _send_clarification(lead: Lead, body: str) -> None:
    send_sms(to=lead.phone, body=body, lead_id=lead.id)


# --- Voice ---
import json
from datetime import datetime

CALL_STATE_KEY_PREFIX = "voice_call:"


def _call_state_get(call_sid: str):
    from redis import Redis
    import os
    r = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    key = f"{CALL_STATE_KEY_PREFIX}{call_sid}"
    raw = r.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw.decode())
    except Exception:
        return None


def _call_state_set(call_sid: str, state: dict, ttl_seconds: int = 3600) -> None:
    from redis import Redis
    import os
    r = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    key = f"{CALL_STATE_KEY_PREFIX}{call_sid}"
    r.setex(key, ttl_seconds, json.dumps(state, default=str))


def handle_inbound_voice(payload: dict, request_url: str = "", query_params: dict = None) -> str:
    """
    Handle Twilio Voice webhook. Returns TwiML string.
    Flow: Greet -> Press 1 for scheduling -> (find lead, get slot) -> We have X at Y, press 1 to confirm, 2 for another -> on 1: book, SMS, goodbye.
    """
    query_params = query_params or {}
    form = payload.get("raw") or payload
    call_sid = form.get("CallSid")
    from_phone = form.get("From")
    digits = (form.get("Digits") or "").strip()
    step = query_params.get("step", "")
    public_url = os.getenv("PUBLIC_URL", "").rstrip("/")

    session = SessionLocal()
    try:
        # Persist or update Call record
        call_row = session.query(Call).filter(Call.provider_id == call_sid).first()
        if not call_row:
            lead = session.query(Lead).filter(Lead.phone == from_phone).order_by(Lead.id.desc()).first()
            if not lead:
                lead = session.query(Lead).filter(Lead.phone == normalize_phone(from_phone)).order_by(Lead.id.desc()).first()
            lead_id = lead.id if lead else None
            call_row = Call(lead_id=lead_id, provider_id=call_sid, status="in_progress", metadata=form)
            session.add(call_row)
            session.commit()
            session.add(EventLog(lead_id=lead_id, client_id=lead.client_id if lead else None, event_type="call_started", payload={"call_sid": call_sid, "from": from_phone}))
            session.commit()
    finally:
        session.close()

    # Initial: no step, no digits -> greet and gather
    if not step and not digits:
        action = f"{public_url}/webhook/twilio/voice?step=schedule" if public_url else "/webhook/twilio/voice?step=schedule"
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Gather numDigits="1" action="{action}" timeout="5"><Say>Press 1 to schedule an appointment.</Say></Gather><Say>We did not receive your selection. Goodbye.</Say><Hangup/></Response>'

    # After gather: step=schedule, digits=1 -> find lead, get slot, store state, say slot and ask confirm
    if step == "schedule" and digits == "1":
        session = SessionLocal()
        try:
            lead = session.query(Lead).filter(Lead.phone == from_phone).order_by(Lead.id.desc()).first()
            if not lead:
                lead = session.query(Lead).filter(Lead.phone == normalize_phone(from_phone)).order_by(Lead.id.desc()).first()
            if not lead:
                return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>We do not have your number on file. Please sign up online first. Goodbye.</Say><Hangup/></Response>'
            config = get_client_config(lead.client_id)
            if not config or not _get_adapter(config):
                return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>We cannot check availability right now. Please try again later or reply to our text. Goodbye.</Say><Hangup/></Response>'
            from datetime import timedelta
            tz_str = config.get("timezone", "UTC")
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_str)
                now = datetime.now(tz)
            except Exception:
                now = datetime.utcnow()
                tz = None
            start_date = now
            end_date = now + timedelta(days=7)
            slots = list_free_slots(config, start_date, end_date, tz_str)
            if not slots:
                return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>We are fully booked. We will be in touch. Goodbye.</Say><Hangup/></Response>'
            slot_start, slot_end = slots[0]
            slot_str = slot_start.strftime("%A, %B %d at %I %M %p").replace(" 0", " ")
            _call_state_set(call_sid, {"lead_id": lead.id, "client_id": lead.client_id, "slot_start": slot_start.isoformat(), "slot_end": slot_end.isoformat(), "slot_index": 0})
            action_confirm = f"{public_url}/webhook/twilio/voice?step=confirm" if public_url else "/webhook/twilio/voice?step=confirm"
            return f'<?xml version="1.0" encoding="UTF-8"?><Response><Gather numDigits="1" action="{action_confirm}" timeout="5"><Say>We have availability on {slot_str}. Press 1 to confirm, or 2 for another time.</Say></Gather><Say>Goodbye.</Say><Hangup/></Response>'
        finally:
            session.close()

    # step=confirm, digits=1 -> book and SMS
    if step == "confirm" and digits == "1":
        state = _call_state_get(call_sid)
        if not state:
            return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Session expired. Please call back. Goodbye.</Say><Hangup/></Response>'
        session = SessionLocal()
        try:
            lead_id = state["lead_id"]
            client_id = state["client_id"]
            slot_start = datetime.fromisoformat(state["slot_start"])
            slot_end = datetime.fromisoformat(state["slot_end"])
            lead = session.query(Lead).filter(Lead.id == lead_id).first()
            config = get_client_config(client_id) if lead else None
            if not config or not lead:
                return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Error. Goodbye.</Say><Hangup/></Response>'
            try:
                provider_booking_id = create_booking(
                    config, slot_start, slot_end, lead_id, {"summary": f"Voice booking Lead {lead_id}"}
                )
            except CalendarAdapterError as e:
                logger.warning("Voice booking failed", lead_id=lead_id, error=str(e))
                session.add(EventLog(lead_id=lead_id, client_id=client_id, event_type="voice_booking_failed", payload={"reason": str(e)}))
                session.commit()
                return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>That slot is no longer available. We will send you a text with options. Goodbye.</Say><Hangup/></Response>'
            provider_name = "google_calendar" if config.get("google_calendar_id") else "calendly"
            booking = Booking(lead_id=lead_id, provider=provider_name, provider_booking_id=provider_booking_id, start=slot_start, end=slot_end, status="booked", metadata={})
            session.add(booking)
            lead.state = "booked"
            call_row = session.query(Call).filter(Call.provider_id == call_sid).first()
            if call_row:
                call_row.status = "completed"
            session.add(EventLog(lead_id=lead_id, client_id=client_id, event_type="voice_booking_confirmed", payload={"booking_id": booking.id}))
            session.commit()
            send_sms(to=lead.phone, body=f"Your appointment is confirmed for {slot_start.strftime('%Y-%m-%d at %H:%M')}.", lead_id=lead_id, idempotency_key="voice_confirm_sms", message_type="confirmation")
        finally:
            session.close()
        return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>You are all set. We have sent a confirmation by text. Goodbye.</Say><Hangup/></Response>'

    # step=confirm, digits=2 -> next slot
    if step == "confirm" and digits == "2":
        state = _call_state_get(call_sid)
        if not state:
            return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Session expired. Goodbye.</Say><Hangup/></Response>'
        session = SessionLocal()
        try:
            lead = session.query(Lead).filter(Lead.id == state["lead_id"]).first()
            config = get_client_config(state["client_id"]) if lead else None
            if not config:
                return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Goodbye.</Say><Hangup/></Response>'
            from datetime import timedelta
            idx = int(state.get("slot_index", 0)) + 1
            tz_str = config.get("timezone", "UTC")
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_str)
                now = datetime.now(tz)
            except Exception:
                now = datetime.utcnow()
            start_date = now
            end_date = now + timedelta(days=7)
            slots = list_free_slots(config, start_date, end_date, tz_str)
            if idx >= len(slots):
                return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>No more slots. We will text you. Goodbye.</Say><Hangup/></Response>'
            slot_start, slot_end = slots[idx]
            slot_str = slot_start.strftime("%A, %B %d at %I %M %p").replace(" 0", " ")
            _call_state_set(call_sid, {"lead_id": state["lead_id"], "client_id": state["client_id"], "slot_start": slot_start.isoformat(), "slot_end": slot_end.isoformat(), "slot_index": idx})
            action_confirm = f"{public_url}/webhook/twilio/voice?step=confirm" if public_url else "/webhook/twilio/voice?step=confirm"
            return f'<?xml version="1.0" encoding="UTF-8"?><Response><Gather numDigits="1" action="{action_confirm}" timeout="5"><Say>We have {slot_str}. Press 1 to confirm, 2 for another.</Say></Gather><Say>Goodbye.</Say><Hangup/></Response>'
        finally:
            session.close()

    # Default
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Goodbye.</Say><Hangup/></Response>'
