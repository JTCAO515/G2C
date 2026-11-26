-- local runtime only for the synthetic case audit extension.
ALTER TABLE jt_workbench.audit
    ADD COLUMN case_action text CHECK (case_action IN ('claim', 'advance', 'confirm', 'reject')),
    ADD COLUMN case_step text,
    ADD COLUMN case_revision bigint CHECK (case_revision >= 0),
    ADD COLUMN case_reason text,
    ADD CHECK (case_action IS NULL OR (action = 'decide' AND case_id IS NOT NULL));

-- Keep the original base marker readable by the previous startup entry.
CREATE TABLE jt_workbench.case_audit_version (version integer PRIMARY KEY CHECK (version = 2));
INSERT INTO jt_workbench.case_audit_version VALUES (2);
GRANT SELECT ON jt_workbench.case_audit_version TO jt_workbench_runtime;
