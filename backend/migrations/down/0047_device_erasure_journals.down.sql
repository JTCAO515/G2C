-- local runtime only: never discard an original V4 binding/call or receipt.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_cleanup_device_binding WHERE protocol='CLEANUP-DEVICE@4')
 OR EXISTS(SELECT 1 FROM cj_cleanup_device_call WHERE convert_from(request_bytes,'UTF8')::jsonb->>'version'='CLEANUP-DEVICE@4') THEN
  RAISE EXCEPTION 'original V4 device evidence retained';
 END IF;
END $$;
ALTER TABLE cj_cleanup_device_binding DROP CONSTRAINT cj_cleanup_device_binding_protocol_check;
ALTER TABLE cj_cleanup_device_binding ADD CONSTRAINT cj_cleanup_device_binding_protocol_check
 CHECK(protocol IN ('CLEANUP-DEVICE@1','CLEANUP-DEVICE@2','CLEANUP-DEVICE@3'));
