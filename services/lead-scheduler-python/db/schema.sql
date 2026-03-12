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

CREATE TABLE stops (
  id SERIAL PRIMARY KEY,
  phone TEXT UNIQUE,
  lead_id INT,
  client_id INT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);