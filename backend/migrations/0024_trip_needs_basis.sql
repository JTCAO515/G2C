-- local runtime only: immutable C-owned original NEEDS/RUN candidate basis.
CREATE TABLE cj_trip_needs_basis (
 scope text NOT NULL,
 proposal_id text NOT NULL,
 message_scope text NOT NULL,
 run_id text NOT NULL,
 needs_scope text NOT NULL,
 needs_id text NOT NULL,
 needs_version bigint NOT NULL CHECK(needs_version>0),
 source_input bytea NOT NULL CHECK(octet_length(source_input) BETWEEN 1 AND 4000000),
 source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
 proposed_input bytea NOT NULL CHECK(octet_length(proposed_input) BETWEEN 1 AND 131072),
 PRIMARY KEY(scope,proposal_id),
 FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_proposal(scope,proposal_id) ON DELETE RESTRICT,
 FOREIGN KEY(message_scope,run_id) REFERENCES cj_message_receipt(scope,run_id) ON DELETE RESTRICT,
 FOREIGN KEY(needs_scope,needs_id,needs_version) REFERENCES cj_needs_revision(scope,needs_id,version) ON DELETE RESTRICT,
 CHECK(scope='t'||substr(encode(sha256(convert_to(message_scope,'UTF8')),'hex'),1,40)),
 CHECK(needs_scope='n'||encode(sha256(convert_to(message_scope,'UTF8')),'hex'))
);
ALTER TABLE cj_trip_needs_basis ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_needs_basis FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_needs_scope ON cj_trip_needs_basis TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
GRANT SELECT,INSERT ON cj_trip_needs_basis TO cj_m1_runtime;
