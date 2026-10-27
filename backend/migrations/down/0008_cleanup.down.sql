-- Reverts 0008 (backend/cleanup/sql/candidate.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_cleanup_journal_candidate;
