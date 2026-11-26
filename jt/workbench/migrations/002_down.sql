-- local runtime only: 001_down still guards the entire rollback against persisted data.
ALTER TABLE jt_workbench.audit DROP COLUMN case_action, DROP COLUMN case_step,
    DROP COLUMN case_revision, DROP COLUMN case_reason;
DROP TABLE jt_workbench.case_audit_version;
