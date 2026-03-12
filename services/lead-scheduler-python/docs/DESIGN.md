# Design: SMS & Voice Scheduling Automation (Backend-only)

## Goals
- Deterministic scheduling: booking only when explicit confirmation criteria are met.
- Twilio integration: inbound/outbound SMS and Voice; status & transcription logging.
- Google Calendar / Calendly adapter for availability and booking.
- Per-client configuration without code changes.
- Idempotency and duplicate prevention.
- Immediate stop/opt-out enforcement (hard stop).
- Comprehensive logging & audit trail.

---

## Core entities (short)
- Client: business/customer using the system; stores configuration JSON.
- Lead: incoming lead record (source payload, phone, status/state).
- Message: inbound/outbound SMS records (Twilio SID, body, status).
- Call: inbound voice calls (Twilio SID, recording/transcript metadata).
- Booking: appointment attempt and results (calendar provider id, slot/time, status, reason).
- Stop: hard-stop opt-out records (phone, who/when).
- Log/Audit: event records for decisions, failures, transcripts.

---

## ER Diagram (textual)

Clients (1) --- (N) Leads
Leads (1) --- (N) Messages
Leads (1) --- (N) Calls
Leads (1) --- (N) Bookings
Clients (1) --- (N) Stops
Messages (N) --- (1) Leads
Bookings (N) --- (1) Leads

Simplified tables:
- clients: id, name, config (JSONB), created_at
- leads: id, client_id, external_id, phone, payload (JSONB), state, created_at
- messages: id, lead_id, provider_id, direction, body, status, metadata, created_at
- calls: id, lead_id, provider_id, recording_url, transcript, status, metadata, created_at
- bookings: id, lead_id, provider, provider_booking_id, start, end, status, reason, metadata
- stops: id, phone (normalized), client_id (nullable), created_at

Notes:
- Unique constraint: (client_id, external_id) to enforce idempotency for lead ingestion.
- Unique index on messages(provider_id) and/or idempotency keys to prevent duplicate sends.

---

## Primary sequences

1) Lead ingestion (CRM, Zapier, webhook)
- POST /webhook/lead {external_id, client_id, phone, payload}
- Validate idempotency: if external_id for client exists → respond OK, no duplicate sends.
- Normalize phone; check stops table → if stopped, log and ignore.
- Create lead record with state = "new".
- Enqueue processing: scheduler.process_lead(lead_id)

2) Scheduler for SMS flows
- Load client config (business hours, min_buffer, slot_length, followups).
- If config says "propose slot" or lead has a preferred window:
  - Query calendar adapter for free slots matching rules.
  - If slot found and deterministic confirmation is present (e.g., lead replied "YES" to slot) → attempt booking.
  - If no explicit confirmation: send proposal SMS with deterministic format requiring explicit confirmation (e.g., "Reply CONFIRM 2026-03-25T10:00 to book").
- Follow-up engine: scheduled jobs for retries until max attempts or until opt-out/confirmed.

3) Twilio inbound SMS webhook
- Verify Twilio signature.
- Normalize message body and phone.
- If STOP/OPT-OUT tokens → insert into stops table, cancel pending follow-ups, mark leads accordingly, log event.
- If message is a confirmation (matches deterministic grammar) → locate lead, validate proposed slot, check calendar availability, book if free, send confirmation SMS and record booking/log.

4) Twilio Voice inbound call
- TwiML response asks for user preference (DTMF or brief speech).
- Record or use speech-to-text to extract date/time or "choose slot".
- If user directly confirms a slot during call, book after availability check; send SMS confirmation after booking and log transcript.
- Always require explicit confirmation before writing to calendar.

5) Booking flow (calendar adapter)
- Check availability, create event with metadata linking to lead and client.
- On success: record booking.status = "booked"; send confirmation SMS.
- On failure/conflict: record reason; use fallback (ask user for alternate windows or route to manual hold).

---

## Deterministic rule language (mini-DSL)
Purpose: express booking/confirmation rules in an unambiguous, machine-evaluable way in client config JSON.

Example config snippet (JSON):
{
  "business_hours": {
    "monday": ["09:00-17:00"],
    "tuesday": ["09:00-17:00"],
    ...
  },
  "slot_length_minutes": 30,
  "min_lead_time_minutes": 60,
  "max_proposals": 3,
  "confirmation_requirement": {
    "type": "explicit_token",                // or "explicit_phrase"
    "token_format": "CONFIRM {ISO_DATETIME}" // exact reply grammar required
  },
  "followups": [
    {"after_minutes": 15, "message": "Reminder: reply CONFIRM {ISO_DATETIME} to book."},
    {"after_minutes": 60, "message": "Final reminder: reply CONFIRM {ISO_DATETIME}."}
  ],
  "stop_policy": {
    "global": true
  }
}

Confirmation grammar:
- Explicit token: reply must start with token word "CONFIRM" followed by the ISO datetime previously proposed.
- Explicit phrase: e.g., "Yes, book 2026-03-25 10:00" — requires classifier (LLM allowed sparingly) or regex-based parser with high confidence thresholds.

Deterministic rules (examples):
- Only auto-book if exact explicit_token reply is received and calendar slot remains available.
- If parsing confidence < 0.95, do not autobook; send a clarification SMS instead.

---

## Idempotency & duplicate prevention
- For inbound lead: enforce unique(client_id, external_id).
- For outgoing messages: store attempted sends keyed by (lead_id, message_type, idempotency_key) and unique constraint to prevent duplicates.
- For webhook retries: accept X-Idempotency-Key header or use provider SID to dedupe.

---

## Stop / opt-out enforcement
- STOP tokens recognized (case-insensitive): "STOP", "UNSUBSCRIBE", "CANCEL", etc.
- Adding phone to stops table stops further outbound sends across all clients (configurable per-client).
- All pending follow-ups for that phone/lead canceled immediately.
- STOP events logged with timestamp and origin.

---

## Logs & audit
- All events (ingest, outbound send, inbound msg, call, booking attempt, booking result) are logged in an events table with JSON detail.
- Each event stores reason and references (lead_id, client_id, twilio_sid, booking_id).
- Transcripts stored as text in calls with metadata.

---

## Security
- Twilio request signature verification for Twilio webhooks.
- HMAC / shared secret verification for CRM/Zapier webhooks.
- Secrets in environment variables / secret store.
- Least privilege for Google Calendar service account.

---

## Operational notes
- Local development: use Docker Compose (Postgres) and ngrok for Twilio callbacks.
- Testing: mock Twilio / Calendar APIs for unit/integration tests; provide end-to-end tests with test credentials.
