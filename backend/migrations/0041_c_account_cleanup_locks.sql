-- local runtime only: C #27 canonical scope locks for physical owner erasure.
-- Existing cleanup role only; no runtime privilege, new role or content store.
-- Scope-only UPDATE grants row locking; frozen-plan WITH CHECK forbids rename.
DO $c_account_cleanup_lock$
DECLARE
 scope_table text;
 allowed_targets text;
 lock_guard text;
BEGIN
 FOREACH scope_table IN ARRAY ARRAY['cj_memory_scope','cj_trip_scope'] LOOP
  allowed_targets := CASE WHEN scope_table='cj_memory_scope'
   THEN $$ARRAY['business/memory-management-actions','business/memory-authoritative']$$
   ELSE $$ARRAY['business/trip-authoritative']$$ END;
  lock_guard := format($condition$
   scope=nullif(current_setting('cj.cleanup_scope',true),'')
   AND current_setting('cj.cleanup_purpose',true)='account'
   AND EXISTS(
    SELECT 1 FROM cj_cleanup_operation o JOIN cj_cleanup_step s
      ON (s.subject_digest,s.operation_id)=(o.subject_digest,o.operation_id)
    WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
     AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'')
     AND o.purpose='account' AND NOT o.blocked AND o.plan_bytes IS NOT NULL
     AND s.target=ANY(%s) AND s.state='in_progress'
     AND s.request_bytes IS NOT NULL AND s.request_digest=encode(sha256(s.request_bytes),'hex')
     AND convert_from(o.plan_bytes,'UTF8')::jsonb->s.target->>'domain_scope'=scope)
   $condition$,allowed_targets);
  EXECUTE format('CREATE POLICY cj_m3_c_account_cleanup_lock ON %I FOR UPDATE TO cj_local_cleanup USING (%s) WITH CHECK (%s)',
                 scope_table,lock_guard,lock_guard);
 END LOOP;
END $c_account_cleanup_lock$;
GRANT UPDATE(scope) ON cj_trip_scope TO cj_local_cleanup;

-- Cover all runtime bootstrap callers, including old local cohosts. A volatile
-- invoker trigger obtains a shared transaction fence before insertion and reads
-- current retirement after acquisition. Cleanup takes the matching exclusive
-- fence, so an invisible first INSERT cannot commit after confirmed erasure.
CREATE FUNCTION cj_c_scope_bootstrap_fence() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER AS $$
BEGIN
 IF current_user='cj_m1_runtime' THEN
  IF NOT pg_catalog.pg_try_advisory_xact_lock_shared(pg_catalog.hashtextextended(
       'cj-c-account-scope:'||TG_TABLE_NAME||':'||NEW.scope,0)) THEN
   RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='C scope cleanup in progress';
  END IF;
  IF public.cj_account_scope_current(NEW.scope) IS DISTINCT FROM TRUE THEN
   RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='C account scope retired';
  END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_c_scope_bootstrap_fence() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cj_c_scope_bootstrap_fence() TO cj_m1_runtime;
CREATE TRIGGER cj_c_scope_bootstrap_fence BEFORE INSERT ON cj_memory_scope
 FOR EACH ROW EXECUTE FUNCTION cj_c_scope_bootstrap_fence();
CREATE TRIGGER cj_c_scope_bootstrap_fence BEFORE INSERT ON cj_trip_scope
 FOR EACH ROW EXECUTE FUNCTION cj_c_scope_bootstrap_fence();
