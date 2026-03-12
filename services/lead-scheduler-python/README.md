# SMS & Voice Scheduling Automation (Backend-only)

This project implements a deterministic backend scheduling automation platform:
- Twilio SMS & Voice integrations (inbound and outbound)
- Google Calendar integration for booking
- Deterministic scheduling rules, idempotency, and strict stop/opt-out handling
- Per-client configuration and comprehensive logging
- Postgres for persistence, Dockerized for easy deployment

See config.example.env for required environment variables.

To run locally:
1. Copy config.example.env -> .env and fill credentials
2. npm install
3. npm run migrate
4. npm run dev

Endpoints:
- POST /webhook/lead
- POST /webhook/twilio/sms
- POST /webhook/twilio/voice
- POST /webhook/twilio/status

This repo is a starting scaffold. Full implementation delivered after credentials and repo access are provided.