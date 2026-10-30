-- local runtime only: #270 stop-use; retains all business bytes and original receipts.
ALTER TABLE cj_memory_management_action
 ADD COLUMN withdrawal_history jsonb,
 ADD COLUMN withdrawal_epoch bigint;
ALTER TABLE cj_memory_management_action
 DROP CONSTRAINT cj_memory_management_action_operation_check,
 DROP CONSTRAINT cj_memory_management_action_status_check,
 DROP CONSTRAINT cj_memory_management_action_check,
 DROP CONSTRAINT cj_memory_edit_source_shape;
ALTER TABLE cj_memory_management_action
 ADD CONSTRAINT cj_memory_management_action_operation_check CHECK(operation IN ('pause','resume','edit','withdraw')),
 ADD CONSTRAINT cj_memory_management_action_status_check CHECK(status IN ('active','disabled','withdrawn')),
 ADD CONSTRAINT cj_memory_management_action_check CHECK(
  (operation='pause' AND status='disabled') OR (operation='resume' AND status='active') OR
  (operation='edit' AND status IN ('active','disabled')) OR (operation='withdraw' AND status='withdrawn')),
 ADD CONSTRAINT cj_memory_edit_source_shape CHECK(
  (operation IN ('pause','resume','withdraw') AND previous_source_id IS NULL AND new_source_id IS NULL AND disabled_by_version IS NULL) OR
  (operation='edit' AND previous_source_id IS NOT NULL AND new_source_id IS NOT NULL AND previous_source_id<>new_source_id
   AND ((status='active' AND disabled_by_version IS NULL) OR
        (status='disabled' AND disabled_by_version IS NOT NULL AND disabled_by_version<version)))),
 ADD CONSTRAINT cj_memory_stop_use_shape CHECK(
  (operation='withdraw' AND withdrawal_history IS NOT NULL AND withdrawal_epoch IS NOT NULL AND withdrawal_epoch>1
   AND jsonb_typeof(withdrawal_history)='array' AND jsonb_array_length(withdrawal_history) BETWEEN 1 AND 1000) OR
  (operation<>'withdraw' AND withdrawal_history IS NULL AND withdrawal_epoch IS NULL));
GRANT UPDATE(active) ON cj_memory_source TO cj_m1_runtime;
