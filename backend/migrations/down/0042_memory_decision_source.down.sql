-- local runtime only: never discard a retained accepted-decision association.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_memory_history_origin WHERE decision_source_sha256 IS NOT NULL) THEN
  RAISE EXCEPTION 'accepted decision source evidence retained';
 END IF;
END $$;
DROP TRIGGER cj_memory_decision_origin_append ON cj_memory_history_origin;
DROP FUNCTION cj_memory_decision_origin_append();
REVOKE UPDATE(origin_refs) ON cj_memory_history_origin FROM cj_m1_runtime;
DROP INDEX cj_memory_history_origin_decision;
ALTER TABLE cj_memory_history_origin DROP COLUMN decision_source_sha256;
