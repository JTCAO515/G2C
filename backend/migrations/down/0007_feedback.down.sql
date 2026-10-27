-- Reverts 0007 (backend/feedback/sql/candidate.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_feedback_action;
