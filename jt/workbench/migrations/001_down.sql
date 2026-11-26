-- local runtime only: reject any persisted application data before dropping known tables.
LOCK TABLE jt_workbench.accounts, jt_workbench.failures, jt_workbench.attempts, jt_workbench.sessions,
    jt_workbench.signals, jt_workbench.reviews, jt_workbench.audit IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM jt_workbench.accounts)
        OR EXISTS (SELECT 1 FROM jt_workbench.failures)
        OR EXISTS (SELECT 1 FROM jt_workbench.attempts)
        OR EXISTS (SELECT 1 FROM jt_workbench.sessions)
        OR EXISTS (SELECT 1 FROM jt_workbench.signals)
        OR EXISTS (SELECT 1 FROM jt_workbench.reviews)
        OR EXISTS (SELECT 1 FROM jt_workbench.audit) THEN
        RAISE EXCEPTION 'cannot downgrade a populated workbench database';
    END IF;
END $$;
DROP TABLE jt_workbench.audit, jt_workbench.reviews, jt_workbench.signals,
    jt_workbench.sessions, jt_workbench.attempts, jt_workbench.failures,
    jt_workbench.accounts, jt_workbench.schema_version;
DROP SCHEMA jt_workbench;
