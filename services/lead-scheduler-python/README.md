# SMS & Voice Scheduling Automation (Backend-only)

This project implements a deterministic backend scheduling automation platform:
- Twilio SMS & Voice integrations (inbound and outbound)
- Google Calendar integration for booking
- Deterministic scheduling rules, idempotency, and strict stop/opt-out handling
- Per-client configuration and comprehensive logging
- Postgres for persistence, Dockerized for easy deployment

See config.example.env for required environment variables.

To run locally:
1. Copy config.example.env to .env and set DATABASE_URL, REDIS_URL, TWILIO_*, PUBLIC_URL, optional WEBHOOK_SECRET and GOOGLE_APPLICATION_CREDENTIALS.
2. Start Postgres and Redis (e.g. `docker-compose up -d db redis`).
3. Create tables: from project root run `PYTHONPATH=. python scripts/init_db.py`.
4. Start app and worker: `docker-compose up app worker` or `uvicorn src.app.main:app --reload` and `rq worker followups leads`.

To run tests (with venv): `python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest && PYTHONPATH=. .venv/bin/pytest tests/ -v`

Endpoints:
- POST /webhook/lead
- POST /webhook/twilio/sms
- POST /webhook/twilio/voice
- POST /webhook/twilio/status

This repo is a starting scaffold. Full implementation delivered after credentials and repo access are provided.