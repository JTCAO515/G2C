-- Task-private empty PostgreSQL only; not a production migration or RLS policy.
CREATE TABLE cj_trip_scope (scope text PRIMARY KEY);
CREATE TABLE cj_trip_proposal (
 scope text NOT NULL REFERENCES cj_trip_scope, proposal_id text NOT NULL,
 trip_id text NOT NULL, expected_version bigint NOT NULL CHECK(expected_version >= 0),
 basis_version text NOT NULL, expires_at bigint NOT NULL, content bytea NOT NULL,
 candidate_hash text NOT NULL, status text NOT NULL CHECK(status IN ('pending','accepted','rejected','expired','superseded')),
 PRIMARY KEY(scope,proposal_id)
);
CREATE TABLE cj_trip_record (
 scope text NOT NULL REFERENCES cj_trip_scope, trip_id text NOT NULL,
 version bigint NOT NULL CHECK(version > 0), content bytea NOT NULL,
 PRIMARY KEY(scope,trip_id)
);
CREATE TABLE cj_trip_receipt (
 scope text NOT NULL, action_id text NOT NULL, kind text NOT NULL CHECK(kind IN ('accept','reject')),
 proposal_id text NOT NULL, candidate_hash text NOT NULL, trip_id text NOT NULL,
 committed_version bigint, original_input bytea NOT NULL,
 PRIMARY KEY(scope,action_id), FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_proposal,
 CHECK ((kind='accept' AND committed_version IS NOT NULL AND committed_version > 0) OR (kind='reject' AND committed_version IS NULL))
);
