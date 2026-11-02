-- local runtime only: inherited V1/V2 bytes remain; refuse every new V3 record.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_cleanup_device_action)
 OR EXISTS(SELECT 1 FROM cj_cleanup_device_binding WHERE protocol='CLEANUP-DEVICE@3')
 OR EXISTS(SELECT 1 FROM cj_cleanup_device_call WHERE convert_from(request_bytes,'UTF8')::jsonb->>'version'='CLEANUP-DEVICE@3') THEN
  RAISE EXCEPTION 'original V3 device action evidence retained';
 END IF;
END $$;
DROP TABLE cj_cleanup_device_action;
ALTER TABLE cj_cleanup_device_binding DROP CONSTRAINT cj_cleanup_device_binding_protocol_check;
ALTER TABLE cj_cleanup_device_binding ADD CONSTRAINT cj_cleanup_device_binding_protocol_check
 CHECK(protocol IN ('CLEANUP-DEVICE@1','CLEANUP-DEVICE@2'));
