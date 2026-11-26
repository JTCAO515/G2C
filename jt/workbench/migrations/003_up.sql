-- local runtime only for synthetic operations audit metadata.
ALTER TABLE jt_workbench.audit
    ADD COLUMN operations_action text,
    ADD COLUMN operations_reference text,
    ADD CHECK ((operations_action IS NULL) = (operations_reference IS NULL)),
    ADD CHECK (operations_action IS NULL OR (action = 'decide' AND operations_reference ~ '^[a-z0-9_]{1,80}$'
        AND operations_action IN ('request:accepted', 'request:quoted', 'request:arranged', 'request:in_progress',
            'request:completed', 'request:user_cancelled', 'request:unavailable', 'request:outcome_unknown',
            'lead:contacted', 'lead:converted', 'lead:closed')));
CREATE TABLE jt_workbench.operations_audit_version (version integer PRIMARY KEY CHECK (version = 3));
INSERT INTO jt_workbench.operations_audit_version VALUES (3);
GRANT SELECT ON jt_workbench.operations_audit_version TO jt_workbench_runtime;
