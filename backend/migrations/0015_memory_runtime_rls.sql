-- M2 local MEMORY activation (#226). No production/cloud application is authorized here.
-- Reuse the existing transaction-local principal scope and non-owner runtime role.
ALTER TABLE cj_memory_scope ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_scope FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m2_memory_scope ON cj_memory_scope TO cj_m1_runtime
  USING (scope = nullif(current_setting('cj.message_scope', true), ''))
  WITH CHECK (scope = nullif(current_setting('cj.message_scope', true), ''));
ALTER TABLE cj_memory_source ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_source FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m2_memory_scope ON cj_memory_source TO cj_m1_runtime
  USING (scope = nullif(current_setting('cj.message_scope', true), ''))
  WITH CHECK (scope = nullif(current_setting('cj.message_scope', true), ''));
ALTER TABLE cj_memory_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_item FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m2_memory_scope ON cj_memory_item TO cj_m1_runtime
  USING (scope = nullif(current_setting('cj.message_scope', true), ''))
  WITH CHECK (scope = nullif(current_setting('cj.message_scope', true), ''));
ALTER TABLE cj_memory_operation ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_operation FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m2_memory_scope ON cj_memory_operation TO cj_m1_runtime
  USING (scope = nullif(current_setting('cj.message_scope', true), ''))
  WITH CHECK (scope = nullif(current_setting('cj.message_scope', true), ''));
GRANT SELECT, INSERT ON cj_memory_scope,cj_memory_source,cj_memory_item,cj_memory_operation TO cj_m1_runtime;
GRANT UPDATE(epoch) ON cj_memory_scope TO cj_m1_runtime;
-- SELECT FOR UPDATE needs UPDATE on at least one column (PostgreSQL 16 SELECT).
-- scope-only privilege permits locking; matching USING/WITH CHECK prevents reassignment.
-- It grants no update of source approval, content, version, activity or expiry.
GRANT UPDATE(scope) ON cj_memory_source TO cj_m1_runtime;
