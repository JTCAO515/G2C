-- local runtime only: original source-bound explicit accept/reject and selected Trip.
CREATE TABLE cj_trip_needs_action (
 scope text NOT NULL,
 action_id text NOT NULL,
 proposal_id text NOT NULL,
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 32768),
 original_action bytea NOT NULL CHECK(octet_length(original_action) BETWEEN 1 AND 32768),
 PRIMARY KEY(scope,action_id),
 FOREIGN KEY(scope,action_id) REFERENCES cj_trip_receipt(scope,action_id),
 FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_needs_basis(scope,proposal_id)
);
CREATE TABLE cj_trip_needs_current (
 scope text NOT NULL,
 needs_scope text NOT NULL,
 needs_id text NOT NULL,
 trip_id text NOT NULL,
 trip_version bigint NOT NULL CHECK(trip_version>0),
 PRIMARY KEY(scope,needs_scope,needs_id),
 FOREIGN KEY(scope,trip_id) REFERENCES cj_trip_record(scope,trip_id),
 FOREIGN KEY(needs_scope,needs_id) REFERENCES cj_needs_record(scope,needs_id)
);
ALTER TABLE cj_trip_needs_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_needs_action FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_needs_action_owner ON cj_trip_needs_action TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
ALTER TABLE cj_trip_needs_current ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_needs_current FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_needs_current_owner ON cj_trip_needs_current TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),'') AND needs_scope=nullif(current_setting('cj.needs_scope',true),''));
GRANT SELECT,INSERT ON cj_trip_needs_action,cj_trip_needs_current TO cj_m1_runtime;
GRANT UPDATE(trip_id,trip_version) ON cj_trip_needs_current TO cj_m1_runtime;

CREATE TABLE cj_trip_needs_edit (
 scope text NOT NULL,
 request_id text NOT NULL,
 proposal_id text NOT NULL,
 trip_id text NOT NULL,
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 1000000),
 original_content bytea NOT NULL CHECK(octet_length(original_content) BETWEEN 1 AND 1000000),
 diff bytea NOT NULL CHECK(octet_length(diff) BETWEEN 1 AND 3000000),
 PRIMARY KEY(scope,request_id), UNIQUE(scope,proposal_id),
 FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_needs_basis(scope,proposal_id),
 FOREIGN KEY(scope,trip_id) REFERENCES cj_trip_record(scope,trip_id)
);
ALTER TABLE cj_trip_needs_edit ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_needs_edit FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_needs_edit_owner ON cj_trip_needs_edit TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
GRANT SELECT,INSERT ON cj_trip_needs_edit TO cj_m1_runtime;

CREATE TABLE cj_trip_needs_plan_context (
 scope text NOT NULL, proposal_id text NOT NULL, trip_id text NOT NULL,
 trip_version bigint NOT NULL CHECK(trip_version>0),
 original_content bytea NOT NULL CHECK(octet_length(original_content) BETWEEN 1 AND 1000000),
 PRIMARY KEY(scope,proposal_id),
 FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_needs_basis(scope,proposal_id),
 FOREIGN KEY(scope,trip_id) REFERENCES cj_trip_record(scope,trip_id)
);
ALTER TABLE cj_trip_needs_plan_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_needs_plan_context FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_needs_plan_context_owner ON cj_trip_needs_plan_context TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
GRANT SELECT,INSERT ON cj_trip_needs_plan_context TO cj_m1_runtime;
