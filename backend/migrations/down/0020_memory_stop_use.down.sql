-- local runtime only: refuse nonempty stop-use semantics; no physical cleanup.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cj_memory_management_action WHERE operation='withdraw'
           OR withdrawal_history IS NOT NULL OR withdrawal_epoch IS NOT NULL) THEN
  RAISE EXCEPTION 'stop-use history is not empty; retain schema and reconcile originals';
 END IF;
END $$;
REVOKE UPDATE(active) ON cj_memory_source FROM cj_m1_runtime;
ALTER TABLE cj_memory_management_action
 DROP CONSTRAINT cj_memory_stop_use_shape,
 DROP CONSTRAINT cj_memory_edit_source_shape,
 DROP CONSTRAINT cj_memory_management_action_check,
 DROP CONSTRAINT cj_memory_management_action_status_check,
 DROP CONSTRAINT cj_memory_management_action_operation_check,
 DROP COLUMN withdrawal_epoch,
 DROP COLUMN withdrawal_history;
ALTER TABLE cj_memory_management_action
 ADD CONSTRAINT cj_memory_management_action_operation_check CHECK(operation IN ('pause','resume','edit')),
 ADD CONSTRAINT cj_memory_management_action_status_check CHECK(status IN ('active','disabled')),
 ADD CONSTRAINT cj_memory_management_action_check CHECK(
  (operation='pause' AND status='disabled') OR (operation='resume' AND status='active') OR
  (operation='edit' AND status IN ('active','disabled'))),
 ADD CONSTRAINT cj_memory_edit_source_shape CHECK(
  (operation IN ('pause','resume') AND previous_source_id IS NULL AND new_source_id IS NULL AND disabled_by_version IS NULL) OR
  (operation='edit' AND previous_source_id IS NOT NULL AND new_source_id IS NOT NULL AND previous_source_id<>new_source_id
   AND ((status='active' AND disabled_by_version IS NULL) OR
        (status='disabled' AND disabled_by_version IS NOT NULL AND disabled_by_version<version))));
