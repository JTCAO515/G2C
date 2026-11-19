"""Validate the unverified Guangzhou/Shenzhen place candidates; no network IO."""
from datetime import date
from pathlib import Path
import re
from urllib.parse import urlsplit

from validate import calendar_date, load_records, nonblank, validation_cli

VERSION = "visitor-place-candidate.2"
STATUS = "待核实"
CATEGORIES = frozenset({"attraction", "restaurant", "hotel", "shop"})
SOURCE_TYPES = frozenset({
    "official_government", "official_venue", "official_transport", "official_media",
    "commercial_platform", "map_platform", "other_public",
})
FIELDS = frozenset({
    "format_version", "id", "city", "category", "subcategory", "name_zh", "name_en",
    "name_en_source", "district", "address", "description_zh", "tags", "official_url",
    "attraction_info", "restaurant_info", "hotel_info", "shop_info", "sources",
    "collected_on", "status", "missing", "notes", "conflicts",
})
INFO_FIELDS = {
    "attraction_info": frozenset({"level", "ticket_note", "booking_note"}),
    "restaurant_info": frozenset({"cuisine", "reservation_note"}),
    "hotel_info": frozenset({"stars", "brand", "note"}),
    "shop_info": frozenset({"shop_type", "goods"}),
}
CATEGORY_INFO = {"attraction": "attraction_info", "restaurant": "restaurant_info",
                 "hotel": "hotel_info", "shop": "shop_info"}
NAME_EN_SOURCES = frozenset({"official", "machine"})
SOURCE_FIELDS = frozenset({"name", "url", "type", "language", "published_on", "valid_until"})
PLACE_ID = re.compile(
    r"place\.([0-9]{4}-[0-9]{2}-[0-9]{2})\.([a-z0-9-]+)\."
    r"(attraction|restaurant|hotel|shop)\.[a-z0-9][a-z0-9.-]*")
MAX_DESCRIPTION = 300


def source_url(value: object) -> bool:
    """Official pages may still be HTTP-only; the URL is recorded as-is."""
    if not isinstance(value, str):
        return False
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme in ("http", "https") and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not parsed.fragment and parsed.port in (None, 80, 443))
    except ValueError:
        return False


def text_array(value: object, *, field: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{field} must be a text array")
    if any(not nonblank(item) for item in value):
        raise ValueError(f"{field} must contain nonblank text")
    if len(value) != len(set(value)):
        raise ValueError(f"duplicate {field}")
    return value


def nullable_text(value: object, *, field: str) -> None:
    if value is not None and not nonblank(value):
        raise ValueError(f"{field} must be null or nonblank")


def validate_info_object(value: object, *, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or value.keys() != INFO_FIELDS[field]:
        raise ValueError(f"{field} must have exactly the documented fields")
    for key in INFO_FIELDS[field]:
        nullable_text(value[key], field=f"{field}.{key}")


def validate_source(value: object, *, collected: date) -> None:
    if not isinstance(value, dict) or value.keys() != SOURCE_FIELDS:
        raise ValueError("source must have exactly the documented fields")
    if not nonblank(value["name"]):
        raise ValueError("source.name must be nonblank")
    if not nonblank(value["language"]):
        raise ValueError("source.language must be nonblank")
    if not isinstance(value["type"], str) or value["type"] not in SOURCE_TYPES:
        raise ValueError("invalid source type")
    if not source_url(value["url"]):
        raise ValueError("invalid source URL")
    published = None if value["published_on"] is None else calendar_date(value["published_on"])
    if value["valid_until"] is not None:
        calendar_date(value["valid_until"])
    if published is not None and published > collected:
        raise ValueError("source.published_on is after collected_on")


def validate_candidate(entry: object, *, as_of: date) -> None:
    if not isinstance(entry, dict) or entry.keys() != FIELDS:
        raise ValueError("place candidate must have exactly the documented fields")
    if entry["format_version"] != VERSION:
        raise ValueError("unsupported place candidate format_version")
    collected = calendar_date(entry["collected_on"])
    if collected > as_of:
        raise ValueError("collected_on is in the future")
    match = PLACE_ID.fullmatch(entry["id"]) if isinstance(entry["id"], str) else None
    if match is None:
        raise ValueError("invalid place candidate id")
    if match.group(1) != entry["collected_on"]:
        raise ValueError("place candidate id date must equal collected_on")
    if match.group(2) != entry["city"]:
        raise ValueError("place candidate id city must equal city")
    if match.group(3) != entry["category"]:
        raise ValueError("place candidate id category must equal category")
    if entry["category"] not in CATEGORIES:
        raise ValueError("invalid category")
    if not nonblank(entry["city"]):
        raise ValueError("city must be nonblank")
    if not nonblank(entry["subcategory"]):
        raise ValueError("subcategory must be nonblank")
    if not nonblank(entry["name_zh"]):
        raise ValueError("name_zh must be nonblank")
    nullable_text(entry["name_en"], field="name_en")
    name_en = entry["name_en"]
    if name_en is None:
        if entry["name_en_source"] is not None:
            raise ValueError("name_en_source must be null when name_en is null")
    elif entry["name_en_source"] not in NAME_EN_SOURCES:
        raise ValueError("name_en_source must be official or machine when name_en is set")
    nullable_text(entry["district"], field="district")
    nullable_text(entry["address"], field="address")
    description = entry["description_zh"]
    if not nonblank(description):
        raise ValueError("description_zh must be nonblank")
    if len(description) > MAX_DESCRIPTION:
        raise ValueError("description_zh must stay a short summary")
    text_array(entry["tags"], field="tags", allow_empty=True)
    if entry["official_url"] is not None and not source_url(entry["official_url"]):
        raise ValueError("invalid official_url")
    for field in INFO_FIELDS:
        validate_info_object(entry[field], field=field)
    required_info = CATEGORY_INFO[entry["category"]]
    for field in INFO_FIELDS:
        if (field == required_info and entry[field] is None) or \
                (field != required_info and entry[field] is not None):
            raise ValueError(f"{entry['category']} requires {required_info} and null other info objects")
    sources = entry["sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a nonempty array")
    for source in sources:
        validate_source(source, collected=collected)
    urls = [source["url"] for source in sources]
    if len(urls) != len(set(urls)):
        raise ValueError("duplicate source URL")
    if entry["status"] != STATUS:
        raise ValueError("place candidate status must stay 待核实")
    text_array(entry["missing"], field="missing", allow_empty=True)
    if entry["notes"] is not None and not nonblank(entry["notes"]):
        raise ValueError("notes must be null or nonblank")
    text_array(entry["conflicts"], field="conflicts", allow_empty=True)


def load_place_candidates(paths: list[Path], *, as_of: date) -> list[dict]:
    return load_records(paths, validate_record=lambda entry: validate_candidate(entry, as_of=as_of))


def main() -> int:
    return validation_cli(load_place_candidates, description=__doc__,
                          label="place candidate records")


if __name__ == "__main__":
    raise SystemExit(main())
