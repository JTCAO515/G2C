-- local runtime only: MESSAGE-SOURCE@1 type reservation and explicit end signal.
-- No new storage domain, role or DELETE grant. Existing forced RLS applies.
CREATE TYPE cj_conversation_type AS ENUM ('travel','service');
ALTER TABLE cj_message_chat
 ADD COLUMN conversation_type cj_conversation_type NOT NULL DEFAULT 'travel',
 ADD COLUMN end_id text,
 ADD COLUMN end_generation text,
 ADD COLUMN end_epoch bigint,
 ADD COLUMN end_sequence bigint,
 ADD CONSTRAINT cj_message_travel_only CHECK (conversation_type='travel'),
 ADD CONSTRAINT cj_message_end_shape CHECK (
   (end_id IS NULL AND end_generation IS NULL AND end_epoch IS NULL AND end_sequence IS NULL)
   OR (end_id IS NOT NULL AND end_id ~ '^[0-9a-f]{64}$' AND end_generation IS NOT NULL
       AND end_epoch IS NOT NULL AND end_epoch>=0 AND end_sequence IS NOT NULL AND end_sequence>=0));

CREATE FUNCTION cj_message_end_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM cj_message_scope WHERE scope=NEW.scope FOR UPDATE;
 IF OLD.end_id IS NOT NULL AND
    ROW(NEW.end_id,NEW.end_generation,NEW.end_epoch,NEW.end_sequence) IS DISTINCT FROM
    ROW(OLD.end_id,OLD.end_generation,OLD.end_epoch,OLD.end_sequence) THEN
  RAISE EXCEPTION 'message end immutable';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_message_end_immutable() FROM PUBLIC;
CREATE TRIGGER cj_message_end_immutable BEFORE UPDATE ON cj_message_chat
 FOR EACH ROW EXECUTE FUNCTION cj_message_end_immutable();

CREATE FUNCTION cj_message_no_send_after_end() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM cj_message_scope WHERE scope=NEW.scope FOR UPDATE;
 IF NOT EXISTS (SELECT 1 FROM cj_message_chat WHERE scope=NEW.scope
    AND conversation_id=NEW.conversation_id AND generation=NEW.generation
    AND active AND end_id IS NULL AND conversation_type='travel') THEN
  RAISE EXCEPTION 'message conversation unavailable';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_message_no_send_after_end() FROM PUBLIC;
CREATE TRIGGER cj_message_no_send_after_end BEFORE INSERT ON cj_message_receipt
 FOR EACH ROW EXECUTE FUNCTION cj_message_no_send_after_end();
