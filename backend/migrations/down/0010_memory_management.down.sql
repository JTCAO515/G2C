-- Reverts 0010 (backend/memory_management/schema.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_memory_management_action;
