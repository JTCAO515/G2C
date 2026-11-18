"""Validate round-2 POI increments against the round-1 baseline; no network IO."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_seven_city_poi import (  # noqa: E402
    CITY_PREFIX, CITIES, FIELDS, STATUS, SUBCATEGORIES, SOURCE_TYPES,
    parse_date, valid_url, validate_row,
)

ENRICH_FIELDS = [
    "row_id", "city", "field", "old_value", "new_value", "source_name",
    "source_type", "source_url", "collected_on", "notes",
]
ENRICHABLE = frozenset({
    "district", "subcategory", "address_zh", "branch_name", "brand_or_parent",
    "attraction_level", "cuisine", "signature_dishes", "accommodation_type",
    "venue_type", "nearest_metro", "official_website", "name_en", "name_en_type",
    "name_en_source_url", "name_zh_alt", "notes",
})
ROW_ID = re.compile(r"(BJ|SH|GZ|SZ|CD|CQ|GL)-[0-9]{4}")


def load_csv(path: Path, fields: list[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != fields:
            raise ValueError(f"{path.name}: header must exactly match the documented columns")
        rows = [dict(r) for r in reader]
    if not rows:
        raise ValueError(f"{path.name}: no rows")
    return rows


def validate_new(path: Path, baseline_ids: set[str], *, as_of: date) -> list[dict[str, str]]:
    rows = load_csv(path, FIELDS)
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        validate_row(row, as_of=as_of, source=f"{path.name}:{index}")
        if row["row_id"] in baseline_ids:
            raise ValueError(f"{path.name}:{index}: row_id {row['row_id']} already exists in round 1")
        if row["row_id"] in seen:
            raise ValueError(f"{path.name}:{index}: duplicate row_id {row['row_id']}")
        seen.add(row["row_id"])
    return rows


def validate_enrich(path: Path, baseline: dict[str, dict[str, str]], *, as_of: date) -> list[dict[str, str]]:
    rows = load_csv(path, ENRICH_FIELDS)
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=2):
        rid = row["row_id"]
        if not ROW_ID.fullmatch(rid):
            raise ValueError(f"{path.name}:{index}: invalid row_id {rid!r}")
        if rid not in baseline:
            raise ValueError(f"{path.name}:{index}: row_id {rid} not found in round 1")
        base = baseline[rid]
        if row["city"] != base["city"]:
            raise ValueError(f"{path.name}:{index}: city does not match baseline")
        field = row["field"]
        if field not in ENRICHABLE:
            raise ValueError(f"{path.name}:{index}: field {field!r} is not enrichable")
        if field == "subcategory" and row["new_value"] not in SUBCATEGORIES[base["category"]]:
            raise ValueError(f"{path.name}:{index}: subcategory not allowed for {base['category']}")
        if field == "name_en_type" and row["new_value"] not in {"官方英文", "来源已有英文", "机器翻译", "拼音转写"}:
            raise ValueError(f"{path.name}:{index}: invalid name_en_type")
        if row["old_value"] != (base.get(field) or ""):
            raise ValueError(f"{path.name}:{index}: old_value does not match round 1")
        if not row["new_value"].strip() or row["new_value"] == row["old_value"]:
            raise ValueError(f"{path.name}:{index}: new_value must be non-empty and different")
        if row["source_type"] not in SOURCE_TYPES:
            raise ValueError(f"{path.name}:{index}: unknown source_type {row['source_type']!r}")
        if not valid_url(row["source_url"]):
            raise ValueError(f"{path.name}:{index}: invalid source_url")
        if parse_date(row["collected_on"]) > as_of:
            raise ValueError(f"{path.name}:{index}: collected_on is in the future")
        if not row["notes"].strip():
            raise ValueError(f"{path.name}:{index}: notes must state review caveats")
        key = (rid, field)
        if key in seen:
            raise ValueError(f"{path.name}:{index}: duplicate enrichment for {rid}/{field}")
        seen.add(key)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", nargs="+", type=Path, required=True)
    parser.add_argument("--new", nargs="*", type=Path, default=[])
    parser.add_argument("--enrich", nargs="*", type=Path, default=[])
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    try:
        baseline_rows: dict[str, dict[str, str]] = {}
        for path in args.baseline:
            for row in load_csv(path, FIELDS):
                if row["row_id"] in baseline_rows:
                    raise ValueError(f"{path.name}: duplicate baseline row_id {row['row_id']}")
                baseline_rows[row["row_id"]] = row
        if set(row["city"] for row in baseline_rows.values()) != CITIES:
            raise ValueError("baseline must cover seven cities")
        total_new = total_enrich = 0
        new_by_name: dict[str, list[dict[str, str]]] = {}
        enrich_by_name: dict[str, list[dict[str, str]]] = {}
        for path in args.new:
            rows = validate_new(path, set(baseline_rows), as_of=args.as_of)
            new_by_name[path.name] = rows
            total_new += len(rows)
            print(f"PASS new {path.name}: {len(rows)} rows")
        for path in args.enrich:
            rows = validate_enrich(path, baseline_rows, as_of=args.as_of)
            enrich_by_name[path.name] = rows
            total_enrich += len(rows)
            print(f"PASS enrich {path.name}: {len(rows)} rows")
        combined_new = new_by_name.get("all-cities-new.csv")
        city_new = {k: v for k, v in new_by_name.items() if k != "all-cities-new.csv"}
        cross_new: set[str] = set()
        for rows in city_new.values():
            for row in rows:
                if row["row_id"] in cross_new:
                    raise ValueError(f"duplicate new row_id across files: {row['row_id']}")
                cross_new.add(row["row_id"])
        if combined_new is not None and city_new:
            if {r["row_id"] for r in combined_new} != {r["row_id"] for rows in city_new.values() for r in rows}:
                raise ValueError("all-cities-new.csv row_ids must match the union of city new files")
            total_new = len(combined_new)
        combined_enrich = enrich_by_name.get("all-cities-enrich.csv")
        city_enrich = {k: v for k, v in enrich_by_name.items() if k != "all-cities-enrich.csv"}
        if combined_enrich is not None and city_enrich:
            union = {(r["row_id"], r["field"]) for rows in city_enrich.values() for r in rows}
            if {(r["row_id"], r["field"]) for r in combined_enrich} != union:
                raise ValueError("all-cities-enrich.csv keys must match the union of city enrich files")
            total_enrich = len(combined_enrich)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print(f"PASS round2: {total_new} new rows, {total_enrich} enrichment rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
