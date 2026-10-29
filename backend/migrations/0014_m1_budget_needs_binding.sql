-- Local-only scaffolding; not a product conversation/NEEDS relationship.
CREATE TABLE cj_message_needs_selection (
 message_scope text NOT NULL, conversation_id text NOT NULL, generation text NOT NULL,
 needs_scope text NOT NULL, needs_id text NOT NULL,
 PRIMARY KEY(message_scope,conversation_id,generation),
 FOREIGN KEY(message_scope,conversation_id,generation) REFERENCES cj_message_chat(scope,conversation_id,generation),
 FOREIGN KEY(needs_scope,needs_id) REFERENCES cj_needs_record(scope,needs_id)
);
CREATE TABLE cj_message_needs_binding (
 message_scope text NOT NULL, message_id text NOT NULL, run_id text NOT NULL,
 needs_scope text NOT NULL, needs_id text NOT NULL, needs_version bigint NOT NULL CHECK(needs_version>0),
 content_sha256 text NOT NULL CHECK(content_sha256 ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(message_scope,message_id), UNIQUE(message_scope,run_id),
 FOREIGN KEY(message_scope,message_id,run_id) REFERENCES cj_message_receipt(scope,message_id,run_id),
 FOREIGN KEY(needs_scope,needs_id,needs_version) REFERENCES cj_needs_revision(scope,needs_id,version)
);
CREATE TABLE cj_run_step_usage (
 scope text NOT NULL, run_id text NOT NULL, step_key text NOT NULL CHECK(step_key IN ('answer','draft')),
 attempt_id text NOT NULL CHECK(length(attempt_id) BETWEEN 1 AND 200),
 ledger_scope text NOT NULL REFERENCES cj_usage_ledger_candidate(scope_id),
 unit text NOT NULL CHECK(unit='provider_call'),
 period_start bigint NOT NULL CHECK(period_start>=0), period_end bigint NOT NULL CHECK(period_end>period_start),
 command_bytes bytea NOT NULL, input_bytes bytea NOT NULL,
 PRIMARY KEY(scope,run_id,step_key), UNIQUE(scope,attempt_id),
 FOREIGN KEY(scope,run_id) REFERENCES cj_run_record(scope,run_id)
);
ALTER TABLE cj_message_needs_selection ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_message_needs_selection FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_message_needs_binding ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_message_needs_binding FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_run_step_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_run_step_usage FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m1_selection_read ON cj_message_needs_selection FOR SELECT TO cj_m1_runtime
 USING(message_scope=nullif(current_setting('cj.message_scope',true),'') AND needs_scope=nullif(current_setting('cj.needs_scope',true),''));
CREATE POLICY cj_m1_binding_read ON cj_message_needs_binding FOR SELECT TO cj_m1_runtime
 USING(message_scope=nullif(current_setting('cj.message_scope',true),'') AND needs_scope=nullif(current_setting('cj.needs_scope',true),''));
CREATE POLICY cj_m1_binding_insert ON cj_message_needs_binding FOR INSERT TO cj_m1_runtime
 WITH CHECK(message_scope=nullif(current_setting('cj.message_scope',true),'') AND needs_scope=nullif(current_setting('cj.needs_scope',true),''));
CREATE POLICY cj_m1_step_read ON cj_run_step_usage FOR SELECT TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),'') AND ledger_scope=nullif(current_setting('cj.usage_scope',true),''));
CREATE POLICY cj_m1_step_insert ON cj_run_step_usage FOR INSERT TO cj_m1_runtime
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND ledger_scope=nullif(current_setting('cj.usage_scope',true),''));
GRANT SELECT ON cj_message_needs_selection TO cj_m1_runtime;
GRANT SELECT,INSERT ON cj_message_needs_binding,cj_run_step_usage TO cj_m1_runtime;
ALTER TABLE cj_needs_scope ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_scope FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_record FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_revision ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_needs_revision FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m1_needs_read ON cj_needs_scope FOR SELECT TO cj_m1_runtime USING(scope=nullif(current_setting('cj.needs_scope',true),''));
CREATE POLICY cj_m1_needs_read ON cj_needs_record FOR SELECT TO cj_m1_runtime USING(scope=nullif(current_setting('cj.needs_scope',true),''));
CREATE POLICY cj_m1_needs_read ON cj_needs_revision FOR SELECT TO cj_m1_runtime USING(scope=nullif(current_setting('cj.needs_scope',true),''));
GRANT SELECT ON cj_needs_scope,cj_needs_record,cj_needs_revision TO cj_m1_runtime;
CREATE POLICY cj_m1_usage_read ON cj_usage_ledger_candidate FOR SELECT TO cj_m1_runtime USING(scope_id=nullif(current_setting('cj.usage_scope',true),''));
CREATE POLICY cj_m1_usage_update ON cj_usage_ledger_candidate FOR UPDATE TO cj_m1_runtime
 USING(scope_id=nullif(current_setting('cj.usage_scope',true),'')) WITH CHECK(scope_id=nullif(current_setting('cj.usage_scope',true),''));
GRANT SELECT, UPDATE(ledger,revision) ON cj_usage_ledger_candidate TO cj_m1_runtime;
-- Shared leases use this same key with pg_advisory_xact_lock_shared.
CREATE FUNCTION cj_needs_fence_key(value text) RETURNS bigint LANGUAGE sql IMMUTABLE STRICT
 RETURN pg_catalog.hashtextextended('CJ-NEEDS-FENCE@1:' || value,0);
CREATE FUNCTION cj_needs_write_fence() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE selected_scope text;
BEGIN
 IF TG_OP='UPDATE' AND NEW.scope IS DISTINCT FROM OLD.scope THEN
   RAISE EXCEPTION 'immutable NEEDS scope';
 END IF;
 IF TG_OP='DELETE' THEN selected_scope:=OLD.scope; ELSE selected_scope:=NEW.scope; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(public.cj_needs_fence_key(selected_scope));
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE TRIGGER cj_needs_write_fence BEFORE INSERT OR UPDATE OR DELETE ON cj_needs_scope FOR EACH ROW EXECUTE FUNCTION cj_needs_write_fence();
CREATE TRIGGER cj_needs_write_fence BEFORE INSERT OR UPDATE OR DELETE ON cj_needs_record FOR EACH ROW EXECUTE FUNCTION cj_needs_write_fence();
CREATE TRIGGER cj_needs_write_fence BEFORE INSERT OR UPDATE OR DELETE ON cj_needs_revision FOR EACH ROW EXECUTE FUNCTION cj_needs_write_fence();
-- TRUNCATE does not fire row triggers and cannot participate in revision fencing.
CREATE FUNCTION cj_needs_reject_truncate() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN RAISE EXCEPTION 'NEEDS truncation unavailable while revision fence is enabled'; END $$;
CREATE TRIGGER cj_needs_no_truncate BEFORE TRUNCATE ON cj_needs_scope FOR EACH STATEMENT EXECUTE FUNCTION cj_needs_reject_truncate();
CREATE TRIGGER cj_needs_no_truncate BEFORE TRUNCATE ON cj_needs_record FOR EACH STATEMENT EXECUTE FUNCTION cj_needs_reject_truncate();
CREATE TRIGGER cj_needs_no_truncate BEFORE TRUNCATE ON cj_needs_revision FOR EACH STATEMENT EXECUTE FUNCTION cj_needs_reject_truncate();
ALTER TABLE cj_run_event DROP CONSTRAINT cj_run_event_kind_check, DROP CONSTRAINT cj_run_event_check,
 ADD CONSTRAINT cj_run_event_kind_check CHECK(kind IN ('started','text_delta','effect_committed','completed','failed','cancelled','context_invalid','unknown','draft_outcome','budget_denied')),
 ADD CONSTRAINT cj_run_event_check CHECK(
 (kind IN ('text_delta','effect_committed') AND length(value)>0)
 OR (kind='draft_outcome' AND value IN ('validation_failed','provider_failed','provider_unknown','budget_exhausted'))
 OR (kind='budget_denied' AND value IN ('answer','draft'))
 OR (kind NOT IN ('text_delta','effect_committed','draft_outcome','budget_denied') AND value=''));
