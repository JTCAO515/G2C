-- Reverts 0009 (backend/memory/schema.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_memory_operation;
DROP TABLE cj_memory_item;
DROP TABLE cj_memory_source;
DROP TABLE cj_memory_scope;
