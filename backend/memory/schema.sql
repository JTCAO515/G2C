-- Candidate only: CJ005 owns registration/application. No production migration.
CREATE TABLE cj_memory_scope(scope text PRIMARY KEY, active boolean NOT NULL DEFAULT true, epoch bigint NOT NULL DEFAULT 1 CHECK(epoch>0));
-- Trusted composition inserts exact approved bytes after source ownership, consent,
-- subject, canonical slot, purpose/time/retention checks. No public writer exists.
CREATE TABLE cj_memory_source(
 scope text REFERENCES cj_memory_scope, source_id text, version bigint NOT NULL CHECK(version>0),
 approved_input bytea NOT NULL, authorized boolean NOT NULL, confirmed boolean NOT NULL,
 semantic_resolved boolean NOT NULL, active boolean NOT NULL, expires_at timestamptz NOT NULL,
 PRIMARY KEY(scope,source_id));
CREATE TABLE cj_memory_item(
 scope text REFERENCES cj_memory_scope, item_id text, version bigint NOT NULL CHECK(version>0),
 status text NOT NULL CHECK(status IN ('active','candidate','disabled','withdrawn')),
 subject text NOT NULL, slot text NOT NULL, extent text NOT NULL CHECK(extent IN ('long_term','current')),
 context_id text NOT NULL, source_id text NOT NULL, source_version bigint NOT NULL,
 original_input bytea NOT NULL, recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(scope,item_id), FOREIGN KEY(scope,source_id) REFERENCES cj_memory_source,
 CHECK((extent='long_term' AND context_id='') OR (extent='current' AND context_id<>'')));
CREATE UNIQUE INDEX cj_memory_active_slot ON cj_memory_item(scope,subject,slot,extent,context_id) WHERE status='active';
CREATE TABLE cj_memory_operation(
 scope text REFERENCES cj_memory_scope, operation_id text, original_input bytea NOT NULL,
 item_id text NOT NULL, version bigint NOT NULL, status text NOT NULL,
 PRIMARY KEY(scope,operation_id), FOREIGN KEY(scope,item_id) REFERENCES cj_memory_item);
