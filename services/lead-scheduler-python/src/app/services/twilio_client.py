from twilio.rest import Client
from loguru import logger
import os

_twilio_client = None

def get_twilio_client():
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    return _twilio_client

def send_sms(to: str, body: str, status_callback: str = None):
    client = get_twilio_client()
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    logger.info("Sending SMS", to=to, body=body)
    message = client.messages.create(
        to=to,
        from_=from_number,
        body=body,
        status_callback=status_callback
    )
    return message