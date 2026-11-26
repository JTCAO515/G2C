"""Provision just the workbench database from the PG container using private stdin."""
import json
import sys
from pathlib import Path

import psycopg
from psycopg import sql

DATABASE = "jt_workbench"
OWNER = "jt_workbench_owner"
RUNTIME = "jt_workbench_runtime"
ROLES = (OWNER, RUNTIME)


def operator():
    for line in Path("/local-pg/local-db.env").read_text().splitlines():
        name, _, value = line.partition("=")
        if name == "CJ_SUPABASE_OPERATOR_URI":
            return psycopg.connect(value, autocommit=True)
    raise RuntimeError("local database operator unavailable")


def provision(passwords):
    if set(passwords) != set(ROLES) or any(not isinstance(value, str) or len(value) < 40 for value in passwords.values()):
        raise ValueError("invalid private workbench connection input")
    with operator() as db:
        if db.execute("SELECT current_database(), current_setting('is_superuser')").fetchone() != ("postgres", "on"):
            raise RuntimeError("local PostgreSQL operator required")
        if db.execute("SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL").fetchone() != (0,):
            raise RuntimeError("PostgreSQL rejected a new authentication rule")
        expected = [(DATABASE, list(ROLES), "scram-sha-256"), ("all", list(ROLES), "reject")]
        rules = db.execute("SELECT database, user_name, auth_method FROM pg_hba_file_rules WHERE user_name=%s ORDER BY rule_number", (list(ROLES),)).fetchall()
        if rules != [([name], roles, method) for name, roles, method in expected]:
            raise RuntimeError("workbench PostgreSQL authentication scope could not be verified")
        with db.transaction():
            db.execute("SET LOCAL log_statement = 'none'")
            db.execute("SET LOCAL log_min_error_statement = 'panic'")
            for role in ROLES:
                identity = sql.Identifier(role)
                verifier = db.pgconn.encrypt_password(passwords[role].encode(), role.encode(), b"scram-sha-256").decode()
                present = db.execute("SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
                if present is None:
                    db.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}").format(identity, sql.Literal(verifier)))
                elif present != (True,) + (False,) * 6 or db.execute("SELECT 1 FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname=%s)", (role,)).fetchone():
                    raise RuntimeError("unexpected privileges on an existing workbench role")
        existing = db.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (DATABASE,)).fetchone()
        if existing is None:
            db.execute("CREATE DATABASE jt_workbench WITH OWNER jt_workbench_owner ALLOW_CONNECTIONS false")
        elif existing != (OWNER,):
            raise RuntimeError("unexpected workbench database owner")
        db.execute("REVOKE ALL ON DATABASE jt_workbench FROM PUBLIC")
        db.execute("GRANT CONNECT ON DATABASE jt_workbench TO jt_workbench_runtime")
        db.execute("ALTER DATABASE jt_workbench ALLOW_CONNECTIONS true")
        db.execute("SELECT pg_reload_conf()")


if __name__ == "__main__":
    try:
        provision(json.load(sys.stdin))
    except (psycopg.Error, OSError, ValueError, RuntimeError):
        print("JT workbench database provisioning failed; see private service state", file=sys.stderr)
        raise SystemExit(1) from None
