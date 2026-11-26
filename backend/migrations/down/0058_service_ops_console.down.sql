-- local runtime only: refuse to drop retained staff audit or a cleared-note marker.
LOCK TABLE cj_service_request,cj_service_request_staff_audit IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_service_request_staff_audit)
 OR EXISTS(SELECT 1 FROM cj_service_request WHERE note_cleared_at IS NOT NULL) THEN
  RAISE EXCEPTION 'service_ops_console down refused: retained audit or cleared note';
 END IF;
END $$;
DROP TABLE cj_service_request_staff_audit;
DROP FUNCTION cj_service_request_staff_audit_append_only();
DROP TRIGGER service_request_note_clear_only ON cj_service_request;
DROP FUNCTION cj_service_request_note_clear_only();
DROP POLICY service_ops_read ON cj_service_request_history;
REVOKE SELECT ON cj_service_request_history FROM cj_ops_console;
DROP POLICY service_ops_clear_note ON cj_service_request;
DROP POLICY service_ops_read ON cj_service_request;
REVOKE SELECT,UPDATE(details,original_input,note_cleared_at) ON cj_service_request FROM cj_ops_console;
DROP POLICY service_ops_lock ON cj_service_request_scope;
DROP POLICY service_ops_read ON cj_service_request_scope;
REVOKE SELECT,UPDATE(scope_digest) ON cj_service_request_scope FROM cj_ops_console;
ALTER TABLE cj_service_request DROP COLUMN note_cleared_at;
REVOKE USAGE ON SCHEMA public FROM cj_ops_console;
DROP ROLE cj_ops_console;
