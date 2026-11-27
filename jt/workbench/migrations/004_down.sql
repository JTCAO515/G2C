-- local runtime only: 001_down still guards a full rollback against persisted data.
-- Narrow the audit vocabulary back. Refuses while rows written by the password-only version exist.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM jt_workbench.audit WHERE action IN ('account_enabled', 'account_deleted', 'password_reset')) THEN
        RAISE EXCEPTION 'cannot narrow audit actions while password-only audit rows exist';
    END IF;
END $$;
DO $$
DECLARE
    old_check text;
BEGIN
    FOR old_check IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'jt_workbench.audit'::regclass AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%''login_failed''%'
    LOOP
        EXECUTE format('ALTER TABLE jt_workbench.audit DROP CONSTRAINT %I', old_check);
    END LOOP;
END $$;
ALTER TABLE jt_workbench.audit ADD CONSTRAINT audit_action_check CHECK (action IN (
    'login', 'login_failed', 'logout', 'account_created', 'account_disabled', 'account_unlocked',
    'role_changed', 'totp_bound', 'totp_rebind_authorized', 'view', 'annotate', 'export', 'reveal', 'decide'
));
DROP TABLE jt_workbench.password_auth_version;
