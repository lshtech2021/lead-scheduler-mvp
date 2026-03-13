"""Unit tests for utils (phone, config, confirmation parsing)."""
import pytest
from src.app.utils.phone import normalize_phone


def test_normalize_phone_empty():
    assert normalize_phone(None) is None
    assert normalize_phone("") is None
    assert normalize_phone("   ") is None


def test_normalize_phone_us_10_digits():
    assert normalize_phone("5551234567") == "+15551234567"
    assert normalize_phone("(555) 123-4567") == "+15551234567"


def test_normalize_phone_us_11_digits():
    assert normalize_phone("15551234567") == "+15551234567"


def test_normalize_phone_preserves_plus():
    assert normalize_phone("+15551234567") == "+15551234567"


def test_confirm_parsing():
    from src.app.services.twilio_webhook import _parse_confirm_datetime
    assert _parse_confirm_datetime("CONFIRM 2026-03-25T10:00") == ("2026-03-25", 10, 0)
    assert _parse_confirm_datetime("confirm 2026-03-25 14:30") == ("2026-03-25", 14, 30)
    assert _parse_confirm_datetime("CONFIRM 2026-03-25T09:15") == ("2026-03-25", 9, 15)
    assert _parse_confirm_datetime("random text") is None
    assert _parse_confirm_datetime("CONFIRM invalid") is None
