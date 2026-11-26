-- local runtime only for #1885 validation; apply to the dedicated workbench database.
CREATE SCHEMA jt_workbench;
REVOKE ALL ON SCHEMA jt_workbench FROM PUBLIC;
CREATE TABLE jt_workbench.schema_version (version integer PRIMARY KEY CHECK (version = 1));
INSERT INTO jt_workbench.schema_version VALUES (1);

CREATE TABLE jt_workbench.accounts (
    username text PRIMARY KEY CHECK (username ~ '^[a-z][a-z0-9_-]{2,31}$'),
    role text NOT NULL CHECK (role IN ('admin', 'operator', 'reviewer')),
    password_salt bytea CHECK (octet_length(password_salt) = 16),
    password_digest bytea CHECK (octet_length(password_digest) = 64),
    totp_seed bytea CHECK (octet_length(totp_seed) = 20),
    last_totp_step bigint NOT NULL CHECK (last_totp_step >= -1),
    setup_digest bytea CHECK (octet_length(setup_digest) = 32),
    setup_expires double precision,
    enabled boolean NOT NULL,
    CHECK ((password_salt IS NULL) = (password_digest IS NULL)),
    CHECK ((setup_digest IS NULL) = (setup_expires IS NULL))
);
CREATE TABLE jt_workbench.failures (
    username text PRIMARY KEY REFERENCES jt_workbench.accounts (username),
    count integer NOT NULL CHECK (count >= 0),
    expires double precision NOT NULL
);
CREATE TABLE jt_workbench.attempts (attempted_at double precision NOT NULL);
CREATE INDEX attempts_time_idx ON jt_workbench.attempts (attempted_at);

CREATE TABLE jt_workbench.sessions (
    digest bytea PRIMARY KEY CHECK (octet_length(digest) = 32),
    username text NOT NULL REFERENCES jt_workbench.accounts (username),
    role text NOT NULL CHECK (role IN ('admin', 'operator', 'reviewer')),
    csrf text NOT NULL CHECK (csrf ~ '^[A-Za-z0-9_-]{43}$'),
    expires_at double precision NOT NULL,
    idle_until double precision NOT NULL CHECK (idle_until <= expires_at)
);
CREATE INDEX sessions_staff_idx ON jt_workbench.sessions (username);

CREATE TABLE jt_workbench.signals (
    signal_id text PRIMARY KEY,
    reference text UNIQUE NOT NULL CHECK (reference ~ '^[A-Za-z0-9_-]{43}$'),
    payload jsonb NOT NULL CHECK (payload->>'signal_id' IS NOT DISTINCT FROM signal_id),
    due_at timestamptz NOT NULL,
    case_id uuid
);
CREATE TABLE jt_workbench.reviews (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference text NOT NULL REFERENCES jt_workbench.signals (reference),
    actual_severity text CHECK (actual_severity IN ('P0', 'P1', 'P2', 'P3', 'P4')),
    false_positive boolean NOT NULL,
    missed boolean NOT NULL,
    note text NOT NULL CHECK (char_length(note) <= 500),
    actor text NOT NULL REFERENCES jt_workbench.accounts (username),
    recorded_at timestamptz NOT NULL,
    CHECK ((actual_severity IS NULL) = false_positive AND NOT (false_positive AND missed))
);
CREATE INDEX reviews_signal_idx ON jt_workbench.reviews (reference, id);

CREATE TABLE jt_workbench.audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    timestamp double precision NOT NULL,
    action text NOT NULL CHECK (action IN (
        'login', 'login_failed', 'logout', 'account_created', 'account_disabled', 'account_unlocked',
        'role_changed', 'totp_bound', 'totp_rebind_authorized', 'view', 'annotate', 'export', 'reveal', 'decide'
    )),
    actor text REFERENCES jt_workbench.accounts (username),
    case_id uuid,
    result text NOT NULL CHECK (result IN ('success', 'denied')),
    staff_target text REFERENCES jt_workbench.accounts (username),
    signal_reference text REFERENCES jt_workbench.signals (reference)
);

GRANT USAGE ON SCHEMA jt_workbench TO jt_workbench_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA jt_workbench TO jt_workbench_runtime;
GRANT INSERT ON jt_workbench.accounts, jt_workbench.failures, jt_workbench.attempts,
    jt_workbench.sessions, jt_workbench.signals, jt_workbench.reviews, jt_workbench.audit TO jt_workbench_runtime;
GRANT UPDATE (role, password_salt, password_digest, totp_seed, last_totp_step, setup_digest, setup_expires, enabled)
    ON jt_workbench.accounts TO jt_workbench_runtime;
GRANT UPDATE (count, expires) ON jt_workbench.failures TO jt_workbench_runtime;
GRANT UPDATE (idle_until) ON jt_workbench.sessions TO jt_workbench_runtime;
GRANT DELETE ON jt_workbench.sessions, jt_workbench.attempts TO jt_workbench_runtime;
