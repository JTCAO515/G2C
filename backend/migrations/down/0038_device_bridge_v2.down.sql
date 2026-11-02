-- local runtime only: refuse every new protocol while preserving legacy V1 data.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_cleanup_device_binding WHERE protocol<>'CLEANUP-DEVICE@1')
 OR EXISTS(SELECT 1 FROM cj_cleanup_device_call
           WHERE convert_from(request_bytes,'UTF8')::jsonb->>'version' IS DISTINCT FROM 'CLEANUP-DEVICE@1') THEN
  RAISE EXCEPTION 'device bridge contains original binding/call evidence';
 END IF;
END $$;
ALTER TABLE cj_cleanup_device_binding DROP CONSTRAINT cleanup_device_protocol_state_unique;
ALTER TABLE cj_cleanup_device_binding DROP COLUMN protocol;
ALTER TABLE cj_cleanup_device_binding ADD UNIQUE(subject_digest,device_id,state_ref);
