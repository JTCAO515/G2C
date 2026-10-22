-- UNAPPLIED module design candidate, NOT a registered migration.
-- No grants, roles, policies, runtime connection or identity mapping is supplied.
-- Deployment must supply the existing canonical private-data authority; never
-- bypass RLS to make this candidate runnable.
CREATE TABLE cj_usage_ledger_candidate (
    scope_id text PRIMARY KEY CHECK (length(scope_id) BETWEEN 1 AND 200),
    revision bigint NOT NULL CHECK (revision >= 0),
    format_version integer NOT NULL CHECK (format_version = 1),
    ledger jsonb NOT NULL CHECK (jsonb_typeof(ledger) = 'object')
);
ALTER TABLE cj_usage_ledger_candidate ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_usage_ledger_candidate FORCE ROW LEVEL SECURITY;
REVOKE ALL ON cj_usage_ledger_candidate FROM PUBLIC;

-- Future repository protocol, in ONE short transaction:
-- 1. Under canonical authority, INSERT initial scope row ON CONFLICT DO NOTHING.
-- 2. SELECT revision, format_version, ledger ... WHERE scope_id = $1 FOR UPDATE.
-- 3. Strictly decode/validate version, config, attempts, runs and arithmetic.
-- 4. Apply exactly one Meter transition; UPDATE row and increment revision.
-- 5. COMMIT before returning a claim. Unknown commit ACK => no provider dispatch.
-- Keep external calls outside the transaction. Scope-row lock serializes all
-- runs and attempts sharing the same user's budget, including background work.
-- A missing/malformed/unknown-version row is an error, never reset to empty.
-- Codec, repository implementation, RLS binding, migration registration,
-- retention/cleanup integration and real PostgreSQL verification remain UNRUN.
