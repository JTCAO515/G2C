"""Validate visitor content files at the deserialization boundary; no network IO."""
import argparse
from datetime import date, datetime
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from cj_strict_json import reject_duplicates

TOPICS = frozenset({"payment", "passport_booking", "transport", "internet", "emergency"})
CITIES = frozenset({"beijing", "chengdu", "xian", "shanghai", "hangzhou", "chongqing", "shenzhen"})
FIELDS = frozenset({"id", "topic", "cities", "text_zh", "text_en", "source_urls", "checked_on", "expires_on"})


def calendar_date(value: str) -> date:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


def nonblank(value: object) -> bool:
    return (isinstance(value, str) and bool(value.strip())
            and not any(0xD800 <= ord(ch) <= 0xDFFF for ch in value))


def https_url(value: str) -> bool:
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not parsed.fragment and parsed.port in (None, 443))
    except ValueError:
        return False


def validate_entry(entry: object, *, as_of: date) -> None:
    if not isinstance(entry, dict) or entry.keys() != FIELDS:
        raise ValueError("entry must have exactly the documented fields")
    if not isinstance(entry["id"], str) or re.fullmatch(r"visitor\.[a-z0-9][a-z0-9.-]*", entry["id"]) is None:
        raise ValueError("invalid id")
    if not isinstance(entry["topic"], str) or entry["topic"] not in TOPICS:
        raise ValueError("invalid topic")
    for field in ("text_zh", "text_en"):
        if not nonblank(entry[field]):
            raise ValueError(f"{field} must be nonblank text")
    for field in ("cities", "source_urls"):
        values = entry[field]
        if (not isinstance(values, list) or not values
                or any(not nonblank(value) for value in values)):
            raise ValueError(f"{field} must be a nonempty text array")
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {field}")
    if any(city not in CITIES for city in entry["cities"]):
        raise ValueError("invalid city")
    if any(not https_url(url) for url in entry["source_urls"]):
        raise ValueError("invalid source URL")
    checked = calendar_date(entry["checked_on"])
    expires = calendar_date(entry["expires_on"])
    if checked > as_of:
        raise ValueError("checked_on is in the future")
    if expires <= checked:
        raise ValueError("expires_on must follow checked_on")
    if expires <= as_of:
        raise ValueError("entry has expired")


def reject_constant(_: str) -> None:
    raise ValueError("non-finite JSON value")


def load_entries(paths: list[Path], *, as_of: date) -> list[dict]:
    """Read and validate the whole batch once; return only validated entries."""
    entries = []
    ids = set()
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"),
                                 object_pairs_hook=reject_duplicates(ValueError, "duplicate JSON key"),
                                 parse_constant=reject_constant)
            if not isinstance(payload, list) or not payload:
                raise ValueError("file must be a nonempty entry array")
            for index, entry in enumerate(payload):
                try:
                    validate_entry(entry, as_of=as_of)
                    if entry["id"] in ids:
                        raise ValueError("duplicate id in batch")
                except ValueError as exc:
                    raise ValueError(f"entry {index}: {exc}") from exc
                ids.add(entry["id"])
                entries.append(entry)
        except (OSError, ValueError) as exc:
            raise ValueError(f"{path}: {exc}") from exc
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=calendar_date,
                        help="test clock YYYY-MM-DD; default is today's Asia/Shanghai date")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    as_of = args.as_of if args.as_of is not None else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    try:
        entries = load_entries(args.files, as_of=as_of)
    except ValueError as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print(f"PASS: {len(entries)} entries; as_of={as_of.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
