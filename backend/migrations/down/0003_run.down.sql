-- Reverts 0003 (backend/run/sql/candidate.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_run_event;
DROP TABLE cj_run_record;
DROP TABLE cj_run_scope;
DROP FUNCTION cj_run_guard_original_binding();
