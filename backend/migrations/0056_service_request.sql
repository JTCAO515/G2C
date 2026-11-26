-- local runtime only: SERVICE-REQUEST@1 store, append-only history, escort view audit (#1769).
-- Owner scope is server-resolved (cj.message_scope); callers never supply owner/state/quote/staff.
-- Retention (PIPIA 9): 12 months after first terminal state; completion_summary body 90 days.
-- Account erasure: irreversible scope fence, then physical delete by cj_local_cleanup only.
CREATE TABLE cj_service_request_scope (
 scope_digest text PRIMARY KEY CHECK(scope_digest ~ '^[0-9a-f]{64}$'),
 retired boolean NOT NULL DEFAULT false
);
CREATE TABLE cj_service_request (
 scope text NOT NULL,
 request_id text NOT NULL CHECK(request_id ~ '^sr_[0-9a-f]{32}$'),
 client_request_id text NOT NULL CHECK(client_request_id ~ '^[A-Za-z0-9_-]{1,128}$'),
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 8192),
 input_sha256 text NOT NULL CHECK(input_sha256 ~ '^[0-9a-f]{64}$'),
 state text NOT NULL CHECK(state IN ('submitted','accepted','quoted','arranged','in_progress',
  'completed','user_cancelled','unavailable','outcome_unknown')),
 details jsonb NOT NULL CHECK(jsonb_typeof(details)='object'),
 human_service jsonb NOT NULL CHECK(jsonb_typeof(human_service)='object'),
 quote jsonb CHECK(quote IS NULL OR jsonb_typeof(quote)='object'),
 submitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 arranged_at timestamptz,
 first_terminal_at timestamptz,
 CHECK((state IN ('completed','user_cancelled','unavailable','outcome_unknown')) = (first_terminal_at IS NOT NULL)),
 PRIMARY KEY(scope,request_id),
 UNIQUE(scope,client_request_id)
);
CREATE TABLE cj_service_request_history (
 scope text NOT NULL,
 request_id text NOT NULL,
 seq integer NOT NULL CHECK(seq>=1),
 from_state text,
 to_state text NOT NULL,
 at timestamptz NOT NULL DEFAULT clock_timestamp(),
 actor_kind text NOT NULL CHECK(actor_kind IN ('user','staff','system')),
 staff_ref text CHECK(staff_ref IS NULL OR (actor_kind='staff' AND length(staff_ref) BETWEEN 1 AND 128)),
 evidence_kind text NOT NULL,
 evidence_body text,
 PRIMARY KEY(scope,request_id,seq),
 FOREIGN KEY(scope,request_id) REFERENCES cj_service_request(scope,request_id) ON DELETE CASCADE
);
CREATE TABLE cj_service_request_view (
 scope text NOT NULL,
 request_id text NOT NULL,
 view_id bigint GENERATED ALWAYS AS IDENTITY,
 viewer_ref text NOT NULL CHECK(length(viewer_ref) BETWEEN 1 AND 128),
 fields jsonb NOT NULL CHECK(jsonb_typeof(fields)='array'),
 viewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,request_id,view_id),
 FOREIGN KEY(scope,request_id) REFERENCES cj_service_request(scope,request_id) ON DELETE CASCADE
);
ALTER TABLE cj_service_request_scope ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_service_request_scope FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_service_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_service_request FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_service_request_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_service_request_history FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_service_request_view ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_service_request_view FORCE ROW LEVEL SECURITY;
REVOKE ALL ON cj_service_request_scope,cj_service_request,cj_service_request_history,cj_service_request_view FROM PUBLIC;

-- Runtime: own scope only; the fence row is lock-only and retired is never runtime-writable.
CREATE POLICY service_request_runtime ON cj_service_request_scope TO cj_m1_runtime
 USING(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex'))
 WITH CHECK(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex') AND NOT retired);
GRANT SELECT,INSERT(scope_digest),UPDATE(scope_digest) ON cj_service_request_scope TO cj_m1_runtime;
CREATE POLICY service_request_runtime ON cj_service_request TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
-- Retention erasure only: the database clock, never a caller cutoff, gates runtime DELETE.
CREATE POLICY service_request_retention ON cj_service_request AS RESTRICTIVE FOR DELETE TO cj_m1_runtime
 USING(first_terminal_at IS NOT NULL AND first_terminal_at < clock_timestamp() - interval '12 months');
GRANT SELECT,INSERT,DELETE ON cj_service_request TO cj_m1_runtime;
GRANT UPDATE(state,quote,human_service,arranged_at,first_terminal_at) ON cj_service_request TO cj_m1_runtime;
CREATE POLICY service_request_runtime ON cj_service_request_history TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
GRANT SELECT,INSERT,UPDATE(evidence_body) ON cj_service_request_history TO cj_m1_runtime;
CREATE POLICY service_request_runtime ON cj_service_request_view TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),''));
GRANT SELECT,INSERT ON cj_service_request_view TO cj_m1_runtime;
CREATE POLICY account_retired ON cj_service_request AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_service_request_history AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_service_request_view AS RESTRICTIVE TO cj_m1_runtime
 USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));

-- Cleanup: the original approved account operation only (same shape as FEEDBACK@1.0).
CREATE POLICY service_request_cleanup ON cj_service_request_scope TO cj_local_cleanup
 USING(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.cleanup_scope',true),''),'UTF8')),'hex'))
 WITH CHECK(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.cleanup_scope',true),''),'UTF8')),'hex')
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation WHERE subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND purpose='account' AND NOT blocked));
GRANT SELECT,INSERT,UPDATE(retired) ON cj_service_request_scope TO cj_local_cleanup;
CREATE POLICY service_request_cleanup ON cj_service_request TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='account'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='account' AND NOT o.blocked));
GRANT SELECT,DELETE ON cj_service_request TO cj_local_cleanup;
CREATE POLICY service_request_cleanup ON cj_service_request_history TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='account'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='account' AND NOT o.blocked));
GRANT SELECT,DELETE ON cj_service_request_history TO cj_local_cleanup;
CREATE POLICY service_request_cleanup ON cj_service_request_view TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='account'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='account' AND NOT o.blocked));
GRANT SELECT,DELETE ON cj_service_request_view TO cj_local_cleanup;

CREATE FUNCTION cj_service_request_retire_once() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.retired AND NOT NEW.retired THEN RAISE EXCEPTION 'service request scope retired'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_service_request_retire_once() FROM PUBLIC;
CREATE TRIGGER service_request_retire_once BEFORE UPDATE ON cj_service_request_scope
 FOR EACH ROW EXECUTE FUNCTION cj_service_request_retire_once();

-- Every write locks the live fence row, so a writer and the account hook serialize.
CREATE FUNCTION cj_service_request_active_write() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM cj_service_request_scope
  WHERE scope_digest=encode(sha256(convert_to(NEW.scope,'UTF8')),'hex') AND NOT retired FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='service request scope unavailable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_service_request_active_write() FROM PUBLIC;
CREATE TRIGGER service_request_active_write BEFORE INSERT OR UPDATE ON cj_service_request
 FOR EACH ROW EXECUTE FUNCTION cj_service_request_active_write();
CREATE TRIGGER service_request_active_write BEFORE INSERT OR UPDATE ON cj_service_request_history
 FOR EACH ROW EXECUTE FUNCTION cj_service_request_active_write();
CREATE TRIGGER service_request_active_write BEFORE INSERT ON cj_service_request_view
 FOR EACH ROW EXECUTE FUNCTION cj_service_request_active_write();

-- History is append-only; the sole update is erasing a completion_summary body after 90 days.
CREATE FUNCTION cj_service_request_history_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.scope,NEW.request_id,NEW.seq,NEW.from_state,NEW.to_state,NEW.at,NEW.actor_kind,NEW.staff_ref,NEW.evidence_kind)
    IS DISTINCT FROM (OLD.scope,OLD.request_id,OLD.seq,OLD.from_state,OLD.to_state,OLD.at,OLD.actor_kind,OLD.staff_ref,OLD.evidence_kind)
  OR NEW.evidence_body IS NOT NULL OR OLD.evidence_kind<>'completion_summary'
  OR NOT EXISTS(SELECT 1 FROM cj_service_request r WHERE r.scope=OLD.scope AND r.request_id=OLD.request_id
   AND r.first_terminal_at < clock_timestamp() - interval '90 days')
 THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='service request history is append-only'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_service_request_history_append_only() FROM PUBLIC;
CREATE TRIGGER service_request_history_append_only BEFORE UPDATE ON cj_service_request_history
 FOR EACH ROW EXECUTE FUNCTION cj_service_request_history_append_only();
CREATE FUNCTION cj_service_request_reject_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'service request truncate refused'; END $$;
REVOKE ALL ON FUNCTION cj_service_request_reject_truncate() FROM PUBLIC;
CREATE TRIGGER service_request_no_truncate BEFORE TRUNCATE ON cj_service_request
 FOR EACH STATEMENT EXECUTE FUNCTION cj_service_request_reject_truncate();
CREATE TRIGGER service_request_no_truncate BEFORE TRUNCATE ON cj_service_request_history
 FOR EACH STATEMENT EXECUTE FUNCTION cj_service_request_reject_truncate();
CREATE TRIGGER service_request_no_truncate BEFORE TRUNCATE ON cj_service_request_view
 FOR EACH STATEMENT EXECUTE FUNCTION cj_service_request_reject_truncate();
