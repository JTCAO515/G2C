-- local runtime only: original job/content/accounting evidence cannot be discarded.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_run_background_job) THEN
  RAISE EXCEPTION 'original background job evidence retained';
 END IF;
END $$;
DROP TABLE cj_run_background_job;
DROP FUNCTION cj_background_original();
