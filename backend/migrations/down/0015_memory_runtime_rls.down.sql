-- Restore the pre-0015 local role/policy state; never delete stored MEMORY data.
REVOKE UPDATE(scope) ON cj_memory_source FROM cj_m1_runtime;
REVOKE UPDATE(epoch) ON cj_memory_scope FROM cj_m1_runtime;
REVOKE SELECT, INSERT ON cj_memory_scope,cj_memory_source,cj_memory_item,cj_memory_operation FROM cj_m1_runtime;
DROP POLICY cj_m2_memory_scope ON cj_memory_operation;
ALTER TABLE cj_memory_operation NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_operation DISABLE ROW LEVEL SECURITY;
DROP POLICY cj_m2_memory_scope ON cj_memory_item;
ALTER TABLE cj_memory_item NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_item DISABLE ROW LEVEL SECURITY;
DROP POLICY cj_m2_memory_scope ON cj_memory_source;
ALTER TABLE cj_memory_source NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_source DISABLE ROW LEVEL SECURITY;
DROP POLICY cj_m2_memory_scope ON cj_memory_scope;
ALTER TABLE cj_memory_scope NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_scope DISABLE ROW LEVEL SECURITY;
