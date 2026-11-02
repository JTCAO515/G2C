-- local runtime only: refuse downgrade while either C canonical scope remains.
DO $c_account_cleanup_down$
BEGIN
 IF EXISTS(SELECT 1 FROM cj_memory_scope) OR EXISTS(SELECT 1 FROM cj_trip_scope) THEN
  RAISE EXCEPTION 'C account cleanup locks still protect retained user data';
 END IF;
END $c_account_cleanup_down$;
DROP TRIGGER cj_c_scope_bootstrap_fence ON cj_memory_scope;
DROP TRIGGER cj_c_scope_bootstrap_fence ON cj_trip_scope;
DROP FUNCTION cj_c_scope_bootstrap_fence();
DROP POLICY cj_m3_c_account_cleanup_lock ON cj_memory_scope;
DROP POLICY cj_m3_c_account_cleanup_lock ON cj_trip_scope;
REVOKE UPDATE(scope) ON cj_trip_scope FROM cj_local_cleanup;
