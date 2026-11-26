-- local runtime only: refuse to drop retained service requests, history or view audit.
-- Scope fence rows hold no user data; the account-level cj_account_fence (0035) stays and the
-- restrictive account_retired policies recreated by re-applying 0056 keep retired owners out.
LOCK TABLE cj_service_request_scope,cj_service_request,cj_service_request_history,cj_service_request_view IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_service_request) OR EXISTS(SELECT 1 FROM cj_service_request_history)
 OR EXISTS(SELECT 1 FROM cj_service_request_view) THEN
  RAISE EXCEPTION 'service_request down refused: retained private data';
 END IF;
END $$;
DROP TABLE cj_service_request_view;
DROP TABLE cj_service_request_history;
DROP TABLE cj_service_request;
DROP TABLE cj_service_request_scope;
DROP FUNCTION cj_service_request_reject_truncate();
DROP FUNCTION cj_service_request_history_append_only();
DROP FUNCTION cj_service_request_active_write();
DROP FUNCTION cj_service_request_retire_once();
