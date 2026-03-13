-- Minimal schema snippet (expandable)
CREATE TABLE clients (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  config JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE leads (
  id SERIAL PRIMARY KEY,
  client_id INT REFERENCES clients(id),
  external_id TEXT,
  phone TEXT,
  payload JSONB,
  state TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  UNIQUE(client_id, external_id)
);

CREATE TABLE messages (
  id SERIAL PRIMARY KEY,
  lead_id INT REFERENCES leads(id),
  direction TEXT, -- inbound/outbound
  provider_id TEXT, -- twilio message sid
  body TEXT,
  status TEXT,
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE UNIQUE INDEX idx_messages_provider_id ON messages(provider_id) WHERE provider_id IS NOT NULL;

CREATE TABLE calls (
  id SERIAL PRIMARY KEY,
  lead_id INT REFERENCES leads(id),
  provider_id TEXT UNIQUE,
  recording_url TEXT,
  transcript TEXT,
  status TEXT,
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE bookings (
  id SERIAL PRIMARY KEY,
  lead_id INT REFERENCES leads(id),
  provider TEXT,
  provider_booking_id TEXT,
  start TIMESTAMP WITH TIME ZONE,
  "end" TIMESTAMP WITH TIME ZONE,
  status TEXT,
  reason TEXT,
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE event_logs (
  id SERIAL PRIMARY KEY,
  lead_id INT,
  client_id INT,
  event_type TEXT,
  payload JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE outbound_sends (
  id SERIAL PRIMARY KEY,
  lead_id INT NOT NULL REFERENCES leads(id),
  message_type TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  message_id INT REFERENCES messages(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  UNIQUE(lead_id, message_type, idempotency_key)
);

CREATE TABLE proposals (
  id SERIAL PRIMARY KEY,
  lead_id INT NOT NULL REFERENCES leads(id),
  slot_start TIMESTAMP WITH TIME ZONE NOT NULL,
  slot_end TIMESTAMP WITH TIME ZONE NOT NULL,
  proposed_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE stops (
  id SERIAL PRIMARY KEY,
  phone TEXT UNIQUE,
  lead_id INT,
  client_id INT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);