"""Create and verify a private JT-only PostgreSQL dump after the daily backup."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from psycopg.conninfo import conninfo_to_dict

ROOT = Path("/jt-backups")
DATABASE = "jt_workbench"
OWNER = "jt_workbench_owner"
SOCKET = "/run/jt-workbench-db"


def checksum(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def daily():
    config = conninfo_to_dict(Path("/run/jt-workbench-connection").read_text().strip())
    if (config.get("dbname"), config.get("user"), config.get("host")) != (DATABASE, OWNER, SOCKET):
        raise ValueError("dedicated workbench backup input required")
    today = dt.datetime.now(dt.timezone.utc).date()
    target = ROOT / today.isoformat()
    dump, manifest = target / "database.dump", target / "manifest.json"
    if target.exists():
        value = json.loads(manifest.read_bytes())
        if value != {"database": DATABASE, "day": today.isoformat(), "sha256": checksum(dump)}:
            raise ValueError("original workbench backup differs")
        return
    child = {"PATH": os.environ["PATH"], "PGHOST": SOCKET, "PGPORT": "5432", "PGUSER": OWNER,
             "PGPASSWORD": config["password"], "PGCONNECT_TIMEOUT": "5"}
    with tempfile.TemporaryDirectory(prefix=".jt-export-", dir=ROOT) as directory:
        scratch = Path(directory) / "export"
        scratch.mkdir(mode=0o700)
        exported = scratch / dump.name
        with exported.open("xb") as data:
            subprocess.run(["pg_dump", "--no-password", "--format=custom", DATABASE], stdout=data,
                           stderr=subprocess.DEVNULL, timeout=60, check=True, env=child)
            data.flush()
            os.fsync(data.fileno())
        with exported.open("rb") as data:
            subprocess.run(["pg_restore", "--list"], stdin=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=15, check=True, env={"PATH": os.environ["PATH"]})
        with (scratch / manifest.name).open("x") as output:
            json.dump({"database": DATABASE, "day": today.isoformat(), "sha256": checksum(exported)}, output)
            output.flush()
            os.fsync(output.fileno())
        scratch.rename(target)
        for path in (target, ROOT):
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


if __name__ == "__main__":
    os.umask(0o077)
    try:
        daily()
        print("JT workbench backup verified")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("ALERT jt_workbench_backup_not_confirmed", file=sys.stderr)
        raise SystemExit(1) from None
