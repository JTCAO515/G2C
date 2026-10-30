-- local runtime only: #269 approved C1 edit history, minimal ACL and RLS.
ALTER TABLE cj_memory_management_action
  ADD COLUMN previous_source_id text,
  ADD COLUMN new_source_id text,
  ADD COLUMN disabled_by_version bigint;
ALTER TABLE cj_memory_management_action
  DROP CONSTRAINT cj_memory_management_action_operation_check,
  DROP CONSTRAINT cj_memory_management_action_check;
ALTER TABLE cj_memory_management_action
  ADD CONSTRAINT cj_memory_management_action_operation_check
    CHECK (operation IN ('pause','resume','edit')),
  ADD CONSTRAINT cj_memory_management_action_check CHECK (
    (operation='pause' AND status='disabled') OR
    (operation='resume' AND status='active') OR
    (operation='edit' AND status IN ('active','disabled'))),
  ADD CONSTRAINT cj_memory_edit_source_shape CHECK (
    (operation IN ('pause','resume') AND previous_source_id IS NULL
      AND new_source_id IS NULL AND disabled_by_version IS NULL) OR
    (operation='edit' AND previous_source_id IS NOT NULL
      AND new_source_id IS NOT NULL AND previous_source_id<>new_source_id
      AND ((status='active' AND disabled_by_version IS NULL) OR
           (status='disabled' AND disabled_by_version IS NOT NULL
            AND disabled_by_version<version)))),
  ADD CONSTRAINT cj_memory_edit_previous_source_fk
    FOREIGN KEY(scope,previous_source_id) REFERENCES cj_memory_source(scope,source_id),
  ADD CONSTRAINT cj_memory_edit_new_source_fk
    FOREIGN KEY(scope,new_source_id) REFERENCES cj_memory_source(scope,source_id),
  ADD CONSTRAINT cj_memory_edit_pause_anchor_fk
    FOREIGN KEY(scope,item_id,disabled_by_version)
    REFERENCES cj_memory_management_action(scope,item_id,version);
ALTER TABLE cj_memory_management_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_management_action FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_m2_memory_management_scope ON cj_memory_management_action TO cj_m1_runtime
  USING (scope=nullif(current_setting('cj.message_scope',true),''))
  WITH CHECK (scope=nullif(current_setting('cj.message_scope',true),''));
GRANT SELECT,INSERT ON cj_memory_management_action TO cj_m1_runtime;
GRANT UPDATE(status,version,original_input,source_id,source_version)
  ON cj_memory_item TO cj_m1_runtime;
