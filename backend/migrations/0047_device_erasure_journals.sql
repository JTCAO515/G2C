-- local runtime only: DEVICE4 covers the two journals provided by merged A480.
-- No new table, role, grant or runtime privilege.
ALTER TABLE cj_cleanup_device_binding DROP CONSTRAINT cj_cleanup_device_binding_protocol_check;
ALTER TABLE cj_cleanup_device_binding ADD CONSTRAINT cj_cleanup_device_binding_protocol_check
 CHECK(protocol IN ('CLEANUP-DEVICE@1','CLEANUP-DEVICE@2','CLEANUP-DEVICE@3','CLEANUP-DEVICE@4'));
