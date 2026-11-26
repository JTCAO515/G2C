"""List visitor entries expiring within the next 30 days and those already expired; no network IO.

Expired entries are listed (#1757), not rejected: the review tool exists to find them. Every
other format rule still applies, so a malformed file still fails with exit code 1. Listing an
expired entry grants it nothing; readers keep refusing it from its expires_on day.
"""
import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from validate import calendar_date, load_entries, load_records, validate_entry
from validate_names import check_unique_names, load_names, validate_name
from validate_v2 import load_entries_v2, validate_entry_v2
from validate_v3 import load_entries_v3, validate_entry_v3

FORMATS = {
    "legacy": (load_entries, ("id", "topic", "cities", "checked_on", "expires_on", "source_urls")),
    "v2": (load_entries_v2, ("format_version", "id", "topic", "entry_kind", "cities", "subject",
                             "conditions", "checked_on", "expires_on", "source_urls")),
    "names": (load_names, ("format_version", "id", "place_key", "wikidata_qid", "name_zh", "name_en",
                           "cities", "checked_on", "expires_on", "source_urls", "license")),
}

FORMATS["v3"] = (load_entries_v3, FORMATS["v2"][1])

VALIDATORS = {"legacy": validate_entry, "v2": validate_entry_v2, "v3": validate_entry_v3, "names": validate_name}


def load_for_review(record_format: str, paths: list[Path], *, as_of: date) -> list[dict]:
    """The format's own loader rules, except that an expired entry is kept for the report.

    An entry whose expires_on is on or before as_of is validated as of its last valid day, so
    every other rule (shape, sources, checked_on before expires_on) still applies to it.
    """
    validator = VALIDATORS[record_format]

    def check(entry: object) -> None:
        day = as_of
        if isinstance(entry, dict):
            try:
                expires = calendar_date(entry.get("expires_on"))
            except ValueError:
                expires = None
            if expires is not None and expires <= as_of:
                day = expires - timedelta(days=1)
        validator(entry, as_of=day)

    records = load_records(paths, validate_record=check)
    if record_format == "names":
        check_unique_names(records)
    return records


def expired_entries(entries: list[dict], *, as_of: date) -> list[dict]:
    """Entries no reader may return on as_of: expires_on is that day or earlier."""
    return sorted((entry for entry in entries if entry["expires_on"] <= as_of.isoformat()),
                  key=lambda entry: (entry["expires_on"], entry["id"]))


def expiring_entries(entries: list[dict], *, as_of: date) -> list[dict]:
    """Entries still valid on as_of that expire within 30 days, including the thirtieth day."""
    first_day, last_day = as_of.isoformat(), (as_of + timedelta(days=30)).isoformat()
    return sorted((entry for entry in entries if first_day < entry["expires_on"] <= last_day),
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
        fields = FORMATS[args.format][1]
        entries = load_for_review(args.format, args.files, as_of=as_of)
    except ValueError as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    due = expiring_entries(entries, as_of=as_of)
    expired = expired_entries(entries, as_of=as_of)
    report = {"as_of": as_of.isoformat(), "window_days": 30, "count": len(due),
              "entries": [{key: entry[key] for key in fields} for entry in due],
              "expired_count": len(expired),
              "expired": [{key: entry[key] for key in fields} for entry in expired]}
    if args.format != "legacy":
        report["record_format"] = args.format
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
