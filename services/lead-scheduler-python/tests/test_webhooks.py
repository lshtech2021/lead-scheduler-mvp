import pytest
from fastapi.testclient import TestClient
from src.app.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_lead_ingest_requires_body():
    """Empty body yields 422 (validation) or 400."""
    resp = client.post("/webhook/lead", content=b"", headers={"Content-Type": "application/json"})
    assert resp.status_code in (400, 422)


def test_twilio_voice_returns_twiml():
    """Voice webhook returns valid TwiML Response."""
    resp = client.post(
        "/webhook/twilio/voice",
        data={"CallSid": "CA123", "From": "+15551234567"},
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")
    assert "<Response>" in resp.text
    assert "<Say>" in resp.text or "<Gather>" in resp.text


def test_twilio_sms_returns_xml():
    """SMS webhook returns empty TwiML (no body required for empty response)."""
    resp = client.post(
        "/webhook/twilio/sms",
        data={"From": "+15551234567", "To": "+15550000000", "Body": "Hello", "MessageSid": "SM123"},
    )
    assert resp.status_code == 200
    assert "xml" in resp.headers.get("content-type", "").lower() or "application/xml" in resp.headers.get("content-type", "")