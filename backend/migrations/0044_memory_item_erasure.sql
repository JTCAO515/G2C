-- local runtime only: original item-erasure association and noncontent fences.
-- No runtime DELETE, new role, BYPASSRLS or SECURITY DEFINER.
CREATE TABLE cj_memory_erasure_manifest (
 scope text NOT NULL REFERENCES cj_memory_scope(scope),
 action_id text NOT NULL,operation_id text NOT NULL,
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 32768),
 input_sha256 text NOT NULL CHECK(input_sha256=encode(sha256(original_input),'hex')),
 association bytea NOT NULL CHECK(octet_length(association) BETWEEN 1 AND 1000000),
 association_sha256 text NOT NULL CHECK(association_sha256=encode(sha256(association),'hex')),
 evidence bytea NOT NULL CHECK(octet_length(evidence) BETWEEN 1 AND 8000000),
 evidence_sha256 text NOT NULL CHECK(evidence_sha256=encode(sha256(evidence),'hex')),
 item_id text NOT NULL,item_version bigint NOT NULL CHECK(item_version>0),
 scope_epoch bigint NOT NULL CHECK(scope_epoch>0),
 PRIMARY KEY(scope,operation_id),UNIQUE(scope,action_id),UNIQUE(scope,item_id)
);
ALTER TABLE cj_memory_erasure_manifest ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_erasure_manifest FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_erasure_manifest TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND public.cj_account_scope_current(scope));
GRANT SELECT,INSERT ON cj_memory_erasure_manifest TO cj_m1_runtime;

CREATE TABLE cj_memory_erasure_fence (
 scope_digest text NOT NULL CHECK(scope_digest ~ '^[0-9a-f]{64}$'),
 kind text NOT NULL CHECK(kind IN ('item','source','operation','message','decision','job','job_id','attempt_id','action')),
 reference_sha256 text NOT NULL CHECK(reference_sha256 ~ '^[0-9a-f]{64}$'),
 original_input_sha256 text CHECK(original_input_sha256 IS NULL OR original_input_sha256 ~ '^[0-9a-f]{64}$'),
 -- Only irreversible original-operation metadata; no IDs, source text or value.
 operation_id text,item_version bigint,scope_epoch bigint,
 PRIMARY KEY(scope_digest,kind,reference_sha256),
 CHECK((kind='action' AND operation_id IS NOT NULL AND item_version IS NOT NULL AND scope_epoch IS NOT NULL
         AND item_version>0 AND scope_epoch>0)
    OR (kind<>'action' AND operation_id IS NULL AND item_version IS NULL AND scope_epoch IS NULL)),
 CHECK(kind<>'action' OR original_input_sha256 IS NOT NULL)
);
ALTER TABLE cj_memory_erasure_fence ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_erasure_fence FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_erasure_fence TO cj_m1_runtime
 USING(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex'))
 WITH CHECK(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.message_scope',true),''),'UTF8')),'hex'));
GRANT SELECT,INSERT ON cj_memory_erasure_fence TO cj_m1_runtime;

CREATE POLICY original_cleanup_read ON cj_memory_erasure_manifest FOR SELECT TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'')
 AND current_setting('cj.cleanup_purpose',true) IN ('account','memory')
 AND (current_setting('cj.cleanup_purpose',true)='account'
      OR operation_id=nullif(current_setting('cj.cleanup_operation',true),''))
 AND EXISTS(SELECT 1 FROM cj_cleanup_operation o WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
   AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND NOT o.blocked
   AND o.purpose=current_setting('cj.cleanup_purpose',true)));
CREATE POLICY original_cleanup_delete ON cj_memory_erasure_manifest FOR DELETE TO cj_local_cleanup
 USING(scope=nullif(current_setting('cj.cleanup_scope',true),'')
 AND current_setting('cj.cleanup_purpose',true) IN ('account','memory')
 AND (current_setting('cj.cleanup_purpose',true)='account'
      OR operation_id=nullif(current_setting('cj.cleanup_operation',true),''))
 AND EXISTS(SELECT 1 FROM cj_cleanup_operation o JOIN cj_cleanup_step s
   ON (s.subject_digest,s.operation_id)=(o.subject_digest,o.operation_id)
   WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
    AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'') AND NOT o.blocked
    AND o.purpose=current_setting('cj.cleanup_purpose',true)
    AND s.target='business/memory-authoritative' AND s.state='in_progress'
    AND s.request_bytes IS NOT NULL AND s.request_digest=encode(sha256(s.request_bytes),'hex')));
GRANT SELECT,DELETE ON cj_memory_erasure_manifest TO cj_local_cleanup;
CREATE POLICY original_cleanup_read ON cj_memory_erasure_fence FOR SELECT TO cj_local_cleanup
 USING(scope_digest=encode(sha256(convert_to(nullif(current_setting('cj.cleanup_scope',true),''),'UTF8')),'hex'));
GRANT SELECT ON cj_memory_erasure_fence TO cj_local_cleanup;

-- Old source/item/operation IDs cannot be recreated by any runtime writer.
CREATE FUNCTION cj_memory_erasure_identifier() RETURNS trigger
LANGUAGE plpgsql VOLATILE SECURITY INVOKER AS $$
DECLARE field_name text;fence_kind text;identifier text;
BEGIN
 IF current_user='cj_m1_runtime' THEN
  CASE TG_TABLE_NAME
   WHEN 'cj_memory_item' THEN field_name:='item_id';fence_kind:='item';
   WHEN 'cj_memory_source' THEN field_name:='source_id';fence_kind:='source';
   WHEN 'cj_memory_operation' THEN field_name:='operation_id';fence_kind:='operation';
   WHEN 'cj_memory_history_job' THEN field_name:='job_id';fence_kind:='job_id';
  END CASE;
  identifier:=to_jsonb(NEW)->>field_name;
  IF EXISTS(SELECT 1 FROM cj_memory_erasure_fence f
   WHERE f.scope_digest=encode(sha256(convert_to(NEW.scope,'UTF8')),'hex') AND f.kind=fence_kind
    AND f.reference_sha256=encode(sha256(convert_to(identifier,'UTF8')),'hex'))
    OR (TG_TABLE_NAME='cj_memory_history_job' AND EXISTS(
      SELECT 1 FROM cj_memory_erasure_fence f WHERE f.scope_digest=encode(sha256(convert_to(NEW.scope,'UTF8')),'hex')
       AND f.kind='attempt_id' AND f.reference_sha256=encode(sha256(convert_to(to_jsonb(NEW)->>'attempt_id','UTF8')),'hex'))) THEN
   RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='original Memory identifier erased';
  END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION cj_memory_erasure_identifier() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cj_memory_erasure_identifier() TO cj_m1_runtime;
CREATE TRIGGER cj_memory_erasure_identifier BEFORE INSERT OR UPDATE ON cj_memory_item
 FOR EACH ROW EXECUTE FUNCTION cj_memory_erasure_identifier();
CREATE TRIGGER cj_memory_erasure_identifier BEFORE INSERT OR UPDATE ON cj_memory_source
 FOR EACH ROW EXECUTE FUNCTION cj_memory_erasure_identifier();
CREATE TRIGGER cj_memory_erasure_identifier BEFORE INSERT ON cj_memory_operation
 FOR EACH ROW EXECUTE FUNCTION cj_memory_erasure_identifier();
CREATE TRIGGER cj_memory_erasure_identifier BEFORE INSERT ON cj_memory_history_job
 FOR EACH ROW EXECUTE FUNCTION cj_memory_erasure_identifier();

DO $item_cleanup$
DECLARE object_name text;guard text;
BEGIN
 guard := $condition$
  scope=nullif(current_setting('cj.cleanup_scope',true),'')
  AND current_setting('cj.cleanup_purpose',true)='memory'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o JOIN cj_cleanup_step s
    ON (s.subject_digest,s.operation_id)=(o.subject_digest,o.operation_id)
    WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
     AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'')
     AND o.purpose='memory' AND NOT o.blocked AND o.plan_bytes IS NOT NULL
     AND s.state='in_progress' AND s.request_bytes IS NOT NULL
     AND s.request_digest=encode(sha256(s.request_bytes),'hex')
     AND s.target IN ('memory-derived','business/memory-management-actions','business/memory-authoritative','business/trip-authoritative')
     AND convert_from(o.plan_bytes,'UTF8')::jsonb->s.target->>'domain_scope'=scope)
 $condition$;
 FOREACH object_name IN ARRAY ARRAY['cj_memory_scope','cj_trip_scope'] LOOP
  EXECUTE format('CREATE POLICY item_cleanup_lock ON %I FOR UPDATE TO cj_local_cleanup USING (%s) WITH CHECK (%s)',object_name,guard,guard);
 END LOOP;
 FOREACH object_name IN ARRAY ARRAY['cj_memory_history_origin','cj_memory_history_candidate_action','cj_memory_history_job'] LOOP
  EXECUTE format('CREATE POLICY item_cleanup_read ON %I FOR SELECT TO cj_local_cleanup USING (%s)',object_name,guard);
  EXECUTE format('CREATE POLICY item_cleanup_delete ON %I FOR DELETE TO cj_local_cleanup USING (%s)',object_name,guard);
 END LOOP;
END $item_cleanup$;
