-- local runtime only: V3 original client-action mapping; no runtime privilege.
ALTER TABLE cj_cleanup_device_binding DROP CONSTRAINT cj_cleanup_device_binding_protocol_check;
ALTER TABLE cj_cleanup_device_binding ADD CONSTRAINT cj_cleanup_device_binding_protocol_check
 CHECK(protocol IN ('CLEANUP-DEVICE@1','CLEANUP-DEVICE@2','CLEANUP-DEVICE@3'));
CREATE TABLE cj_cleanup_device_action (
 subject_digest text NOT NULL CHECK(subject_digest~'^[0-9a-f]{64}$'),
 action_id text NOT NULL,input_digest text NOT NULL CHECK(input_digest~'^[0-9a-f]{64}$'),
 binding_id text NOT NULL REFERENCES cj_cleanup_device_binding(binding_id),
 invocation_id text NOT NULL REFERENCES cj_cleanup_device_call(invocation_id),
 PRIMARY KEY(subject_digest,action_id)
);
ALTER TABLE cj_cleanup_device_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_cleanup_device_action FORCE ROW LEVEL SECURITY;
CREATE POLICY cleanup_subject ON cj_cleanup_device_action TO cj_local_cleanup
 USING(subject_digest=nullif(current_setting('cj.cleanup_subject',true),''))
 WITH CHECK(subject_digest=nullif(current_setting('cj.cleanup_subject',true),''));
GRANT SELECT,INSERT ON cj_cleanup_device_action TO cj_local_cleanup;
