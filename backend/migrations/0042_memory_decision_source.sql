-- local runtime only: exact accepted-decision provenance, never a Memory value.
-- Existing runtime INSERT/SELECT and cleanup account DELETE cover this column.
ALTER TABLE cj_memory_history_origin ADD COLUMN decision_source_sha256 text
 CHECK(decision_source_sha256 IS NULL OR decision_source_sha256 ~ '^[0-9a-f]{64}$');
CREATE INDEX cj_memory_history_origin_decision ON cj_memory_history_origin(scope,decision_source_sha256)
 WHERE decision_source_sha256 IS NOT NULL;

-- V3 logical choices can be referenced from another admitted message. Preserve
-- first producer and all previous refs; old V1/V2 NULL-digest rows stay immutable.
GRANT UPDATE(origin_refs) ON cj_memory_history_origin TO cj_m1_runtime;
CREATE FUNCTION cj_memory_decision_origin_append() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF current_user='cj_m1_runtime' AND (
   OLD.decision_source_sha256 IS NULL
   OR (to_jsonb(NEW)-'origin_refs') IS DISTINCT FROM (to_jsonb(OLD)-'origin_refs')
   OR NOT NEW.origin_refs @> OLD.origin_refs) THEN
  RAISE EXCEPTION 'original memory provenance is immutable';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_memory_decision_origin_append() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cj_memory_decision_origin_append() TO cj_m1_runtime;
CREATE TRIGGER cj_memory_decision_origin_append BEFORE UPDATE ON cj_memory_history_origin
 FOR EACH ROW EXECUTE FUNCTION cj_memory_decision_origin_append();
