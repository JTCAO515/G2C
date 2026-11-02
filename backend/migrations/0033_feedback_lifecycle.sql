-- local runtime only: FEEDBACK@1.0 original-action store and no-resurrection fence.
-- Do not backfill historical timing from migration time. Future events use DB UTC.
ALTER TABLE cj_run_event ADD COLUMN diagnostic_at timestamptz;
ALTER TABLE cj_run_event ALTER COLUMN diagnostic_at SET DEFAULT clock_timestamp();
CREATE TABLE cj_feedback_scope (
 scope_digest text PRIMARY KEY CHECK(scope_digest ~ '^[0-9a-f]{64}$'),
 retired boolean NOT NULL DEFAULT false
);
ALTER TABLE cj_feedback_scope ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_feedback_scope FORCE ROW LEVEL SECURITY;
CREATE POLICY feedback_runtime ON cj_feedback_scope TO cj_m1_runtime
 USING(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex'))
 WITH CHECK(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex') AND NOT retired);
GRANT SELECT,INSERT(scope_digest) ON cj_feedback_scope TO cj_m1_runtime;
-- Row lock only, as in M15: RLS permits no scope change, retired is not writable.
GRANT UPDATE(scope_digest) ON cj_feedback_scope TO cj_m1_runtime;
CREATE POLICY feedback_cleanup ON cj_feedback_scope TO cj_local_cleanup
 USING(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.cleanup_scope',true),''),'UTF8')),'hex'))
 WITH CHECK(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.cleanup_scope',true),''),'UTF8')),'hex')
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation WHERE subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND purpose='account' AND NOT blocked));
GRANT SELECT,INSERT,UPDATE(retired) ON cj_feedback_scope TO cj_local_cleanup;
CREATE FUNCTION cj_feedback_retire_once() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.retired AND NOT NEW.retired THEN RAISE EXCEPTION 'feedback scope retired'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_feedback_retire_once() FROM PUBLIC;
CREATE TRIGGER feedback_retire_once BEFORE UPDATE ON cj_feedback_scope FOR EACH ROW EXECUTE FUNCTION cj_feedback_retire_once();

CREATE POLICY feedback_runtime ON cj_feedback_action TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
GRANT SELECT,INSERT ON cj_feedback_action TO cj_m1_runtime;
CREATE FUNCTION cj_feedback_active_write() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM cj_feedback_scope WHERE scope_digest=encode(sha256(convert_to(NEW.scope,'UTF8')),'hex') AND NOT retired FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='feedback scope unavailable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_feedback_active_write() FROM PUBLIC;
CREATE TRIGGER feedback_active_write BEFORE INSERT ON cj_feedback_action FOR EACH ROW EXECUTE FUNCTION cj_feedback_active_write();
