"""Build the Pages artifact from the checked-in visitor records, without a data copy in git."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

VISITOR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VISITOR))
from validate import load_records, validate_entry  # noqa: E402
from validate_v2 import validate_entry_v2  # noqa: E402
from validate_v3 import validate_entry_v3  # noqa: E402
from validate_names import validate_name  # noqa: E402

GROUPS = (
    ("entries", validate_entry),
    ("entries-v2", validate_entry_v2),
    ("entries-v3", validate_entry_v3),
    ("names", validate_name),
)


def read_records(visitor: Path, today: date) -> list[dict]:
    """Validate each record's original shape, including records that have since expired."""
    records: list[dict] = []
    seen: set[str] = set()
    for directory, validator in GROUPS:
        paths = sorted((visitor / directory).glob("*.json"))
        if not paths:
            raise ValueError(f"missing {directory} records")

        def validate(record: object) -> None:
            if not isinstance(record, dict):
                raise ValueError("record must be an object")
            checked = date.fromisoformat(record["checked_on"])
            if checked > today:
                raise ValueError("checked_on is in the future")
            # The existing validators enforce expiry at as_of. Validating at the
            # actual checked date preserves all structural/source checks while
            # allowing the UI to mark expired entries instead of treating them as current.
            validator(record, as_of=checked)

        batch = load_records(paths, validate_record=validate)
        for record in batch:
            if record["id"] in seen:
                raise ValueError(f"duplicate record id: {record['id']}")
            seen.add(record["id"])
        records.extend(batch)
    return records


def build(output: Path, *, allow_dirty: bool = False) -> None:
    output = output.resolve()
    if output == VISITOR or VISITOR in output.parents or output in VISITOR.parents:
        raise ValueError("output must be outside the visitor source tree")
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    rows = read_records(VISITOR, today)
    root = VISITOR.parents[1]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    data_sha = subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", *[f"knowledge/visitor/{d}" for d, _ in GROUPS]],
        cwd=root, text=True,
    ).strip()
    source_sha = subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "knowledge/visitor"],
        cwd=root, text=True,
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--",
         *[f"knowledge/visitor/{d}" for d, _ in GROUPS]], cwd=root, text=True,
    ).strip()
    site_dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "knowledge/visitor/site"],
        cwd=root, text=True,
    ).strip()
    if dirty or not data_sha or not source_sha or (site_dirty and not allow_dirty):
        raise ValueError("visitor data and site must be committed before building")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "style.css", "app.mjs", "freshness.mjs"):
        shutil.copyfile(VISITOR / "site" / name, output / name)
    payload = {"revision": sha, "source_revision": source_sha, "data_revision": data_sha, "built_at": now.isoformat(), "preview": bool(site_dirty), "records": rows}
    (output / "data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="build directory outside knowledge/visitor")
    parser.add_argument("--allow-dirty", action="store_true", help="mark a local site preview as unpublished")
    args = parser.parse_args()
    build(args.output, allow_dirty=args.allow_dirty)


if __name__ == "__main__":
    main()
