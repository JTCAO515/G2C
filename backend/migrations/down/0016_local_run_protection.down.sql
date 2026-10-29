LOCK TABLE cj_local_run_protection,cj_local_run_requirement IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_local_run_protection) OR EXISTS(SELECT 1 FROM cj_local_run_requirement) THEN
  RAISE EXCEPTION 'local protection records exist; downgrade refused';
 END IF;
END $$;
DROP TABLE cj_local_run_requirement;
DROP TABLE cj_local_run_protection;
