-- Module candidate for NEW isolated databases only. NOT a formal migration.
-- No roles/grants/RLS changes. Trusted composition must provision scope explicitly.
CREATE TABLE cj_run_scope (
  scope text PRIMARY KEY CHECK (length(scope)>0),
  epoch text NOT NULL CHECK (length(epoch)>0),
  active boolean NOT NULL
);
CREATE TABLE cj_run_record (
  scope text NOT NULL REFERENCES cj_run_scope(scope),
  run_id text NOT NULL,
  conversation_id text NOT NULL,
  generation text NOT NULL,
  message_id text NOT NULL,
  message_sequence bigint NOT NULL CHECK (message_sequence>0),
  status text NOT NULL CHECK (status IN ('queued','running','completed','failed','cancelled','context_invalid','unknown')),
  event_sequence bigint NOT NULL CHECK (event_sequence>=0),
  expires_at timestamptz NOT NULL,
  usage_command_bytes bytea,
  usage_input_bytes bytea,
  CHECK ((usage_command_bytes IS NULL) = (usage_input_bytes IS NULL)),
  PRIMARY KEY(scope,run_id),
  UNIQUE(scope,message_id),
  UNIQUE(scope,conversation_id,generation,message_sequence)
);
CREATE TABLE cj_run_event (
  scope text NOT NULL,
  run_id text NOT NULL,
  sequence bigint NOT NULL CHECK (sequence>0),
  event_id text NOT NULL CHECK (length(event_id)>0),
  kind text NOT NULL CHECK (kind IN ('started','text_delta','effect_committed','completed','failed','cancelled','context_invalid','unknown')),
  value text NOT NULL,
  PRIMARY KEY(scope,run_id,sequence),
  UNIQUE(scope,run_id,event_id),
  FOREIGN KEY(scope,run_id) REFERENCES cj_run_record(scope,run_id),
  CHECK ((kind IN ('text_delta','effect_committed') AND length(value)>0)
      OR (kind NOT IN ('text_delta','effect_committed') AND value=''))
);
CREATE UNIQUE INDEX cj_run_one_terminal ON cj_run_event(scope,run_id)
  WHERE kind IN ('completed','failed','cancelled','context_invalid','unknown');
CREATE UNIQUE INDEX cj_run_one_effect ON cj_run_event(scope,run_id,value)
  WHERE kind='effect_committed';
-- Service mutations serialize on cj_run_scope, then lock/read the original record.
-- No deletion, retention cleanup, privilege policy or worker dispatch is activated.
-- Epoch rotation/active revocation writers must lock the same scope row.

-- Association is written only at original row creation. No backfill of legacy
-- unbound rows, even if they are still queued. Exact bytes remain immutable.
CREATE FUNCTION cj_run_guard_original_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.scope,NEW.run_id,NEW.conversation_id,NEW.generation,NEW.message_id,
      NEW.message_sequence,NEW.usage_command_bytes,NEW.usage_input_bytes)
     IS DISTINCT FROM
     (OLD.scope,OLD.run_id,OLD.conversation_id,OLD.generation,OLD.message_id,
      OLD.message_sequence,OLD.usage_command_bytes,OLD.usage_input_bytes) THEN
    RAISE EXCEPTION 'immutable original run association';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER cj_run_original_binding BEFORE UPDATE ON cj_run_record
FOR EACH ROW EXECUTE FUNCTION cj_run_guard_original_binding();
