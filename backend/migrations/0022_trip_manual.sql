-- local runtime only: C-owned structured manual basis and original save intent.
-- Trip records, candidates and receipts continue through the existing sole act.
CREATE TABLE cj_trip_manual_basis (
    scope text NOT NULL,
    request_id text NOT NULL CHECK (request_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
    proposal_id text NOT NULL,
    original_input bytea NOT NULL CHECK (octet_length(original_input) BETWEEN 1 AND 1000000),
    original_content bytea NOT NULL CHECK (octet_length(original_content) BETWEEN 1 AND 1000000),
    diff bytea NOT NULL CHECK (octet_length(diff) BETWEEN 1 AND 3000000),
    PRIMARY KEY(scope,request_id),
    UNIQUE(scope,proposal_id),
    FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_proposal(scope,proposal_id) ON DELETE RESTRICT
);
CREATE TABLE cj_trip_manual_intent (
    scope text NOT NULL,
    action_id text NOT NULL,
    proposal_id text NOT NULL,
    original_input bytea NOT NULL CHECK (octet_length(original_input) BETWEEN 1 AND 32768),
    original_action bytea NOT NULL CHECK (octet_length(original_action) BETWEEN 1 AND 32768),
    PRIMARY KEY(scope,action_id),
    FOREIGN KEY(scope,proposal_id) REFERENCES cj_trip_manual_basis(scope,proposal_id) ON DELETE RESTRICT,
    FOREIGN KEY(scope,action_id) REFERENCES cj_trip_receipt(scope,action_id) ON DELETE RESTRICT
);
ALTER TABLE cj_trip_manual_basis ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_manual_basis FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_manual_scope ON cj_trip_manual_basis TO cj_m1_runtime
    USING (scope=nullif(current_setting('cj.trip_scope',true),''))
    WITH CHECK (scope=nullif(current_setting('cj.trip_scope',true),''));
ALTER TABLE cj_trip_manual_intent ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_manual_intent FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_manual_scope ON cj_trip_manual_intent TO cj_m1_runtime
    USING (scope=nullif(current_setting('cj.trip_scope',true),''))
    WITH CHECK (scope=nullif(current_setting('cj.trip_scope',true),''));
GRANT SELECT,INSERT ON cj_trip_manual_basis,cj_trip_manual_intent TO cj_m1_runtime;
