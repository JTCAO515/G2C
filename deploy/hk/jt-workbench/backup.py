"""Daily JT-only dump with the established private OSS receipt/quota path."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict

from deploy.hk import checkpoint, oss_backup
from deploy.hk.configuration import authorization, load_secret_environment

ROOT = Path("/jt-backups")
DATABASE = "jt_workbench"
OWNER = "jt_workbench_owner"


def export(day, now):
    config = conninfo_to_dict(Path("/run/jt-workbench-connection").read_text().strip())
    if (config.get("dbname"), config.get("user"), config.get("host")) != (DATABASE, OWNER, "/run/jt-workbench-db"):
        raise ValueError("dedicated workbench backup input required")
    path = day / "database.dump"
    manifest = day / "manifest.json"
    if manifest.exists():
        value = json.loads(manifest.read_bytes())
        if value["day"] != day.name or value["database"] != DATABASE or value["sha256"] != oss_backup.checksum(path):
            raise ValueError("original workbench backup differs")
        return value
    scratch = day / "database.tmp"
    if path.exists() or scratch.exists():
        raise ValueError("original workbench export unresolved")
    with scratch.open("xb") as dump:
        handle = subprocess.run(["pg_dump", "--no-password", "--format=custom", DATABASE], stdout=dump,
                                stderr=subprocess.DEVNULL, timeout=60, check=False,
                                env={"PATH": os.environ["PATH"], "PGHOST": config["host"], "PGPORT": "5432", "PGUSER": OWNER,
                                     "PGPASSWORD": config["password"], "PGCONNECT_TIMEOUT": "5"})
        if handle.returncode or dump.tell() == 0:
            raise ValueError("workbench PostgreSQL dump failed")
        dump.flush()
        os.fsync(dump.fileno())
    with scratch.open("rb") as dump:
        subprocess.run(["pg_restore", "--list"], stdin=dump, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=15, check=True, env={"PATH": os.environ["PATH"]})
    scratch.rename(path)
    value = {"version": "jt-workbench-daily.1", "database": DATABASE, "day": day.name,
             "at": now.strftime("%Y%m%dT%H%M%SZ"), "sha256": oss_backup.checksum(path)}
    oss_backup.save(manifest, value)
    return value


def daily():
    load_secret_environment("backup")
    authorization()
    now = dt.datetime.now(dt.timezone.utc)
    day = ROOT / now.strftime("%Y%m%d")
    with checkpoint.lock(ROOT):
        day.mkdir(mode=0o700, exist_ok=True)
        value = export(day, now)
        if (day / "uploaded").exists():
            return
        prefix = f'backups/{value["at"]}-{value["sha256"]}'
        client = oss_backup.client()
        for name in ("database.dump", "manifest.json"):
            oss_backup.upload_file(client, day / name, f"{prefix}/{name}", day / (name + ".receipt.json"))
        (day / "uploaded").touch(mode=0o600, exist_ok=False)


if __name__ == "__main__":
    os.umask(0o077)
    try:
        if sys.argv[1:] != ["daily"]:
            raise ValueError("daily backup operation required")
        daily()
        print("JT workbench backup verified")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, psycopg.Error, oss_backup.oss.exceptions.BaseError):
        print("ALERT jt_workbench_backup_not_confirmed", file=sys.stderr)
        raise SystemExit(1) from None
