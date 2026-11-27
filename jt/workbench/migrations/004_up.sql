-- #1886: staff sign in with username and password only (JT decision 2026-11-27, second factor removed).
-- Runs as jt_workbench_owner inside the single migrate transaction; every statement is safe to repeat.

-- 1. Audit vocabulary: account management now records enable, delete and password reset.
--    Historical totp_* actions stay valid so existing audit rows remain readable.
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
    'role_changed', 'totp_bound', 'totp_rebind_authorized', 'view', 'annotate', 'export', 'reveal', 'decide',
    'account_enabled', 'account_deleted', 'password_reset'
));

-- 2. Retire half-finished accounts. Before this change an account had no password until its owner finished
--    the authenticator setup page; none of those can ever sign in now. Remove sessions, failures and setup
--    grants. The row itself is deleted when no audit or review record refers to it, otherwise it stays as a
--    disabled, credential-free tombstone that keeps the username reserved and the audit trail intact.
DELETE FROM jt_workbench.sessions
    WHERE username IN (SELECT username FROM jt_workbench.accounts WHERE password_digest IS NULL);
DELETE FROM jt_workbench.failures
    WHERE username IN (SELECT username FROM jt_workbench.accounts WHERE password_digest IS NULL);
UPDATE jt_workbench.accounts SET enabled = false WHERE password_digest IS NULL AND enabled;
DELETE FROM jt_workbench.accounts a
    WHERE a.password_digest IS NULL
      AND NOT EXISTS (SELECT 1 FROM jt_workbench.audit x WHERE x.actor = a.username OR x.staff_target = a.username)
      AND NOT EXISTS (SELECT 1 FROM jt_workbench.reviews r WHERE r.actor = a.username);

-- 3. No authenticator material is kept: seeds, replay counters and one-time setup grants are cleared.
UPDATE jt_workbench.accounts SET totp_seed = NULL, last_totp_step = -1, setup_digest = NULL, setup_expires = NULL
    WHERE totp_seed IS NOT NULL OR last_totp_step <> -1 OR setup_digest IS NOT NULL OR setup_expires IS NOT NULL;

-- 4. Version marker, readable by the runtime role. The previous application version ignores it.
CREATE TABLE IF NOT EXISTS jt_workbench.password_auth_version (version integer PRIMARY KEY CHECK (version = 4));
INSERT INTO jt_workbench.password_auth_version VALUES (4) ON CONFLICT DO NOTHING;
GRANT SELECT ON jt_workbench.password_auth_version TO jt_workbench_runtime;
