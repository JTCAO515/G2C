-- local runtime only: retain irreversible fences and original feedback evidence.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_feedback_scope) OR EXISTS(SELECT 1 FROM cj_feedback_action)
 OR EXISTS(SELECT 1 FROM cj_run_event WHERE diagnostic_at IS NOT NULL) THEN
  RAISE EXCEPTION 'feedback_lifecycle down refused: retained private data or fence';
 END IF;
END $$;
DROP TRIGGER feedback_active_write ON cj_feedback_action;
DROP FUNCTION cj_feedback_active_write();
REVOKE SELECT,INSERT ON cj_feedback_action FROM cj_m1_runtime;
DROP POLICY feedback_runtime ON cj_feedback_action;
DROP TABLE cj_feedback_scope;
DROP FUNCTION cj_feedback_retire_once();
ALTER TABLE cj_run_event DROP COLUMN diagnostic_at;
