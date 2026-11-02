-- local runtime only: additive device protocol enrollment; old V1 bindings stay V1.
ALTER TABLE cj_cleanup_device_binding ADD COLUMN protocol text NOT NULL DEFAULT 'CLEANUP-DEVICE@1'
 CHECK(protocol IN ('CLEANUP-DEVICE@1','CLEANUP-DEVICE@2'));
DO $$ DECLARE original_constraint name; BEGIN
 SELECT conname INTO STRICT original_constraint FROM pg_constraint
 WHERE conrelid='cj_cleanup_device_binding'::regclass AND contype='u'
 AND pg_get_constraintdef(oid)='UNIQUE (subject_digest, device_id, state_ref)';
 EXECUTE format('ALTER TABLE cj_cleanup_device_binding DROP CONSTRAINT %I',original_constraint);
END $$;
ALTER TABLE cj_cleanup_device_binding ADD CONSTRAINT cleanup_device_protocol_state_unique
 UNIQUE(subject_digest,device_id,state_ref,protocol);
