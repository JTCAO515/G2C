-- local runtime only: minimal operations console role and append-only staff audit (#1771).
-- Decision: 统筹 2026-11-26 按 JT 预授权决定，超出 ADR-0007 第 2 条的单独批准.
--
-- Login identity: the LOGIN role cj_ops_console is used only by the operations API path
-- (cj_service_request.ops.OpsConsole.ops_connect, routes /v1/internal/ops/*, gated by
-- CJ_OPS_CONSOLE_ENABLED default off). No other composition, worker or CLI connects as it.
-- It is NOBYPASSRLS/NOINHERIT, holds no DELETE/TRUNCATE, and no SECURITY DEFINER is used.
--
-- What it may do:
--  * SELECT the service request tables only (scope fence, request, history); nothing in
--    message/conversation, memory, trip, needs, usage or cleanup tables.
--  * Clear a misreceived note (PIPIA 7): column UPDATE(details,original_input,note_cleared_at)
--    on cj_service_request; a trigger permits exactly details.note -> null (same in the
--    stored original bytes) once, every other field and key unchanged.
--  * INSERT into the append-only staff audit (view, note clearing, each staff transition).
-- State changes are NOT made by this role: they run as cj_m1_runtime under the target
-- owner's scope through Repository.transition -> check_transition.
--
-- Staff audit retention (统筹 2026-11-26): erasure clears request id and owner scope (the
-- only user-linkable values), keeping staff ref, time and action; otherwise it follows the
-- service request (ON DELETE CASCADE at the 12-month deletion); de-linked rows end after 12 months.
CREATE ROLE cj_ops_console LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO cj_ops_console;

ALTER TABLE cj_service_request ADD COLUMN note_cleared_at timestamptz;

CREATE TABLE cj_service_request_staff_audit (
 audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 staff_ref text NOT NULL CHECK(length(staff_ref) BETWEEN 1 AND 128),
 at timestamptz NOT NULL DEFAULT clock_timestamp(),
 action text NOT NULL CHECK(action IN ('list','view','clear_note','accepted','quoted','arranged','in_progress',
  'completed','unavailable','outcome_unknown','user_cancelled')),
 scope text,
 request_id text,
 CHECK((scope IS NULL) = (request_id IS NULL)),
 FOREIGN KEY(scope,request_id) REFERENCES cj_service_request(scope,request_id) ON DELETE CASCADE
);
CREATE INDEX cj_service_request_staff_audit_request ON cj_service_request_staff_audit(scope,request_id);
ALTER TABLE cj_service_request_staff_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_service_request_staff_audit FORCE ROW LEVEL SECURITY;
REVOKE ALL ON cj_service_request_staff_audit FROM PUBLIC;

-- Ops reads: every live (never retired) owner; retired owners are invisible.
CREATE POLICY service_ops_read ON cj_service_request_scope FOR SELECT TO cj_ops_console USING(true);
-- Row lock only (the active-write trigger locks the live fence row); never an actual update.
CREATE POLICY service_ops_lock ON cj_service_request_scope FOR UPDATE TO cj_ops_console
 USING(NOT retired) WITH CHECK(false);
GRANT SELECT,UPDATE(scope_digest) ON cj_service_request_scope TO cj_ops_console;
CREATE POLICY service_ops_read ON cj_service_request FOR SELECT TO cj_ops_console
 USING(EXISTS(SELECT 1 FROM cj_service_request_scope s
  WHERE s.scope_digest=encode(sha256(convert_to(scope,'UTF8')),'hex') AND NOT s.retired));
CREATE POLICY service_ops_clear_note ON cj_service_request FOR UPDATE TO cj_ops_console
 USING(note_cleared_at IS NULL AND EXISTS(SELECT 1 FROM cj_service_request_scope s
  WHERE s.scope_digest=encode(sha256(convert_to(scope,'UTF8')),'hex') AND NOT s.retired))
 WITH CHECK(note_cleared_at IS NOT NULL);
GRANT SELECT,UPDATE(details,original_input,note_cleared_at) ON cj_service_request TO cj_ops_console;
CREATE POLICY service_ops_read ON cj_service_request_history FOR SELECT TO cj_ops_console
 USING(EXISTS(SELECT 1 FROM cj_service_request r WHERE r.scope=cj_service_request_history.scope
  AND r.request_id=cj_service_request_history.request_id));
GRANT SELECT ON cj_service_request_history TO cj_ops_console;
CREATE POLICY service_ops_append ON cj_service_request_staff_audit FOR INSERT TO cj_ops_console WITH CHECK(true);
GRANT INSERT(staff_ref,action,scope,request_id) ON cj_service_request_staff_audit TO cj_ops_console;

-- Cleanup: account erasure de-links the audit rows of the erased owner (then deletes the
-- requests); retention deletes de-linked rows older than 12 months. Nothing else.
-- The de-linked row (scope null) must stay visible to the same statement (UPDATE new-row rule).
CREATE POLICY service_audit_cleanup_read ON cj_service_request_staff_audit FOR SELECT TO cj_local_cleanup
 USING((scope=nullif(current_setting('cj.cleanup_scope',true),'') OR scope IS NULL) AND current_setting('cj.cleanup_purpose',true)='account'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='account' AND NOT o.blocked));
CREATE POLICY service_audit_cleanup ON cj_service_request_staff_audit FOR UPDATE TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='account'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='account' AND NOT o.blocked))
 WITH CHECK(scope IS NULL AND request_id IS NULL);
CREATE POLICY service_audit_retention ON cj_service_request_staff_audit FOR DELETE TO cj_local_cleanup
 USING(current_setting('cj.cleanup_purpose',true)='service_staff_audit_retention'
  AND request_id IS NULL AND at < clock_timestamp() - interval '12 months');
CREATE POLICY service_audit_retention_read ON cj_service_request_staff_audit FOR SELECT TO cj_local_cleanup
 USING(current_setting('cj.cleanup_purpose',true)='service_staff_audit_retention' AND request_id IS NULL);
GRANT SELECT,DELETE,UPDATE(scope,request_id) ON cj_service_request_staff_audit TO cj_local_cleanup;

-- Note clearing: exactly details.note -> null (and the same key in the original bytes), once.
CREATE FUNCTION cj_service_request_note_clear_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.details IS NOT DISTINCT FROM OLD.details AND NEW.original_input IS NOT DISTINCT FROM OLD.original_input
    AND NEW.note_cleared_at IS NOT DISTINCT FROM OLD.note_cleared_at THEN
  RETURN NEW;
 END IF;
 IF OLD.note_cleared_at IS NOT NULL OR NEW.note_cleared_at IS NULL
  OR jsonb_typeof(OLD.details->'note') IS DISTINCT FROM 'string'
  OR NEW.details IS DISTINCT FROM OLD.details || '{"note":null}'::jsonb
  OR convert_from(NEW.original_input,'UTF8')::jsonb
     IS DISTINCT FROM convert_from(OLD.original_input,'UTF8')::jsonb || '{"note":null}'::jsonb
  OR (NEW.scope,NEW.request_id,NEW.client_request_id,NEW.input_sha256,NEW.state,NEW.human_service,NEW.quote,
      NEW.submitted_at,NEW.arranged_at,NEW.first_terminal_at)
     IS DISTINCT FROM (OLD.scope,OLD.request_id,OLD.client_request_id,OLD.input_sha256,OLD.state,OLD.human_service,
      OLD.quote,OLD.submitted_at,OLD.arranged_at,OLD.first_terminal_at)
 THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='service request note may only be cleared';
 END IF;
 NEW.note_cleared_at := clock_timestamp();
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_service_request_note_clear_only() FROM PUBLIC;
CREATE TRIGGER service_request_note_clear_only BEFORE UPDATE ON cj_service_request
 FOR EACH ROW EXECUTE FUNCTION cj_service_request_note_clear_only();

-- Staff audit is append-only; the sole update is de-linking (scope, request id -> null).
CREATE FUNCTION cj_service_request_staff_audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.audit_id,NEW.staff_ref,NEW.at,NEW.action) IS DISTINCT FROM (OLD.audit_id,OLD.staff_ref,OLD.at,OLD.action)
  OR NEW.scope IS NOT NULL OR NEW.request_id IS NOT NULL
 THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='staff audit is append-only'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_service_request_staff_audit_append_only() FROM PUBLIC;
CREATE TRIGGER service_request_staff_audit_append_only BEFORE UPDATE ON cj_service_request_staff_audit
 FOR EACH ROW EXECUTE FUNCTION cj_service_request_staff_audit_append_only();
CREATE TRIGGER service_request_no_truncate BEFORE TRUNCATE ON cj_service_request_staff_audit
 FOR EACH STATEMENT EXECUTE FUNCTION cj_service_request_reject_truncate();
