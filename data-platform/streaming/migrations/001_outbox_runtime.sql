-- Streaming runtime layer on top of event_outbox table.
-- Requires contracts/database/schema.v1.sql to be applied first.

BEGIN;

CREATE OR REPLACE FUNCTION notify_event_outbox_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  payload_text text;
BEGIN
  payload_text := json_build_object(
    'id', NEW.id,
    'aggregate_type', NEW.aggregate_type,
    'aggregate_id', NEW.aggregate_id,
    'event_type', NEW.event_type,
    'event_version', NEW.event_version,
    'payload', NEW.payload,
    'trace_id', NEW.trace_id,
    'created_at', NEW.created_at
  )::text;

  PERFORM pg_notify('infraguard_outbox', payload_text);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_event_outbox_notify_insert ON event_outbox;
CREATE TRIGGER trg_event_outbox_notify_insert
AFTER INSERT ON event_outbox
FOR EACH ROW EXECUTE FUNCTION notify_event_outbox_insert();

CREATE OR REPLACE FUNCTION dequeue_outbox_events(p_batch_size integer DEFAULT 100)
RETURNS TABLE(
  id bigint,
  aggregate_type text,
  aggregate_id text,
  event_type text,
  event_version text,
  payload jsonb,
  trace_id text,
  created_at timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH picked AS (
    SELECT eo.id
    FROM event_outbox eo
    WHERE eo.status = 'pending'
      AND eo.next_attempt_at <= now()
    ORDER BY eo.created_at ASC
    LIMIT GREATEST(p_batch_size, 1)
    FOR UPDATE SKIP LOCKED
  ),
  updated AS (
    UPDATE event_outbox eo
    SET status = 'published',
        published_at = now()
    FROM picked
    WHERE eo.id = picked.id
    RETURNING
      eo.id,
      eo.aggregate_type,
      eo.aggregate_id,
      eo.event_type,
      eo.event_version,
      eo.payload,
      eo.trace_id,
      eo.created_at
  )
  SELECT
    updated.id,
    updated.aggregate_type,
    updated.aggregate_id,
    updated.event_type,
    updated.event_version,
    updated.payload,
    updated.trace_id,
    updated.created_at
  FROM updated;
END;
$$;

CREATE OR REPLACE FUNCTION mark_outbox_event_failed(
  p_event_id bigint,
  p_retry_delay_seconds integer DEFAULT 30
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE event_outbox
  SET status = 'failed',
      retry_count = retry_count + 1,
      next_attempt_at = now() + make_interval(secs => GREATEST(p_retry_delay_seconds, 1))
  WHERE id = p_event_id;
END;
$$;

COMMIT;
