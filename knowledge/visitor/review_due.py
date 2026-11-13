"""List valid visitor entries expiring within the next 30 days; no network IO."""
import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from validate import calendar_date, load_entries
from validate_names import load_names
from validate_v2 import load_entries_v2

FORMATS = {
    "legacy": (load_entries, ("id", "topic", "cities", "checked_on", "expires_on", "source_urls")),
    "v2": (load_entries_v2, ("format_version", "id", "topic", "entry_kind", "cities", "subject",
                             "conditions", "checked_on", "expires_on", "source_urls")),
    "names": (load_names, ("format_version", "id", "place_key", "wikidata_qid", "name_zh", "name_en",
                           "cities", "checked_on", "expires_on", "source_urls", "license")),
}


def expiring_entries(entries: list[dict], *, as_of: date) -> list[dict]:
    """Select from the already validated batch, including the thirtieth day."""
    last_day = (as_of + timedelta(days=30)).isoformat()
    return sorted((entry for entry in entries if entry["expires_on"] <= last_day),
                  key=lambda entry: (entry["expires_on"], entry["id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=calendar_date,
                        help="test clock YYYY-MM-DD; default is today's Asia/Shanghai date")
    parser.add_argument("--format", choices=FORMATS, default="legacy",
                        help="explicit record format; default preserves the original eight-field reader")
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    as_of = args.as_of if args.as_of is not None else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    try:
        loader, fields = FORMATS[args.format]
        entries = loader(args.files, as_of=as_of)
    except ValueError as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    due = expiring_entries(entries, as_of=as_of)
    report = {"as_of": as_of.isoformat(), "window_days": 30, "count": len(due),
              "entries": [{key: entry[key] for key in fields} for entry in due]}
    if args.format != "legacy":
        report["record_format"] = args.format
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
