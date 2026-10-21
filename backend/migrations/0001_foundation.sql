-- PostgreSQL entry point; no user/business tables or old-data migration.
BEGIN;
CREATE SCHEMA cj;
CREATE TABLE cj.schema_migrations (
    version integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO cj.schema_migrations(version) VALUES (1);
COMMIT;
