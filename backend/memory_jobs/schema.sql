-- M3 memory history candidate; local runtime only. Not registered/applied yet.
-- Move into the next append-only migration under the shared migration lock.
CREATE TABLE cj_memory_history_fence (
 scope text PRIMARY KEY,
 erased boolean NOT NULL DEFAULT false
);
CREATE TABLE cj_memory_history_consent (
 scope text NOT NULL REFERENCES cj_memory_scope(scope),
 conversation_id text NOT NULL,
 generation text NOT NULL,
 message_epoch bigint NOT NULL CHECK(message_epoch>=0),
 enabled boolean NOT NULL,
 source_version bigint NOT NULL CHECK(source_version>=1),
 withdrawal_epoch bigint NOT NULL CHECK(withdrawal_epoch>=1),
 PRIMARY KEY(scope,conversation_id)
);
CREATE TABLE cj_memory_history_action (
 scope text NOT NULL REFERENCES cj_memory_scope(scope),
 action_id text NOT NULL,
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 32768),
 receipt bytea NOT NULL CHECK(octet_length(receipt) BETWEEN 1 AND 32768),
 PRIMARY KEY(scope,action_id)
);
CREATE TABLE cj_memory_history_job (
 scope text NOT NULL REFERENCES cj_memory_scope(scope),
 job_id text NOT NULL,
 attempt_id text NOT NULL,
 source_key text NOT NULL CHECK(source_key ~ '^[0-9a-f]{64}$'),
 stream_key text NOT NULL CHECK(stream_key ~ '^[0-9a-f]{64}$'),
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 32768),
 batch bytea NOT NULL CHECK(octet_length(batch) BETWEEN 1 AND 262144),
 memory_epoch bigint NOT NULL CHECK(memory_epoch>=1),
 state text NOT NULL CHECK(state IN ('pending','inflight','unknown','completed','cancelled','failed')),
 processed bigint NOT NULL CHECK(processed>=0),
 candidate bytea CHECK(candidate IS NULL OR octet_length(candidate) BETWEEN 1 AND 16384),
 PRIMARY KEY(scope,job_id),
 UNIQUE(scope,attempt_id),
 UNIQUE(scope,source_key),
 CHECK((state='completed')=(candidate IS NOT NULL))
);
CREATE UNIQUE INDEX cj_memory_history_unresolved ON cj_memory_history_job(scope,stream_key)
 WHERE state IN ('pending','inflight','unknown');
CREATE TABLE cj_memory_history_cursor (
 scope text NOT NULL REFERENCES cj_memory_scope(scope),
 stream_key text NOT NULL CHECK(stream_key ~ '^[0-9a-f]{64}$'),
 processed bigint NOT NULL CHECK(processed>=0),
 PRIMARY KEY(scope,stream_key)
);

ALTER TABLE cj_memory_history_fence ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_history_fence FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_history_fence TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND NOT erased);
ALTER TABLE cj_memory_history_consent ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_history_consent FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_history_consent TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_memory_history_fence f WHERE f.scope=cj_memory_history_consent.scope AND NOT f.erased));
ALTER TABLE cj_memory_history_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_history_action FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_history_action TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_memory_history_fence f WHERE f.scope=cj_memory_history_action.scope AND NOT f.erased));
ALTER TABLE cj_memory_history_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_history_job FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_history_job TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_memory_history_fence f WHERE f.scope=cj_memory_history_job.scope AND NOT f.erased));
ALTER TABLE cj_memory_history_cursor ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_history_cursor FORCE ROW LEVEL SECURITY;
CREATE POLICY own ON cj_memory_history_cursor TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.message_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.message_scope',true),'') AND EXISTS(
  SELECT 1 FROM cj_memory_history_fence f WHERE f.scope=cj_memory_history_cursor.scope AND NOT f.erased));

GRANT SELECT,INSERT ON cj_memory_history_consent,cj_memory_history_action,
 cj_memory_history_job,cj_memory_history_cursor TO cj_m1_runtime;
GRANT SELECT ON cj_memory_history_fence TO cj_m1_runtime;
GRANT INSERT(scope),UPDATE(scope) ON cj_memory_history_fence TO cj_m1_runtime;
GRANT UPDATE(generation,message_epoch,enabled,source_version,withdrawal_epoch)
 ON cj_memory_history_consent TO cj_m1_runtime;
GRANT UPDATE(state,processed,candidate) ON cj_memory_history_job TO cj_m1_runtime;
GRANT UPDATE(processed) ON cj_memory_history_cursor TO cj_m1_runtime;
-- Same approved #402 role and original-result ledger; no duplicate C ledger.
-- The frozen plan, not a freely supplied cleanup_scope alone, binds the owner.
DO $history_acl$
DECLARE
 object_name text;
 plan_guard text := $condition$
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
 FOREACH object_name IN ARRAY ARRAY['cj_memory_history_consent','cj_memory_history_action',
                                   'cj_memory_history_job','cj_memory_history_cursor'] LOOP
  EXECUTE format('CREATE POLICY cleanup_read ON %I FOR SELECT TO cj_local_cleanup USING (%s)',object_name,plan_guard);
  EXECUTE format('CREATE POLICY cleanup_delete ON %I FOR DELETE TO cj_local_cleanup USING (%s)',object_name,plan_guard);
  EXECUTE format('GRANT SELECT,DELETE ON %I TO cj_local_cleanup',object_name);
 END LOOP;
 EXECUTE format('CREATE POLICY cleanup_read ON cj_memory_history_fence FOR SELECT TO cj_local_cleanup USING (%s)',plan_guard);
 EXECUTE format('CREATE POLICY cleanup_insert ON cj_memory_history_fence FOR INSERT TO cj_local_cleanup WITH CHECK (erased AND (%s))',plan_guard);
 EXECUTE format('CREATE POLICY cleanup_update ON cj_memory_history_fence FOR UPDATE TO cj_local_cleanup USING (%s) WITH CHECK (erased AND (%s))',plan_guard,plan_guard);
 -- Scope-only UPDATE permits the canonical lock; frozen-plan RLS disallows renaming.
 EXECUTE format('CREATE POLICY cj_m3_history_cleanup_lock ON cj_memory_scope FOR UPDATE TO cj_local_cleanup USING (%s) WITH CHECK (%s)',plan_guard,plan_guard);
END $history_acl$;
GRANT SELECT ON cj_memory_history_fence TO cj_local_cleanup;
GRANT INSERT(scope,erased),UPDATE(erased) ON cj_memory_history_fence TO cj_local_cleanup;
GRANT UPDATE(scope) ON cj_memory_scope TO cj_local_cleanup;
-- No runtime DELETE/TRUNCATE, role switching or default privilege expansion.
