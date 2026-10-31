-- local runtime only: immutable scoped candidate source/diff and original action.
CREATE TABLE cj_trip_scoped_basis (
 scope text NOT NULL, proposal_id text NOT NULL, message_scope text NOT NULL, run_id text NOT NULL,
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 1048576),
 original_trip bytea NOT NULL CHECK(octet_length(original_trip) BETWEEN 1 AND 1000000),
 scope_input bytea NOT NULL CHECK(octet_length(scope_input) BETWEEN 1 AND 131072),
 needs_input bytea NOT NULL CHECK(octet_length(needs_input) BETWEEN 1 AND 4000000),
 memory_input bytea NOT NULL CHECK(octet_length(memory_input) BETWEEN 1 AND 65536),
 model_input bytea NOT NULL CHECK(octet_length(model_input) BETWEEN 1 AND 1000000),
 diff bytea NOT NULL CHECK(octet_length(diff) BETWEEN 1 AND 3000000),
 report bytea NOT NULL CHECK(octet_length(report) BETWEEN 1 AND 1000000),
 PRIMARY KEY(scope,proposal_id), UNIQUE(message_scope,run_id),
 FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_proposal(scope,proposal_id),
 FOREIGN KEY(message_scope,run_id) REFERENCES cj_message_receipt(scope,run_id),
 CHECK(scope='t'||substr(encode(sha256(convert_to(message_scope,'UTF8')),'hex'),1,40))
);
CREATE TABLE cj_trip_scoped_action (
 scope text NOT NULL, action_id text NOT NULL, proposal_id text NOT NULL,
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 32768),
 original_action bytea NOT NULL CHECK(octet_length(original_action) BETWEEN 1 AND 32768),
 PRIMARY KEY(scope,action_id),
 FOREIGN KEY(scope,action_id) REFERENCES cj_trip_receipt(scope,action_id),
 FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_scoped_basis(scope,proposal_id)
);
ALTER TABLE cj_trip_scoped_basis ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_scoped_basis FORCE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_scoped_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_scoped_action FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_scoped_basis_owner ON cj_trip_scoped_basis TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),'')) WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
CREATE POLICY cj_trip_scoped_action_owner ON cj_trip_scoped_action TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),'')) WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
GRANT SELECT,INSERT ON cj_trip_scoped_basis,cj_trip_scoped_action TO cj_m1_runtime;
