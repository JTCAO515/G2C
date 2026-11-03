-- local runtime only: erased private bytes and permanent barriers cannot return.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_run_payload_erasure)
 OR EXISTS(SELECT 1 FROM cj_run_metered_operation WHERE input_bytes IS NULL)
 OR EXISTS(SELECT 1 FROM cj_run_step_usage WHERE input_bytes IS NULL)
 OR EXISTS(SELECT 1 FROM cj_run_record WHERE usage_command_bytes IS NOT NULL AND usage_input_bytes IS NULL)
 THEN RAISE EXCEPTION 'original memory payload erasure evidence retained'; END IF;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['cj_run_record','cj_run_event','cj_run_step_usage','cj_run_metered_operation',
  'cj_run_background_job','cj_message_trip_reference','cj_message_edit_reference'] LOOP
  EXECUTE format('DROP TRIGGER payload_write_barrier ON %I',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['cj_message_receipt','cj_message_chat','cj_message_delivery','cj_message_trip_reference',
  'cj_message_edit_reference','cj_run_record','cj_run_event','cj_run_step_usage','cj_run_metered_operation',
  'cj_run_metered_binding','cj_run_background_job'] LOOP
  EXECUTE format('DROP POLICY payload_memory_read ON %I',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['cj_run_record','cj_run_step_usage','cj_run_metered_operation','cj_run_background_job',
  'cj_message_trip_reference','cj_message_edit_reference','cj_message_delivery'] LOOP
  EXECUTE format('DROP POLICY payload_memory_update ON %I',t);
 END LOOP;
END $$;
DROP POLICY payload_run_insert ON cj_run_record;
DROP POLICY payload_run_update ON cj_run_record;
DROP POLICY payload_event_insert ON cj_run_event;
DROP POLICY payload_step_insert ON cj_run_step_usage;
DROP POLICY payload_operation_insert ON cj_run_metered_operation;
DROP POLICY payload_job_insert ON cj_run_background_job;
DROP POLICY payload_job_update ON cj_run_background_job;
DROP TRIGGER payload_step_original ON cj_run_step_usage;
DROP TRIGGER payload_operation_original ON cj_run_metered_operation;
DROP TRIGGER payload_trip_reference ON cj_message_trip_reference;
DROP TRIGGER payload_edit_reference ON cj_message_edit_reference;
REVOKE UPDATE(input_bytes) ON cj_run_step_usage,cj_run_metered_operation,cj_run_background_job FROM cj_local_cleanup;
REVOKE UPDATE(usage_input_bytes) ON cj_run_record FROM cj_local_cleanup;
REVOKE UPDATE(source_content,content_sha256) ON cj_message_trip_reference,cj_message_edit_reference FROM cj_local_cleanup;
REVOKE UPDATE(acknowledged) ON cj_message_delivery FROM cj_local_cleanup;
ALTER TABLE cj_run_step_usage DROP CONSTRAINT payload_step_erased,ALTER COLUMN input_bytes SET NOT NULL;
ALTER TABLE cj_run_metered_operation DROP CONSTRAINT payload_operation_erased,ALTER COLUMN input_bytes SET NOT NULL;
ALTER TABLE cj_run_record DROP CONSTRAINT payload_run_erased,
 ADD CONSTRAINT cj_run_record_check CHECK((usage_command_bytes IS NULL)=(usage_input_bytes IS NULL));
CREATE OR REPLACE FUNCTION cj_run_guard_original_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.scope,NEW.run_id,NEW.conversation_id,NEW.generation,NEW.message_id,
     NEW.message_sequence,NEW.usage_command_bytes,NEW.usage_input_bytes)
  IS DISTINCT FROM (OLD.scope,OLD.run_id,OLD.conversation_id,OLD.generation,OLD.message_id,
     OLD.message_sequence,OLD.usage_command_bytes,OLD.usage_input_bytes)
 THEN RAISE EXCEPTION 'immutable original run association'; END IF;
 RETURN NEW;
END $$;
DROP FUNCTION cj_payload_input_guard(),cj_payload_reference_guard(),cj_payload_write_barrier(),
 cj_payload_run_current(text,text),cj_payload_input_erased(text,text,text,text,bytea),cj_payload_job_current(text,text,text);
DROP TABLE cj_run_payload_erasure;
DROP FUNCTION cj_payload_write(text,text),cj_payload_plan(text),cj_payload_barrier_key(text),cj_payload_key(text,text[]);
