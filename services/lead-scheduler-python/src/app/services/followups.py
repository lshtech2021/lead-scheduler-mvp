from rq import Queue
from redis import Redis
import os
from datetime import timedelta
from .twilio_client import send_sms
from loguru import logger

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(redis_url)
q = Queue("followups", connection=redis_conn)
leads_queue = Queue("leads", connection=redis_conn)

FOLLOWUP_JOBS_KEY_PREFIX = "followup_jobs:"

def enqueue_followup(lead_id: int, to: str, body: str, delay_seconds: int, idempotency_key: str = None) -> str | None:
    """Enqueue a follow-up SMS. Stores job id in Redis for cancel on STOP. Returns job id if available."""
    logger.info("Enqueue followup", lead_id=lead_id, to=to, delay_seconds=delay_seconds)
    job = q.enqueue_in(timedelta(seconds=delay_seconds), send_followup_job, lead_id, to, body)
    if job and job.id:
        redis_conn.sadd(f"{FOLLOWUP_JOBS_KEY_PREFIX}{lead_id}", job.id)
        return job.id
    return None

def cancel_followups_for_lead(lead_id: int) -> None:
    """Cancel all pending follow-up jobs for this lead (e.g. on STOP)."""
    key = f"{FOLLOWUP_JOBS_KEY_PREFIX}{lead_id}"
    job_ids = redis_conn.smembers(key)
    for jid in job_ids:
        try:
            job = q.fetch_job(jid.decode() if isinstance(jid, bytes) else jid)
            if job and job.get_status() in ("queued", "scheduled"):
                job.cancel()
                logger.info("Cancelled followup job", lead_id=lead_id, job_id=job.id)
        except Exception as e:
            logger.warning("Failed to cancel followup job", lead_id=lead_id, error=str(e))
    redis_conn.delete(key)

def send_followup_job(lead_id: int, to: str, body: str):
    """Runs in worker. Checks stop list before sending; no reply after STOP."""
    from ..db import SessionLocal
    from ..models import Stop, Lead, EventLog
    session = SessionLocal()
    try:
        stop = session.query(Stop).filter(Stop.phone == to).first()
        if stop:
            logger.info("Skipping followup - phone on stop list", lead_id=lead_id, to=to)
            session.add(EventLog(lead_id=lead_id, client_id=None, event_type="followup_skipped", payload={"reason": "stop_list", "to": to}))
            session.commit()
            return
        if lead_id:
            lead = session.query(Lead).filter(Lead.id == lead_id).first()
            if lead and lead.state == "booked":
                logger.info("Skipping followup - lead already booked", lead_id=lead_id)
                session.add(EventLog(lead_id=lead_id, client_id=lead.client_id, event_type="followup_skipped", payload={"reason": "already_booked"}))
                session.commit()
                return
    finally:
        session.close()
    logger.info("Sending followup", lead_id=lead_id, to=to)
    send_sms(to=to, body=body, lead_id=lead_id)