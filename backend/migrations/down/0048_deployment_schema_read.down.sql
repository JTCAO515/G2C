-- local runtime only: activated deployments cannot discard instance identity.
-- Revoke-only rollback does not erase inherited device/deletion evidence;
-- their original migration guards keep ownership of those down refusals.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_local_run_protection) THEN
  RAISE EXCEPTION 'activated deployment prevents schema-read rollback';
 END IF;
END $$;
DROP TABLE cj.deployment_identity;
REVOKE SELECT ON cj.schema_migrations FROM cj_m1_runtime;
REVOKE USAGE ON SCHEMA cj FROM cj_m1_runtime;
