-- local runtime only: immutable instance identity and readiness metadata, no business data.
CREATE TABLE cj.deployment_identity (
 singleton boolean PRIMARY KEY CHECK(singleton),
 lineage uuid NOT NULL DEFAULT gen_random_uuid(),
 instance uuid NOT NULL DEFAULT gen_random_uuid()
);
INSERT INTO cj.deployment_identity(singleton) VALUES(true);
REVOKE ALL ON cj.deployment_identity FROM PUBLIC;
GRANT USAGE ON SCHEMA cj TO cj_m1_runtime;
GRANT SELECT ON cj.schema_migrations,cj.deployment_identity TO cj_m1_runtime;
