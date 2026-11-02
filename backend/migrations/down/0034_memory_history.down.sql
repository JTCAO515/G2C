-- local runtime only: never erase history/cleanup fences to make a rollback pass.
DO $history_down$
BEGIN
 IF EXISTS(SELECT 1 FROM cj_memory_history_fence)
  OR EXISTS(SELECT 1 FROM cj_memory_history_consent)
  OR EXISTS(SELECT 1 FROM cj_memory_history_action)
  OR EXISTS(SELECT 1 FROM cj_memory_history_job)
  OR EXISTS(SELECT 1 FROM cj_memory_history_cursor) THEN
  RAISE EXCEPTION 'history state retained; down refused';
 END IF;
END $history_down$;
DROP POLICY cj_m3_history_cleanup_lock ON cj_memory_scope;
REVOKE UPDATE(scope) ON cj_memory_scope FROM cj_local_cleanup;
DROP TABLE cj_memory_history_cursor,cj_memory_history_job,cj_memory_history_action,
 cj_memory_history_consent,cj_memory_history_fence;
