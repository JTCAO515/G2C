-- Task-private candidate for a NEW empty database; NOT a registered migration.
-- Host provisions opaque account scopes; payloads never provision their own owner.
CREATE TABLE cj_needs_scope (scope text PRIMARY KEY);
CREATE TABLE cj_needs_record (
 scope text NOT NULL REFERENCES cj_needs_scope, needs_id text NOT NULL,
 version bigint NOT NULL CHECK (version > 0), content bytea NOT NULL,
 PRIMARY KEY (scope, needs_id)
);
CREATE TABLE cj_needs_revision (
 scope text NOT NULL, needs_id text NOT NULL, version bigint NOT NULL CHECK (version > 0),
 action_id text NOT NULL, operation text NOT NULL CHECK (operation = 'manual_patch'),
 original_input bytea NOT NULL, content bytea NOT NULL,
 source_kind text NOT NULL CHECK (source_kind = 'user_provided'),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (scope, needs_id, version), UNIQUE (scope, operation, action_id),
 FOREIGN KEY (scope, needs_id) REFERENCES cj_needs_record
);
