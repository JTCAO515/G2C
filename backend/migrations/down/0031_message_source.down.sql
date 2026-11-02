-- local runtime only: refuse to discard durable end signals or reserved type data.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_message_chat WHERE end_id IS NOT NULL OR conversation_type<>'travel') THEN
  RAISE EXCEPTION 'message_source down refused: retained end signal';
 END IF;
END $$;
DROP TRIGGER cj_message_no_send_after_end ON cj_message_receipt;
DROP FUNCTION cj_message_no_send_after_end();
DROP TRIGGER cj_message_end_immutable ON cj_message_chat;
DROP FUNCTION cj_message_end_immutable();
ALTER TABLE cj_message_chat DROP CONSTRAINT cj_message_end_shape,
 DROP CONSTRAINT cj_message_travel_only,
 DROP COLUMN conversation_type,DROP COLUMN end_id,DROP COLUMN end_generation,
 DROP COLUMN end_epoch,DROP COLUMN end_sequence;
DROP TYPE cj_conversation_type;
