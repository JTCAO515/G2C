-- local runtime only: earlier down migrations still guard all stored data.
ALTER TABLE jt_workbench.audit DROP COLUMN operations_action, DROP COLUMN operations_reference;
DROP TABLE jt_workbench.operations_audit_version;
