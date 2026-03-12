from rq import Queue
from redis import Redis
import os
from datetime import timedelta
from .twilio_client import send_sms
from loguru import logger

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(redis_url)
q = Queue("followups", connection=redis_conn)

def enqueue_followup(lead_id: int, to: str, body: str, delay_seconds: int):
    logger.info("Enqueue followup", lead_id=lead_id, to=to, delay_seconds=delay_seconds)
    q.enqueue_in(timedelta(seconds=delay_seconds), send_followup_job, lead_id, to, body)

def send_followup_job(lead_id: int, to: str, body: str):
    # This runs in the worker process
    logger.info("Sending followup job", lead_id=lead_id, to=to)
    send_sms(to=to, body=body, lead_id=lead_id)