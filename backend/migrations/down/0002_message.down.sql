-- Reverts 0002 (backend/message/sql/candidate.sql). Tables in reverse dependency order; triggers/indexes go with their tables.
DROP TABLE cj_message_draft;
DROP TABLE cj_message_delivery;
DROP TABLE cj_message_receipt;
DROP TABLE cj_message_chat;
DROP TABLE cj_message_scope;
DROP FUNCTION cj_message_invalidate_list();
