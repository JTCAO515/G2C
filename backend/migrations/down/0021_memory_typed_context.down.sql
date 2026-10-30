-- local runtime only: conservative nonempty refusal; never collapse typed data.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_memory_item) OR EXISTS(SELECT 1 FROM cj_memory_source)
    OR EXISTS(SELECT 1 FROM cj_memory_operation) OR EXISTS(SELECT 1 FROM cj_memory_management_action) THEN
  RAISE EXCEPTION 'memory data is not empty; retain typed schema and original histories';
 END IF;
END $$;
CREATE UNIQUE INDEX cj_memory_active_slot
 ON cj_memory_item(scope,subject,slot,extent,context_id) WHERE status='active';
DROP INDEX cj_memory_active_typed_slot;
ALTER TABLE cj_memory_item
 DROP CONSTRAINT cj_memory_owned_travel_context_fk,
 DROP CONSTRAINT cj_memory_context_kind_check,
 DROP COLUMN travel_context_id,
 DROP COLUMN context_kind;
