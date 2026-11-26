"""Re-enroll one approved administrator after restoring a workbench archive offline."""
import json
import re
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from jt.workbench.auth import SETUP_LIFETIME
from jt.workbench.security import new_token, token_digest
from jt.workbench.store import Role


def reissue(connection, admin, roster):
    if (not isinstance(roster, dict) or roster.get(admin) != Role.ADMIN
            or any(not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", name) or not isinstance(role, str) or role not in Role
                   for name, role in roster.items())):
        raise ValueError("explicit approved staff roster and administrator required")
    with connection.transaction():
        if connection.execute("SELECT current_database(), current_user").fetchone() != ("jt_workbench", "jt_workbench_owner"):
            raise ValueError("dedicated workbench owner session required")
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (0x4A54574F524B,))
        active = {name for name, in connection.execute("SELECT username FROM jt_workbench.accounts WHERE enabled")}
        if not roster.keys() <= active:
            raise ValueError("restoration may re-enroll only current staff present and enabled in the archive")
        now, = connection.execute("SELECT EXTRACT(EPOCH FROM clock_timestamp())::double precision").fetchone()
        code = new_token()
        connection.execute("DELETE FROM jt_workbench.sessions")
        connection.execute("DELETE FROM jt_workbench.failures")
        connection.execute("DELETE FROM jt_workbench.attempts")
        connection.execute("""UPDATE jt_workbench.accounts SET enabled=false, password_salt=NULL,
            password_digest=NULL, totp_seed=NULL, last_totp_step=-1, setup_digest=NULL, setup_expires=NULL""")
        for name, role in roster.items():
            connection.execute("UPDATE jt_workbench.accounts SET enabled=true, role=%s WHERE username=%s", (role, name))
        connection.execute("UPDATE jt_workbench.accounts SET setup_digest=%s, setup_expires=%s WHERE username=%s",
                           (token_digest(code), now + SETUP_LIFETIME, admin))
        connection.execute("""INSERT INTO jt_workbench.audit (timestamp, action, result, staff_target)
            VALUES (%s, 'totp_rebind_authorized', 'success', %s)""", (now, admin))
    return code


def main():
    if len(sys.argv) != 2 or not sys.stdout.isatty():
        raise ValueError("use a private interactive terminal with an explicit restored administrator")
    config = conninfo_to_dict(Path("/run/jt-workbench-connection").read_text().strip())
    if (config.get("dbname"), config.get("user"), config.get("host")) != ("jt_workbench", "jt_workbench_owner", "/run/jt-workbench-db"):
        raise ValueError("dedicated workbench owner input required")
    roster = json.loads(Path("/run/jt-workbench-recovery-roster").read_bytes())
    with psycopg.connect(**config, autocommit=True) as connection:
        code = reissue(connection, sys.argv[1], roster)
    print("请私下交给管理员本人。设置码 15 分钟有效，只能使用一次。")
    print(code)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, psycopg.Error):
        print("JT workbench recovery enrollment did not complete", file=sys.stderr)
        raise SystemExit(1) from None
