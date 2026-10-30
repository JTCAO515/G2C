-- local runtime only: retain nonempty edit history; never delete data.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM cj_memory_management_action
             WHERE operation='edit' OR previous_source_id IS NOT NULL
                OR new_source_id IS NOT NULL OR disabled_by_version IS NOT NULL) THEN
    RAISE EXCEPTION 'edit history is not empty; retain schema and reconcile originals';
  END IF;
END $$;
REVOKE UPDATE(status,version,original_input,source_id,source_version)
  ON cj_memory_item FROM cj_m1_runtime;
REVOKE SELECT,INSERT ON cj_memory_management_action FROM cj_m1_runtime;
DROP POLICY cj_m2_memory_management_scope ON cj_memory_management_action;
ALTER TABLE cj_memory_management_action NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_management_action DISABLE ROW LEVEL SECURITY;
ALTER TABLE cj_memory_management_action
  DROP CONSTRAINT cj_memory_edit_pause_anchor_fk,
  DROP CONSTRAINT cj_memory_edit_new_source_fk,
  DROP CONSTRAINT cj_memory_edit_previous_source_fk,
  DROP CONSTRAINT cj_memory_edit_source_shape,
  DROP CONSTRAINT cj_memory_management_action_check,
  DROP CONSTRAINT cj_memory_management_action_operation_check,
  DROP COLUMN disabled_by_version,
  DROP COLUMN new_source_id,
  DROP COLUMN previous_source_id;
ALTER TABLE cj_memory_management_action
  ADD CONSTRAINT cj_memory_management_action_operation_check
    CHECK (operation IN ('pause','resume')),
  ADD CONSTRAINT cj_memory_management_action_check CHECK (
    (operation='pause' AND status='disabled') OR
    (operation='resume' AND status='active'));
