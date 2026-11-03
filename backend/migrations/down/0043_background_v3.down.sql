-- local runtime only: new decision provenance cannot be discarded by downgrade.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_run_background_job WHERE protocol='RUN-BACKGROUND@3') THEN
  RAISE EXCEPTION 'original BG3 decision evidence retained';
 END IF;
END $$;
DROP TRIGGER background_header_immutable ON cj_run_background_job;
DROP FUNCTION cj_background_header_immutable();
DROP POLICY background_protocol ON cj_run_background_job;
ALTER TABLE cj_run_background_job DROP CONSTRAINT cj_background_decision_header,
 DROP COLUMN decision_source_sha256,DROP COLUMN protocol;
