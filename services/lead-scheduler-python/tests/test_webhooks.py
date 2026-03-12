import pytest
from fastapi.testclient import TestClient
from src.app.main import app

client = TestClient(app)

def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

def test_lead_ingest_duplicate(tmp_path, monkeypatch):
    # This test is illustrative; a real test would connect to a test DB
    resp = client.post("/webhook/lead", json={"client_id": 1, "external_id": "abc123", "phone": "+15551234"})
    assert resp.status_code in (200, 201)