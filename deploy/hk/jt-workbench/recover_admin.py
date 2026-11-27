"""Restore access after a workbench archive was restored offline: reset every credential, then set one approved
administrator's new password from a private interactive terminal. Nothing secret is printed, logged or passed as an
argument."""
import json
import re
import sys
import warnings
from getpass import GetPassWarning, getpass
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from jt.workbench.security import PasswordHash, valid_password
from jt.workbench.store import Role


def recover(connection, admin, roster, password):
    if (not isinstance(roster, dict) or roster.get(admin) != Role.ADMIN
            or any(not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", name) or not isinstance(role, str) or role not in Role
                   for name, role in roster.items())):
        raise ValueError("explicit approved staff roster and administrator required")
    if not valid_password(password):
        raise ValueError("administrator password must be 12 to 128 characters")
    digest = PasswordHash.make(password)
    with connection.transaction():
        if connection.execute("SELECT current_database(), current_user").fetchone() != ("jt_workbench", "jt_workbench_owner"):
            raise ValueError("dedicated workbench owner session required")
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (0x4A54574F524B,))
        active = {name for name, in connection.execute("SELECT username FROM jt_workbench.accounts WHERE enabled")}
        if not roster.keys() <= active:
            raise ValueError("restoration may re-enroll only current staff present and enabled in the archive")
        now, = connection.execute("SELECT EXTRACT(EPOCH FROM clock_timestamp())::double precision").fetchone()
        connection.execute("DELETE FROM jt_workbench.sessions")
        connection.execute("DELETE FROM jt_workbench.failures")
        connection.execute("DELETE FROM jt_workbench.attempts")
        connection.execute("""UPDATE jt_workbench.accounts SET enabled=false, password_salt=NULL,
            password_digest=NULL, totp_seed=NULL, last_totp_step=-1, setup_digest=NULL, setup_expires=NULL""")
        for name, role in roster.items():
            connection.execute("UPDATE jt_workbench.accounts SET enabled=true, role=%s WHERE username=%s", (role, name))
        connection.execute("UPDATE jt_workbench.accounts SET password_salt=%s, password_digest=%s WHERE username=%s",
                           (digest.salt, digest.digest, admin))
        connection.execute("""INSERT INTO jt_workbench.audit (timestamp, action, result, staff_target)
            VALUES (%s, 'password_reset', 'success', %s)""", (now, admin))


def read_password():
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        password = getpass("恢复管理员的新密码（至少 12 位）：")
        if getpass("再次输入密码：") != password:
            raise ValueError("passwords do not match")
    return password


def main():
    if len(sys.argv) != 2 or not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("use a private interactive terminal with an explicit restored administrator")
    config = conninfo_to_dict(Path("/run/jt-workbench-connection").read_text().strip())
    if (config.get("dbname"), config.get("user"), config.get("host")) != ("jt_workbench", "jt_workbench_owner", "/run/jt-workbench-db"):
        raise ValueError("dedicated workbench owner input required")
    roster = json.loads(Path("/run/jt-workbench-recovery-roster").read_bytes())
    password = read_password()
    with psycopg.connect(**config, autocommit=True) as connection:
        recover(connection, sys.argv[1], roster, password)
    print("管理员密码已重设。名单内其他员工需由管理员在「用户管理」页逐一重设密码后才能登录。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, GetPassWarning, psycopg.Error):
        print("JT workbench recovery did not complete", file=sys.stderr)
        raise SystemExit(1) from None
