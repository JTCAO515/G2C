-- local runtime only: #27 HTTP original-operation metadata and irreversible fences.
-- This candidate is appended to the next free migration only after C's locked queue slice.
CREATE TABLE cj_cleanup_request (
 subject_digest text NOT NULL CHECK(subject_digest ~ '^[0-9a-f]{64}$'),
 operation_id text PRIMARY KEY, action_id text NOT NULL, input_digest text NOT NULL,
 registry_bytes bytea NOT NULL, inventory jsonb NOT NULL, plan_bytes bytea,
 plan_digest text NOT NULL, binding_id text NOT NULL,
 phase text NOT NULL CHECK(phase IN ('prepared','confirmed','blocked')),
 confirmation_digest text, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0),
 UNIQUE(subject_digest,action_id),UNIQUE(subject_digest,operation_id)
);
CREATE TABLE cj_account_fence (
 subject_digest text PRIMARY KEY, owner_digest text NOT NULL UNIQUE,
 operation_id text NOT NULL REFERENCES cj_cleanup_request(operation_id),
 namespace_digests jsonb NOT NULL CHECK(jsonb_typeof(namespace_digests)='array'),
 retired_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE cj_cleanup_device_binding (
 subject_digest text NOT NULL, binding_id text PRIMARY KEY,
 action_id text NOT NULL,input_digest text NOT NULL,device_id text NOT NULL,
 state_ref text NOT NULL,scope_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(subject_digest,action_id),UNIQUE(subject_digest,device_id,state_ref)
);
CREATE TABLE cj_cleanup_device_call (
 subject_digest text NOT NULL,operation_id text NOT NULL,invocation_id text PRIMARY KEY,
 binding_id text NOT NULL REFERENCES cj_cleanup_device_binding(binding_id),
 reason text NOT NULL CHECK(reason IN ('account_cleanup','session_invalid','offline_expired')),
 request_digest text NOT NULL,request_bytes bytea NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','unknown','failed','confirmed')),
 receipt_action_id text,receipt_digest text,receipt_bytes bytea,
 received_at timestamptz,UNIQUE(operation_id,binding_id,reason)
);
ALTER TABLE cj_cleanup_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_cleanup_request FORCE ROW LEVEL SECURITY;
CREATE POLICY cleanup_subject ON cj_cleanup_request TO cj_local_cleanup USING(subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')) WITH CHECK(subject_digest=nullif(current_setting('cj.cleanup_subject',true),''));
GRANT SELECT,INSERT ON cj_cleanup_request TO cj_local_cleanup;
ALTER TABLE cj_account_fence ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_account_fence FORCE ROW LEVEL SECURITY;
CREATE POLICY cleanup_subject ON cj_account_fence TO cj_local_cleanup USING(subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')) WITH CHECK(subject_digest=nullif(current_setting('cj.cleanup_subject',true),''));
GRANT SELECT,INSERT ON cj_account_fence TO cj_local_cleanup;
ALTER TABLE cj_cleanup_device_binding ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_cleanup_device_binding FORCE ROW LEVEL SECURITY;
CREATE POLICY cleanup_subject ON cj_cleanup_device_binding TO cj_local_cleanup USING(subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')) WITH CHECK(subject_digest=nullif(current_setting('cj.cleanup_subject',true),''));
GRANT SELECT,INSERT ON cj_cleanup_device_binding TO cj_local_cleanup;
ALTER TABLE cj_cleanup_device_call ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_cleanup_device_call FORCE ROW LEVEL SECURITY;
CREATE POLICY cleanup_subject ON cj_cleanup_device_call TO cj_local_cleanup USING(subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')) WITH CHECK(subject_digest=nullif(current_setting('cj.cleanup_subject',true),''));
GRANT SELECT,INSERT ON cj_cleanup_device_call TO cj_local_cleanup;
GRANT UPDATE(phase,confirmation_digest,plan_bytes,revision) ON cj_cleanup_request TO cj_local_cleanup;
GRANT UPDATE(state,receipt_action_id,receipt_digest,receipt_bytes,received_at) ON cj_cleanup_device_call TO cj_local_cleanup;
CREATE POLICY account_fence_runtime ON cj_account_fence FOR SELECT TO cj_m1_runtime USING(
 owner_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex')
 OR namespace_digests ? encode(sha256(convert_to(nullif(current_setting('cj.trip_scope',true),''),'UTF8')),'hex')
 OR namespace_digests ? encode(sha256(convert_to(nullif(current_setting('cj.needs_scope',true),''),'UTF8')),'hex')
 OR namespace_digests ? encode(sha256(convert_to(nullif(current_setting('cj.usage_scope',true),''),'UTF8')),'hex'));
GRANT SELECT ON cj_account_fence TO cj_m1_runtime;
CREATE FUNCTION cj_account_scope_current(p_scope text) RETURNS boolean LANGUAGE sql STABLE STRICT SECURITY INVOKER AS $$
 SELECT NOT EXISTS(SELECT 1 FROM public.cj_account_fence
 WHERE owner_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex')
 OR namespace_digests ? encode(sha256(convert_to(p_scope,'UTF8')),'hex'))
$$;
REVOKE ALL ON FUNCTION cj_account_scope_current(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cj_account_scope_current(text) TO cj_m1_runtime;
CREATE POLICY account_retired ON cj_message_scope AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_chat AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_receipt AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_delivery AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_draft AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_travel_context AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_travel_context_action AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_context_profile AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_travel_reference AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_needs_selection AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(message_scope)) WITH CHECK(public.cj_account_scope_current(message_scope));
CREATE POLICY account_retired ON cj_message_needs_binding AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(message_scope)) WITH CHECK(public.cj_account_scope_current(message_scope));
CREATE POLICY account_retired ON cj_local_run_requirement AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_local_run_protection AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_local_metered_profile AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_metered_requirement AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_trip_profile AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_trip_reference AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_edit_profile AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_edit_reference AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_message_edit_result_profile AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_usage_ledger_candidate AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope_id)) WITH CHECK(public.cj_account_scope_current(scope_id));
CREATE POLICY account_retired ON cj_memory_scope AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_memory_source AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_memory_item AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_memory_operation AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_scope AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_proposal AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_record AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_receipt AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_manual_basis AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_manual_intent AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_needs_basis AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_needs_action AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_needs_current AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_needs_edit AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_needs_plan_context AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_scoped_basis AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_scoped_action AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_trip_scoped_result AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_needs_scope AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_needs_record AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_needs_revision AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_feedback_action AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_memory_management_action AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_run_scope AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_run_record AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_run_event AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_run_step_usage AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_run_metered_binding AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_run_metered_operation AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_memory_history_consent AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_memory_history_action AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_memory_history_job AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
CREATE POLICY account_retired ON cj_memory_history_cursor AS RESTRICTIVE TO cj_m1_runtime USING(public.cj_account_scope_current(scope)) WITH CHECK(public.cj_account_scope_current(scope));
GRANT UPDATE(active,epoch) ON cj_run_scope TO cj_local_cleanup;
CREATE POLICY cleanup_stop ON cj_run_scope FOR UPDATE TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'')) WITH CHECK(scope=nullif(current_setting('cj.cleanup_scope',true),''));
GRANT UPDATE(diagnostic_at) ON cj_run_event TO cj_local_cleanup;
CREATE POLICY cleanup_diagnostic_select ON cj_run_event FOR SELECT TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='diagnostics' AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='diagnostics' AND NOT o.blocked));
CREATE POLICY cleanup_diagnostic_update ON cj_run_event FOR UPDATE TO cj_local_cleanup USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='diagnostics' AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='diagnostics' AND NOT o.blocked)) WITH CHECK(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND current_setting('cj.cleanup_purpose',true)='diagnostics' AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='diagnostics' AND NOT o.blocked));
-- Existing chat-delete trigger advances the retained list epoch before scope erase.
GRANT UPDATE(history_epoch) ON cj_message_scope TO cj_local_cleanup;
CREATE POLICY cleanup_list_epoch ON cj_message_scope FOR UPDATE TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_account_fence f WHERE f.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
  AND f.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND f.owner_digest=encode(sha256(convert_to(scope,'UTF8')),'hex')))
 WITH CHECK(scope=nullif(current_setting('cj.cleanup_scope',true),''));
CREATE FUNCTION cj_cleanup_progress_revision() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 UPDATE public.cj_cleanup_request SET revision=revision+1
 WHERE subject_digest=NEW.subject_digest AND operation_id=NEW.operation_id;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_cleanup_progress_revision() FROM PUBLIC;
CREATE TRIGGER cleanup_step_progress AFTER INSERT OR UPDATE ON cj_cleanup_step
 FOR EACH ROW EXECUTE FUNCTION cj_cleanup_progress_revision();
CREATE TRIGGER cleanup_device_progress AFTER INSERT OR UPDATE ON cj_cleanup_device_call
 FOR EACH ROW EXECUTE FUNCTION cj_cleanup_progress_revision();
CREATE TRIGGER cleanup_operation_progress AFTER UPDATE ON cj_cleanup_operation
 FOR EACH ROW WHEN (OLD.blocked IS DISTINCT FROM NEW.blocked OR OLD.plan_bytes IS DISTINCT FROM NEW.plan_bytes)
 EXECUTE FUNCTION cj_cleanup_progress_revision();
-- Account-wide USAGE discovery: owner is recomputed with the existing M16/M17
-- compact UTF8 ledger_scope_for algorithm, not inferred from client IDs.
CREATE FUNCTION cj_cleanup_usage_owner(scope_id text,ledger jsonb) RETURNS boolean
LANGUAGE sql STABLE STRICT SECURITY INVOKER AS $$
 SELECT current_setting('cj.cleanup_purpose',true)='account'
 AND scope_id='u'||encode(sha256(convert_to(
  '['||to_json(nullif(current_setting('cj.cleanup_owner_scope',true),''))::text||','
  ||to_json(ledger->'config'->>'unit')::text||','
  ||(ledger->'config'->>'period_start')::bigint::text||','
  ||(ledger->'config'->>'period_end')::bigint::text||']','UTF8')),'hex')
 AND EXISTS(SELECT 1 FROM public.cj_cleanup_operation o
  WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND o.purpose='account' AND NOT o.blocked
   AND o.plan_bytes IS NOT NULL
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'business/usage'->>'domain_scope'=current_setting('cj.cleanup_owner_scope',true))
$$;
REVOKE ALL ON FUNCTION cj_cleanup_usage_owner(text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cj_cleanup_usage_owner(text,jsonb) TO cj_local_cleanup;
CREATE POLICY cleanup_usage_owner_read ON cj_usage_ledger_candidate FOR SELECT TO cj_local_cleanup
 USING(public.cj_cleanup_usage_owner(scope_id,ledger));
CREATE POLICY cleanup_usage_owner_delete ON cj_usage_ledger_candidate FOR DELETE TO cj_local_cleanup
 USING(public.cj_cleanup_usage_owner(scope_id,ledger));
