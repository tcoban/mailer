CREATE TYPE message_status AS ENUM (
  'QUEUED',
  'RETRY_PENDING',
  'SENT',
  'DELIVERED',
  'BOUNCED',
  'FAILED',
  'CANCELLED'
);

CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  status message_status NOT NULL DEFAULT 'QUEUED',
  status_reason TEXT,
  provider_message_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE message_status_transitions (
  from_status message_status NOT NULL,
  to_status message_status NOT NULL,
  PRIMARY KEY (from_status, to_status)
);

INSERT INTO message_status_transitions (from_status, to_status) VALUES
  ('QUEUED', 'SENT'),
  ('QUEUED', 'RETRY_PENDING'),
  ('QUEUED', 'FAILED'),
  ('QUEUED', 'CANCELLED'),
  ('RETRY_PENDING', 'SENT'),
  ('RETRY_PENDING', 'FAILED'),
  ('RETRY_PENDING', 'CANCELLED'),
  ('SENT', 'DELIVERED'),
  ('SENT', 'BOUNCED'),
  ('SENT', 'FAILED');

CREATE OR REPLACE FUNCTION validate_message_status_transition()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status = OLD.status THEN
    RETURN NEW;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM message_status_transitions
    WHERE from_status = OLD.status
      AND to_status = NEW.status
  ) THEN
    RAISE EXCEPTION 'Invalid message status transition from % to %', OLD.status, NEW.status;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER enforce_message_status_transition
BEFORE UPDATE OF status ON messages
FOR EACH ROW
EXECUTE FUNCTION validate_message_status_transition();
