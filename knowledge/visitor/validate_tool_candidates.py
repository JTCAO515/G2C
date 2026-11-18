"""Validate unverified app/tool candidate records at the file boundary; no network IO."""
from datetime import date
from pathlib import Path
import re
from urllib.parse import urlsplit

from validate import calendar_date, load_records, nonblank, validation_cli

VERSION = "visitor-tool-candidate.1"
STATUS = "待核实"
CATEGORIES = frozenset({
    "payment", "map", "taxi", "rail", "city_transport",
    "translation", "communication", "booking", "other",
})
CITIES = frozenset({
    "beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", "xian",
    "hangzhou", "chongqing", "suzhou-jiangsu", "nanjing", "wuhan", "changsha",
    "guilin", "xiamen", "qingdao", "harbin", "kunming", "zhangjiajie",
    "luoyang", "sanya", "taizhou-zhejiang", "suzhou-anhui", "nationwide",
})
LINK_TYPES = frozenset({"official_site", "official_store", "official_help"})
SOURCE_TYPES = frozenset({
    "official_government", "official_operator", "official_tool",
    "official_store", "official_media", "commercial_platform", "other_public",
})
FIELDS = frozenset({
    "format_version", "id", "name_zh", "name_en", "category", "purpose_zh",
    "cities", "languages", "preparation", "official_links", "sources",
    "collected_on", "status", "missing", "notes", "conflicts", "related_entries",
})
LINK_FIELDS = frozenset({"name", "url", "type"})
SOURCE_FIELDS = frozenset({"name", "url", "type", "language", "published_on", "valid_until"})
CANDIDATE_ID = re.compile(r"tool-candidate\.([0-9]{4}-[0-9]{2}-[0-9]{2})\.[a-z0-9][a-z0-9.-]*")
ENTRY_ID = re.compile(r"visitor\.[a-z0-9][a-z0-9.-]*")
MAX_PURPOSE = 600


def source_url(value: object) -> bool:
    """Official pages and stores may still be HTTP-only; the URL is recorded as-is."""
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


def validate_link(value: object) -> None:
    if not isinstance(value, dict) or value.keys() != LINK_FIELDS:
        raise ValueError("official link must have exactly name/url/type")
    if not nonblank(value["name"]):
        raise ValueError("official link name must be nonblank")
    if not isinstance(value["type"], str) or value["type"] not in LINK_TYPES:
        raise ValueError("invalid official link type")
    if not source_url(value["url"]):
        raise ValueError("invalid official link URL")


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
        raise ValueError("tool candidate must have exactly the documented fields")
    if entry["format_version"] != VERSION:
        raise ValueError("unsupported tool candidate format_version")
    collected = calendar_date(entry["collected_on"])
    if collected > as_of:
        raise ValueError("collected_on is in the future")
    match = CANDIDATE_ID.fullmatch(entry["id"]) if isinstance(entry["id"], str) else None
    if match is None:
        raise ValueError("invalid tool candidate id")
    if match.group(1) != entry["collected_on"]:
        raise ValueError("tool candidate id date must equal collected_on")
    for field in ("name_zh", "name_en"):
        if not nonblank(entry[field]):
            raise ValueError(f"{field} must be nonblank")
    if not isinstance(entry["category"], str) or entry["category"] not in CATEGORIES:
        raise ValueError("invalid category")
    purpose = entry["purpose_zh"]
    if not nonblank(purpose):
        raise ValueError("purpose_zh must be nonblank")
    if len(purpose) > MAX_PURPOSE:
        raise ValueError("purpose_zh must stay a short summary")
    cities = text_array(entry["cities"], field="cities")
    if any(city not in CITIES for city in cities):
        raise ValueError("invalid city")
    text_array(entry["languages"], field="languages")
    text_array(entry["preparation"], field="preparation")
    links = entry["official_links"]
    if not isinstance(links, list):
        raise ValueError("official_links must be an array")
    for link in links:
        validate_link(link)
    urls = [link["url"] for link in links]
    if len(urls) != len(set(urls)):
        raise ValueError("duplicate official link URL")
    sources = entry["sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a nonempty array")
    for source in sources:
        validate_source(source, collected=collected)
    source_urls = [source["url"] for source in sources]
    if len(source_urls) != len(set(source_urls)):
        raise ValueError("duplicate source URL")
    if entry["status"] != STATUS:
        raise ValueError("tool candidate status must stay 待核实")
    text_array(entry["missing"], field="missing", allow_empty=True)
    if entry["notes"] is not None and not nonblank(entry["notes"]):
        raise ValueError("notes must be null or nonblank")
    text_array(entry["conflicts"], field="conflicts", allow_empty=True)
    related = text_array(entry["related_entries"], field="related_entries", allow_empty=True)
    if any(ENTRY_ID.fullmatch(item) is None for item in related):
        raise ValueError("related_entries must be existing visitor entry ids")


def load_tool_candidates(paths: list[Path], *, as_of: date) -> list[dict]:
    return load_records(paths, validate_record=lambda entry: validate_candidate(entry, as_of=as_of))


def main() -> int:
    return validation_cli(load_tool_candidates, description=__doc__,
                          label="tool candidate records")


if __name__ == "__main__":
    raise SystemExit(main())
