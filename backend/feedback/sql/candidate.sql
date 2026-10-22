-- CJ023 private empty PostgreSQL only. CJ005 owns formal migration, privileges/RLS.
-- No authenticated/browser role grants and no cross-domain foreign keys or SQL.
CREATE TABLE cj_feedback_action (
 scope text NOT NULL,
 operation text NOT NULL CHECK (operation = 'submit'),
 action_id text NOT NULL,
 original_input bytea NOT NULL CHECK (octet_length(original_input) BETWEEN 1 AND 16384),
 input_sha256 text NOT NULL CHECK (length(input_sha256) = 64),
 source_reference jsonb CHECK (source_reference IS NULL OR jsonb_typeof(source_reference) = 'object'),
 submitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope, operation, action_id)
);
REVOKE ALL ON cj_feedback_action FROM PUBLIC;
