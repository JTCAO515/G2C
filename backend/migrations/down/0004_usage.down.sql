-- Reverts 0004 (backend/usage/sql/001_candidate.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_usage_ledger_candidate;
