"""Erase a retired employee's credentials while reserving audit references."""
import re
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict


def offboard(connection, username):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", username):
        raise ValueError("explicit workbench username required")
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (0x4A54574F524B,))
        previous = connection.execute("SELECT enabled FROM jt_workbench.accounts WHERE username=%s FOR UPDATE", (username,)).fetchone()
        if previous != (False,):
            raise ValueError("disable the actual workbench account before cleanup")
        connection.execute("DELETE FROM jt_workbench.sessions WHERE username=%s", (username,))
        connection.execute("DELETE FROM jt_workbench.failures WHERE username=%s", (username,))
        connection.execute("""UPDATE jt_workbench.accounts SET password_salt=NULL, password_digest=NULL,
            totp_seed=NULL, last_totp_step=-1, setup_digest=NULL, setup_expires=NULL WHERE username=%s""", (username,))


def main():
    config = conninfo_to_dict(Path("/run/jt-workbench-connection").read_text().strip())
    if (config.get("dbname"), config.get("user"), config.get("host")) != ("jt_workbench", "jt_workbench_owner", "/run/jt-workbench-db"):
        raise ValueError("dedicated workbench owner input required")
    if len(sys.argv) != 2:
        raise ValueError("explicit workbench username required")
    with psycopg.connect(**config, autocommit=True) as connection:
        offboard(connection, sys.argv[1])
    print("WorkBench offboarding complete")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, psycopg.Error):
        print("WorkBench offboarding did not complete", file=sys.stderr)
        raise SystemExit(1) from None
