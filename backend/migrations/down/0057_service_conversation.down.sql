-- local runtime only: refuse to drop service conversations or server-initiated messages.
LOCK TABLE cj_message_chat,cj_service_message,cj_service_message_authority IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_service_message) OR EXISTS(SELECT 1 FROM cj_service_message_authority)
 OR EXISTS(SELECT 1 FROM cj_message_chat WHERE conversation_kind='service') THEN
  RAISE EXCEPTION 'service_conversation down refused: retained private data';
 END IF;
END $$;
DROP TRIGGER message_not_service ON cj_message_needs_binding;
DROP TRIGGER message_not_service ON cj_message_edit_reference;
DROP TRIGGER message_not_service ON cj_message_trip_reference;
DROP TRIGGER message_not_service ON cj_message_travel_reference;
DROP TRIGGER message_not_service ON cj_message_delivery;
DROP TRIGGER message_receipt_not_service_sequence ON cj_message_receipt;
DROP TABLE cj_service_message_authority;
DROP TABLE cj_service_message;
DROP TRIGGER message_chat_kind_fixed ON cj_message_chat;
DROP INDEX cj_message_chat_one_service;
ALTER TABLE cj_message_chat DROP COLUMN conversation_kind;
DROP FUNCTION cj_message_not_service();
DROP FUNCTION cj_service_message_reject_truncate();
DROP FUNCTION cj_service_message_append_only();
DROP FUNCTION cj_message_receipt_not_service_sequence();
DROP FUNCTION cj_service_message_head();
DROP FUNCTION cj_message_chat_kind_fixed();
