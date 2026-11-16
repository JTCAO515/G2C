"""Explicit nine-city content extension; old formats and FACT wire stay unchanged."""
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from validate import CITIES, load_records, nonblank, validate_entry_fields, validation_cli
from validate_v2 import (GOVERNMENT_HOSTS, IMMIGRATION_CHANNEL_HOSTS, SUBJECT_FIELDS,
                         V2_FIELDS, V2_TOPICS, place_key, qid, validate_conditions)

VERSION = "visitor-entry.3"
V3_FIELDS = V2_FIELDS
V3_CITIES = CITIES | {"taizhou-zhejiang", "suzhou-anhui"}
V3_TOPICS = V2_TOPICS | {"seasonal_holiday"}
# JT approved these exact hostnames in #702/6907792461, without subdomains.
V3_GOVERNMENT_HOSTS = GOVERNMENT_HOSTS | {"www.zjtz.gov.cn", "www.ahsz.gov.cn", "www.gov.cn"}
# JT venue approvals: #702/6908024069, 6908348251; candidates failing identity are excluded.
VENUE_SOURCE_CITIES = {host: frozenset({city}) for host, city in {
    "www.zjtz.gov.cn": "taizhou-zhejiang", "www.ahsz.gov.cn": "suzhou-anhui",
    "www.cdmuseum.com": "chengdu", "www.cddfct.cn": "chengdu", "www.panda.org.cn": "chengdu",
    "www.bmy.com.cn": "xian", "www.beilin-museum.com": "xian", "beilin-museum.com": "xian",
    "www.dpm.org.cn": "beijing", "westlake.hangzhou.gov.cn": "hangzhou",
    "wgltj.zjtz.gov.cn": "taizhou-zhejiang", "www.linhai.gov.cn": "taizhou-zhejiang",
    "www.sz-museum.com": "suzhou-anhui", "cgj.ahsz.gov.cn": "suzhou-anhui",
    "www.badaling.cn": "beijing", "cgj.cq.gov.cn": "chongqing",
    "qjxq.xa.gov.cn": "xian",
    "www.shanghaimuseum.net": "shanghai", "www.shanghaimuseum.cn": "shanghai",
    "www.shenzhenmuseum.com": "shenzhen", "www.szwwco.com": "shenzhen",
}.items()}
VENUE_SOURCE_CITIES.update({
    "wlt.sc.gov.cn": frozenset({"chengdu"}),
    "ct.zj.gov.cn": frozenset({"hangzhou", "taizhou-zhejiang"}),
    "whlyw.cq.gov.cn": frozenset({"chongqing"}),
    "cqjlp.gov.cn": frozenset({"chongqing"}),
    "wlj.xa.gov.cn": frozenset({"xian"}),
})
VENUE_PAGE_CITIES = {
    "https://cdn3.shenzhenmuseum.com/museum/html/aboutus/visit-service.html": frozenset({"shenzhen"}),
}
V3_APPROVED_HOSTS = V3_GOVERNMENT_HOSTS | VENUE_SOURCE_CITIES.keys()


def validate_entry_v3(entry: object, *, as_of: date) -> None:
    if not isinstance(entry, dict) or entry.keys() != V3_FIELDS:
        raise ValueError("v3 entry must have exactly the documented fields")
    if entry["format_version"] != VERSION:
        raise ValueError("unsupported visitor format_version")
    validate_entry_fields(entry, as_of=as_of, topics=V3_TOPICS, cities=V3_CITIES)
    if any(urlsplit(url).hostname not in V3_APPROVED_HOSTS and url not in VENUE_PAGE_CITIES
           for url in entry["source_urls"]):
        raise ValueError("v3 facts require confirmed source hosts")
    # The three new hostname approvals are narrower than the existing inventory.
    for url in entry["source_urls"]:
        host = urlsplit(url).hostname
        if host == "www.gov.cn" and entry["topic"] != "seasonal_holiday":
            raise ValueError("new gov.cn approval is limited to holiday guidance")
        local_cities = VENUE_SOURCE_CITIES.get(host, VENUE_PAGE_CITIES.get(url))
        if local_cities is not None and (len(entry["cities"]) != 1 or entry["cities"][0] not in local_cities
                                      or entry["topic"] != "passport_booking" or entry["subject"] is None):
            raise ValueError("new local source approval is limited to that city's venue guidance")
    validate_conditions(entry["conditions"])
    kind, subject = entry["entry_kind"], entry["subject"]
    if kind not in ("fact", "official_channel"):
        raise ValueError("unsupported entry_kind")
    if entry["topic"] == "visa_entry":
        if kind != "official_channel":
            raise ValueError("visa/entry content must be official_channel guidance")
        if any(urlsplit(url).hostname not in IMMIGRATION_CHANNEL_HOSTS for url in entry["source_urls"]):
            raise ValueError("visa/entry guidance requires an approved immigration official channel")
    if kind == "official_channel":
        if entry["topic"] not in ("visa_entry", "seasonal_holiday") or subject is not None:
            raise ValueError("official channels require a supported topic and no place subject")
    if subject is None:
        if any(value is not None for value in entry["conditions"].values()):
            raise ValueError("city-wide facts and channels cannot carry place conditions")
    else:
        if not isinstance(subject, dict) or subject.keys() != SUBJECT_FIELDS:
            raise ValueError("place facts require an exact subject shape")
        if not place_key(subject["key"]) or any(not nonblank(subject[key]) for key in ("name_zh", "name_en")):
            raise ValueError("invalid place subject")
        if subject["wikidata_qid"] is not None and not qid(subject["wikidata_qid"]):
            raise ValueError("invalid subject Wikidata QID")


def load_entries_v3(paths: list[Path], *, as_of: date) -> list[dict]:
    return load_records(paths, validate_record=lambda entry: validate_entry_v3(entry, as_of=as_of))


def main() -> int:
    return validation_cli(load_entries_v3, description=__doc__, label="v3 entries")


if __name__ == "__main__":
    raise SystemExit(main())
