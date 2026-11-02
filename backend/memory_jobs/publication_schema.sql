-- local runtime only: #410 output checkpoints, user decisions and exact origin map.
-- Candidate SQL; register in the next available append-only migration with its hook.
ALTER TABLE cj_memory_history_job ADD COLUMN result_bytes bytea
 CHECK(result_bytes IS NULL OR octet_length(result_bytes) BETWEEN 1 AND 16384);
GRANT UPDATE(result_bytes) ON cj_memory_history_job TO cj_m1_runtime;
CREATE TABLE cj_memory_history_candidate_action (
 scope text NOT NULL REFERENCES cj_memory_scope(scope),
 action_id text NOT NULL,
 candidate_id text NOT NULL,
 job_id text NOT NULL,
 attempt_id text NOT NULL,
 operation text NOT NULL CHECK(operation IN ('confirm','reject')),
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 32768),
 receipt bytea NOT NULL CHECK(octet_length(receipt) BETWEEN 1 AND 32768),
 previous_source_id text NOT NULL,
 new_source_id text,
 PRIMARY KEY(scope,action_id),UNIQUE(scope,candidate_id)
);
CREATE TABLE cj_memory_history_origin (
 scope text NOT NULL REFERENCES cj_memory_scope(scope),
 source_id text NOT NULL,
 item_id text NOT NULL,
 job_id text NOT NULL,
 attempt_id text NOT NULL,
 origin_refs jsonb NOT NULL CHECK(jsonb_typeof(origin_refs)='array'),
 PRIMARY KEY(scope,source_id),
 FOREIGN KEY(scope,source_id) REFERENCES cj_memory_source(scope,source_id),
 FOREIGN KEY(scope,item_id) REFERENCES cj_memory_item(scope,item_id)
);
CREATE INDEX cj_memory_history_origin_item ON cj_memory_history_origin(scope,item_id);
ALTER TABLE cj_memory_history_candidate_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_history_candidate_action FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_history_candidate_action TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_memory_history_fence f
   WHERE f.scope_digest=encode(sha256(convert_to(cj_memory_history_candidate_action.scope,'UTF8')),'hex') AND NOT f.erased));
ALTER TABLE cj_memory_history_origin ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_history_origin FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_history_origin TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_memory_history_fence f
   WHERE f.scope_digest=encode(sha256(convert_to(cj_memory_history_origin.scope,'UTF8')),'hex') AND NOT f.erased));
GRANT SELECT,INSERT ON cj_memory_history_candidate_action,cj_memory_history_origin TO cj_m1_runtime;
DO $publication_acl$
DECLARE object_name text;
 guard text := $condition$
  scope=nullif(current_setting('cj.cleanup_scope',true),'')
  AND current_setting('cj.cleanup_purpose',true)='account'
  AND EXISTS(SELECT 1 FROM cj_cleanup_operation o
   WHERE o.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
    AND o.operation_id=nullif(current_setting('cj.cleanup_operation',true),'')
    AND o.purpose='account' AND NOT o.blocked AND o.plan_bytes IS NOT NULL
    AND convert_from(o.plan_bytes,'UTF8')::jsonb->'memory-derived'->>'domain_scope'=scope)
  AND EXISTS(SELECT 1 FROM cj_cleanup_step s
   WHERE s.subject_digest=nullif(current_setting('cj.cleanup_subject',true),'')
    AND s.operation_id=nullif(current_setting('cj.cleanup_operation',true),'')
    AND s.target='memory-derived' AND s.state='in_progress'
    AND s.request_bytes IS NOT NULL AND s.request_digest=encode(sha256(s.request_bytes),'hex'))
 $condition$;
BEGIN
 FOREACH object_name IN ARRAY ARRAY['cj_memory_history_candidate_action','cj_memory_history_origin'] LOOP
  EXECUTE format('CREATE POLICY cleanup_read ON %I FOR SELECT TO cj_local_cleanup USING (%s)',object_name,guard);
  EXECUTE format('CREATE POLICY cleanup_delete ON %I FOR DELETE TO cj_local_cleanup USING (%s)',object_name,guard);
  EXECUTE format('GRANT SELECT,DELETE ON %I TO cj_local_cleanup',object_name);
 END LOOP;
END $publication_acl$;
