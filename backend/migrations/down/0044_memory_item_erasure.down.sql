-- local runtime only: never discard private manifests or restoration barriers.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_memory_erasure_manifest) OR EXISTS(SELECT 1 FROM cj_memory_erasure_fence) THEN
  RAISE EXCEPTION 'memory item erasure evidence retained';
 END IF;
END $$;
DROP POLICY item_cleanup_lock ON cj_memory_scope;
DROP POLICY item_cleanup_lock ON cj_trip_scope;
DROP POLICY item_cleanup_read ON cj_memory_history_origin;
DROP POLICY item_cleanup_delete ON cj_memory_history_origin;
DROP POLICY item_cleanup_read ON cj_memory_history_candidate_action;
DROP POLICY item_cleanup_delete ON cj_memory_history_candidate_action;
DROP POLICY item_cleanup_read ON cj_memory_history_job;
DROP POLICY item_cleanup_delete ON cj_memory_history_job;
DROP TRIGGER cj_memory_erasure_identifier ON cj_memory_item;
DROP TRIGGER cj_memory_erasure_identifier ON cj_memory_source;
DROP TRIGGER cj_memory_erasure_identifier ON cj_memory_operation;
DROP FUNCTION cj_memory_erasure_identifier();
DROP TABLE cj_memory_erasure_manifest;
DROP TABLE cj_memory_erasure_fence;
