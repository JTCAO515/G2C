-- local runtime only: immutable non-acceptable original scoped result bodies.
CREATE TABLE cj_trip_scoped_result (
 scope text NOT NULL, result_id text NOT NULL CHECK(result_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
 message_scope text NOT NULL, run_id text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('clarification_required','expansion_required')),
 original_input bytea NOT NULL CHECK(octet_length(original_input) BETWEEN 1 AND 1048576),
 input_sha256 text NOT NULL CHECK(input_sha256=encode(sha256(original_input),'hex')),
 trip_id text NOT NULL, trip_version bigint NOT NULL CHECK(trip_version>0),
 original_trip bytea NOT NULL CHECK(octet_length(original_trip) BETWEEN 1 AND 1000000),
 scope_input bytea NOT NULL CHECK(octet_length(scope_input) BETWEEN 1 AND 131072),
 needs_input bytea NOT NULL CHECK(octet_length(needs_input) BETWEEN 1 AND 4000000),
 memory_input bytea NOT NULL CHECK(octet_length(memory_input) BETWEEN 1 AND 65536),
 model_input bytea CHECK(octet_length(model_input) BETWEEN 1 AND 1000000),
 explanation bytea NOT NULL CHECK(octet_length(explanation) BETWEEN 1 AND 1000000),
 report bytea CHECK(octet_length(report) BETWEEN 1 AND 1000000),
 PRIMARY KEY(scope,result_id), UNIQUE(message_scope,run_id),
 FOREIGN KEY(message_scope,run_id) REFERENCES cj_message_receipt(scope,run_id),
 FOREIGN KEY(scope,trip_id) REFERENCES cj_trip_record(scope,trip_id),
 CHECK(scope='t'||substr(encode(sha256(convert_to(message_scope,'UTF8')),'hex'),1,40)),
 CHECK((kind='clarification_required' AND model_input IS NULL AND report IS NULL)
    OR (kind='expansion_required' AND model_input IS NOT NULL AND report IS NOT NULL))
);
ALTER TABLE cj_trip_scoped_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE cj_trip_scoped_result FORCE ROW LEVEL SECURITY;
CREATE POLICY cj_trip_scoped_result_owner ON cj_trip_scoped_result TO cj_m1_runtime
 USING(scope=nullif(current_setting('cj.trip_scope',true),''))
 WITH CHECK(scope=nullif(current_setting('cj.trip_scope',true),''));
GRANT SELECT,INSERT ON cj_trip_scoped_result TO cj_m1_runtime;
