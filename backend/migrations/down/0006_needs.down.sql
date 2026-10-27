-- Reverts 0006 (backend/needs/sql/candidate.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_needs_revision;
DROP TABLE cj_needs_record;
DROP TABLE cj_needs_scope;
