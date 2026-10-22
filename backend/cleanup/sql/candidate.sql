-- Candidate metadata only. Apply solely to an explicitly authorized new empty database.
-- No business/account/auth tables, no role or policy changes.
CREATE TABLE cj_cleanup_journal_candidate (
    scope_bytes bytea PRIMARY KEY,
    operation_id text NOT NULL,
    revision bigint NOT NULL CHECK (revision >= 0),
    journal_bytes bytea NOT NULL,
    state_bytes bytea NOT NULL,
    CHECK (octet_length(scope_bytes) > 0),
    CHECK (length(operation_id) BETWEEN 1 AND 160)
);
