-- local runtime only: retained output/decision/origin state cannot be discarded.
DO $publication_down$
BEGIN
 IF EXISTS(SELECT 1 FROM cj_memory_history_job WHERE result_bytes IS NOT NULL)
  OR EXISTS(SELECT 1 FROM cj_memory_history_candidate_action)
  OR EXISTS(SELECT 1 FROM cj_memory_history_origin) THEN
  RAISE EXCEPTION 'history publication retained; down refused';
 END IF;
END $publication_down$;
DROP TABLE cj_memory_history_origin,cj_memory_history_candidate_action;
ALTER TABLE cj_memory_history_job DROP COLUMN result_bytes;
