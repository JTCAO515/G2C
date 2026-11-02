-- local runtime only: never downgrade retained original device bindings/calls.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_cleanup_device_binding) OR EXISTS(SELECT 1 FROM cj_cleanup_device_call) THEN
  RAISE EXCEPTION 'device bridge contains original binding/call evidence';
 END IF;
END $$;
ALTER TABLE cj_cleanup_device_binding DROP CONSTRAINT cleanup_device_protocol_state_unique;
ALTER TABLE cj_cleanup_device_binding DROP COLUMN protocol;
ALTER TABLE cj_cleanup_device_binding ADD UNIQUE(subject_digest,device_id,state_ref);
