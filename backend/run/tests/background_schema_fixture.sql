-- TEST FIXTURE ONLY: fresh private PG prototype, not a registered migration or deployment.
CREATE TABLE cj_run_background_job (
 scope text NOT NULL,job_id text NOT NULL,attempt_id text NOT NULL,run_id text NOT NULL,
 ledger_scope text NOT NULL,prepared_input_sha256 text NOT NULL CHECK(prepared_input_sha256~'^[0-9a-f]{64}$'),
 config_bytes bytea NOT NULL,command_bytes bytea NOT NULL,input_bytes bytea,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','publishing','completed','budget_exhausted','cancelled','unknown')),
 output_sha256 text CHECK(output_sha256~'^[0-9a-f]{64}$'),receipt_sha256 text CHECK(receipt_sha256~'^[0-9a-f]{64}$'),
 PRIMARY KEY(scope,job_id,attempt_id),UNIQUE(scope,run_id),
 CHECK(state<>'completed' OR (output_sha256 IS NOT NULL AND receipt_sha256 IS NOT NULL))
);
ALTER TABLE cj_run_background_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_run_background_job FORCE ROW LEVEL SECURITY;
CREATE POLICY own_job ON cj_run_background_job TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),'') AND public.cj_account_scope_current(scope)
 AND EXISTS(SELECT 1 FROM cj_run_scope r WHERE r.scope=cj_run_background_job.scope AND r.active))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND public.cj_account_scope_current(scope)
 AND EXISTS(SELECT 1 FROM cj_run_scope r WHERE r.scope=cj_run_background_job.scope AND r.active));
GRANT SELECT ON cj_run_background_job TO cj_m1_runtime;
GRANT INSERT(scope,job_id,attempt_id,run_id,ledger_scope,prepared_input_sha256,config_bytes,command_bytes,input_bytes) ON cj_run_background_job TO cj_m1_runtime;
GRANT UPDATE(state,output_sha256,receipt_sha256) ON cj_run_background_job TO cj_m1_runtime;
CREATE FUNCTION cj_background_original() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.state<>'queued' OR NEW.input_bytes IS NULL OR NEW.output_sha256 IS NOT NULL OR NEW.receipt_sha256 IS NOT NULL THEN RAISE EXCEPTION 'new queued original job required'; END IF;
  RETURN NEW;
 END IF;
 IF (NEW.scope,NEW.job_id,NEW.attempt_id,NEW.run_id,NEW.ledger_scope,NEW.prepared_input_sha256,NEW.config_bytes,NEW.command_bytes)
  IS DISTINCT FROM (OLD.scope,OLD.job_id,OLD.attempt_id,OLD.run_id,OLD.ledger_scope,OLD.prepared_input_sha256,OLD.config_bytes,OLD.command_bytes) THEN
  RAISE EXCEPTION 'immutable background original';
 END IF;
 IF NEW.input_bytes IS DISTINCT FROM OLD.input_bytes AND (current_user<>'cj_local_cleanup' OR NEW.input_bytes IS NOT NULL) THEN RAISE EXCEPTION 'erased job input cannot be restored'; END IF;
 IF OLD.output_sha256 IS NOT NULL AND NEW.output_sha256 IS DISTINCT FROM OLD.output_sha256 THEN RAISE EXCEPTION 'immutable original output'; END IF;
 IF OLD.receipt_sha256 IS NOT NULL AND NEW.receipt_sha256 IS DISTINCT FROM OLD.receipt_sha256 THEN RAISE EXCEPTION 'immutable original receipt'; END IF;
 IF NEW.state<>OLD.state AND NOT (
  (OLD.state='queued' AND NEW.state IN ('running','cancelled','unknown','budget_exhausted')) OR
  (OLD.state='running' AND NEW.state IN ('publishing','cancelled','unknown','budget_exhausted')) OR
  (OLD.state='publishing' AND NEW.state IN ('completed','cancelled','unknown','budget_exhausted')) OR
  (OLD.state IN ('unknown','cancelled') AND NEW.state IN ('completed','cancelled'))
 ) THEN RAISE EXCEPTION 'original job cannot redispatch'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_background_original() FROM PUBLIC;
CREATE TRIGGER background_original BEFORE INSERT OR UPDATE ON cj_run_background_job FOR EACH ROW EXECUTE FUNCTION cj_background_original();
GRANT SELECT,DELETE ON cj_run_background_job TO cj_local_cleanup;
CREATE POLICY cleanup_job_read ON cj_run_background_job FOR SELECT TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_cleanup_operation o JOIN cj_account_fence f ON f.subject_digest=o.subject_digest AND f.operation_id=o.operation_id
  WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'')
   AND o.purpose='account' AND NOT o.blocked AND o.plan_bytes IS NOT NULL
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'checkpoints/run'->>'domain_scope'=cj_run_background_job.scope
   AND f.owner_digest=encode(sha256(convert_to(cj_run_background_job.scope,'UTF8')),'hex')));

CREATE POLICY cleanup_job_delete ON cj_run_background_job FOR DELETE TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_cleanup_operation o JOIN cj_account_fence f ON f.subject_digest=o.subject_digest AND f.operation_id=o.operation_id
  JOIN cj_cleanup_step s ON s.subject_digest=o.subject_digest AND s.operation_id=o.operation_id AND s.target='checkpoints/run' AND s.state='in_progress'
  WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'') AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'')
   AND o.purpose='account' AND NOT o.blocked AND o.plan_bytes IS NOT NULL
   AND convert_from(o.plan_bytes,'UTF8')::jsonb->'checkpoints/run'->>'domain_scope'=cj_run_background_job.scope
   AND f.owner_digest=encode(sha256(convert_to(cj_run_background_job.scope,'UTF8')),'hex')));
