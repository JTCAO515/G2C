"""Wikidata label records only. No network, coordinates or coordinate conversion."""
from datetime import date
from pathlib import Path

from validate import load_records, nonblank, validate_identity_fields, validation_cli
from validate_v2 import place_key, qid

VERSION = "visitor-name.1"
NAME_FIELDS = {"format_version", "id", "place_key", "wikidata_qid", "name_zh", "name_en",
               "cities", "source_urls", "checked_on", "expires_on", "license"}


def validate_name(entry: object, *, as_of: date) -> None:
    if not isinstance(entry, dict) or entry.keys() != NAME_FIELDS:
        raise ValueError("name record must have exactly the documented fields; coordinates are not accepted")
    if entry["format_version"] != VERSION or entry["license"] != "CC0-1.0":
        raise ValueError("unsupported name format or license")
    validate_identity_fields(entry, as_of=as_of)
    if not place_key(entry["place_key"]) or not qid(entry["wikidata_qid"]):
        raise ValueError("invalid place_key or QID")
    if any(not nonblank(entry[key]) for key in ("name_zh", "name_en")):
        raise ValueError("both original zh and en labels are required")
    if entry["source_urls"] != [f"https://www.wikidata.org/wiki/{entry['wikidata_qid']}"]:
        raise ValueError("name source must match the exact Wikidata QID")


def load_names(paths: list[Path], *, as_of: date) -> list[dict]:
    records = load_records(paths, validate_record=lambda entry: validate_name(entry, as_of=as_of))
    for field in ("place_key", "wikidata_qid"):
        if len({record[field] for record in records}) != len(records):
            raise ValueError(f"duplicate name {field} in batch")
    return records


def main() -> int:
    return validation_cli(load_names, description=__doc__, label="name records")


if __name__ == "__main__":
    raise SystemExit(main())
