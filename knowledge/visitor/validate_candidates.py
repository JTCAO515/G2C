"""Validate the unverified candidate pool at the deserialization boundary; no network IO."""
from datetime import date
from pathlib import Path
import re
from urllib.parse import urlsplit

from validate import calendar_date, load_records, nonblank, validation_cli

VERSION = "visitor-candidate.1"
STATUS = "待核实"
CITIES = frozenset({
    "beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", "xian",
    "hangzhou", "chongqing", "suzhou-jiangsu", "nanjing", "wuhan", "changsha",
    "guilin", "xiamen", "qingdao", "harbin", "kunming", "zhangjiajie",
    "luoyang", "sanya", "taizhou-zhejiang", "suzhou-anhui", "nationwide",
})
THEMES = frozenset({
    "payment", "internet", "transport", "rail", "passport_booking", "emergency",
    "arrival", "attraction", "trip_planning", "accessibility", "family",
    "visa_entry", "seasonal_holiday",
})
SOURCE_TYPES = frozenset({
    "official_government", "official_venue", "official_transport",
    "official_media", "intergovernmental", "commercial_platform",
    "map_platform", "other_public",
})
FIELDS = frozenset({
    "format_version", "id", "title_zh", "summary_zh", "cities", "place",
    "audience", "themes", "sources", "collected_on", "status", "missing",
    "notes", "conflicts", "related_entries",
})
PLACE_FIELDS = frozenset({"name_zh", "name_en", "address"})
SOURCE_FIELDS = frozenset({"name", "url", "type", "language", "published_on", "valid_until"})
CANDIDATE_ID = re.compile(r"candidate\.([0-9]{4}-[0-9]{2}-[0-9]{2})\.[a-z0-9][a-z0-9.-]*")
ENTRY_ID = re.compile(r"visitor\.[a-z0-9][a-z0-9.-]*")
MAX_SUMMARY = 600


def source_url(value: object) -> bool:
    """Candidates may cite an official page that is still HTTP-only; the URL is recorded as-is."""
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


def validate_place(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or value.keys() != PLACE_FIELDS:
        raise ValueError("place must be null or have exactly name_zh/name_en/address")
    if not nonblank(value["name_zh"]):
        raise ValueError("place.name_zh must be nonblank")
    for key in ("name_en", "address"):
        if value[key] is not None and not nonblank(value[key]):
            raise ValueError(f"place.{key} must be null or nonblank")


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
        raise ValueError("candidate must have exactly the documented fields")
    if entry["format_version"] != VERSION:
        raise ValueError("unsupported candidate format_version")
    collected = calendar_date(entry["collected_on"])
    if collected > as_of:
        raise ValueError("collected_on is in the future")
    match = CANDIDATE_ID.fullmatch(entry["id"]) if isinstance(entry["id"], str) else None
    if match is None:
        raise ValueError("invalid candidate id")
    if match.group(1) != entry["collected_on"]:
        raise ValueError("candidate id date must equal collected_on")
    if not nonblank(entry["title_zh"]):
        raise ValueError("title_zh must be nonblank")
    summary = entry["summary_zh"]
    if not nonblank(summary):
        raise ValueError("summary_zh must be nonblank")
    if len(summary) > MAX_SUMMARY:
        raise ValueError("summary_zh must stay a short summary")
    cities = text_array(entry["cities"], field="cities")
    if any(city not in CITIES for city in cities):
        raise ValueError("invalid city")
    text_array(entry["audience"], field="audience")
    themes = text_array(entry["themes"], field="themes")
    if any(theme not in THEMES for theme in themes):
        raise ValueError("invalid theme")
    validate_place(entry["place"])
    sources = entry["sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a nonempty array")
    for source in sources:
        validate_source(source, collected=collected)
    urls = [source["url"] for source in sources]
    if len(urls) != len(set(urls)):
        raise ValueError("duplicate source URL")
    if entry["status"] != STATUS:
        raise ValueError("candidate status must stay 待核实")
    text_array(entry["missing"], field="missing", allow_empty=True)
    if entry["notes"] is not None and not nonblank(entry["notes"]):
        raise ValueError("notes must be null or nonblank")
    text_array(entry["conflicts"], field="conflicts", allow_empty=True)
    related = text_array(entry["related_entries"], field="related_entries", allow_empty=True)
    if any(ENTRY_ID.fullmatch(item) is None for item in related):
        raise ValueError("related_entries must be existing visitor entry ids")


def load_candidates(paths: list[Path], *, as_of: date) -> list[dict]:
    return load_records(paths, validate_record=lambda entry: validate_candidate(entry, as_of=as_of))


def main() -> int:
    return validation_cli(load_candidates, description=__doc__, label="candidate records")


if __name__ == "__main__":
    raise SystemExit(main())
