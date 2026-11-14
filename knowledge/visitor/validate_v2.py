"""Additive WP12 content format. It is not a new FACT wire or an enabled producer."""
from datetime import date
from pathlib import Path
import re
from urllib.parse import urlsplit

from validate import FIELDS, TOPICS, load_records, nonblank, validate_entry_fields, validation_cli

VERSION = "visitor-entry.2"
V2_FIELDS = FIELDS | {"format_version", "entry_kind", "subject", "conditions"}
V2_TOPICS = TOPICS | {"visa_entry"}
CONDITION_FIELDS = {"reservation_required", "closed_weekdays", "advance_booking_days", "advance_booking_rule",
                    "closed_weekdays_public_holiday_exception"}
SUBJECT_FIELDS = {"key", "name_zh", "name_en", "wikidata_qid"}
GOVERNMENT_HOSTS = frozenset({
    "english.www.gov.cn", "www.beijing.gov.cn", "www.chengdu.gov.cn", "www.xa.gov.cn",
    "www.shanghai.gov.cn", "www.hangzhou.gov.cn", "www.cq.gov.cn", "www.sz.gov.cn",
    "www.nra.gov.cn", "www.mot.gov.cn", "www.miit.gov.cn", "www.pbc.gov.cn",
    "www.nia.gov.cn", "www.mfa.gov.cn",
})
IMMIGRATION_CHANNEL_HOSTS = {"www.nia.gov.cn", "www.mfa.gov.cn"}


def place_key(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", value) is not None


def qid(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"Q[1-9][0-9]*", value) is not None


def validate_conditions(value: object) -> None:
    if not isinstance(value, dict) or value.keys() != CONDITION_FIELDS:
        raise ValueError("conditions must have exactly the documented fields")
    required = value["reservation_required"]
    if required is not None and type(required) is not bool:
        raise ValueError("reservation_required must be boolean or null")
    days = value["closed_weekdays"]
    exception = value["closed_weekdays_public_holiday_exception"]
    if days is None:
        if exception is not None:
            raise ValueError("unknown closure days require an unknown holiday exception")
    else:
        if (not isinstance(days, list)
                or any(type(day) is not int or not 1 <= day <= 7 for day in days)
                or len(days) != len(set(days))):
            raise ValueError("closed_weekdays must be unique ISO weekdays 1..7 or null")
        if type(exception) is not bool or (not days and exception):
            raise ValueError("known closure days require an explicit consistent holiday exception")
    advance = value["advance_booking_days"]
    rule = value["advance_booking_rule"]
    if advance is None:
        if rule is not None:
            raise ValueError("unknown advance days require an unknown advance rule")
    else:
        if type(advance) is not int or advance < 0:
            raise ValueError("advance_booking_days must be a nonnegative integer or null")
        if rule not in ("window_max", "minimum_lead"):
            raise ValueError("advance days require window_max or minimum_lead semantics")
        if rule == "minimum_lead" and required is not True:
            raise ValueError("minimum required advance days need reservation_required=true")


def validate_entry_v2(entry: object, *, as_of: date) -> None:
    if not isinstance(entry, dict) or entry.keys() != V2_FIELDS:
        raise ValueError("v2 entry must have exactly the documented fields")
    if entry["format_version"] != VERSION:
        raise ValueError("unsupported visitor format_version")
    validate_entry_fields(entry, as_of=as_of, topics=V2_TOPICS)
    if any(urlsplit(url).hostname not in GOVERNMENT_HOSTS for url in entry["source_urls"]):
        raise ValueError("v2 facts require confirmed government source hosts")
    validate_conditions(entry["conditions"])
    if entry["entry_kind"] == "official_channel":
        if entry["topic"] != "visa_entry" or entry["subject"] is not None:
            raise ValueError("official channels require visa_entry topic and no place subject")
        if any(value is not None for value in entry["conditions"].values()):
            raise ValueError("official channel guidance cannot carry eligibility or venue conditions")
        if any(urlsplit(url).hostname not in IMMIGRATION_CHANNEL_HOSTS for url in entry["source_urls"]):
            raise ValueError("visa/entry guidance requires an approved immigration official channel")
    elif entry["entry_kind"] == "fact":
        if entry["topic"] == "visa_entry":
            raise ValueError("visa/entry content must be official_channel guidance")
        subject = entry["subject"]
        if not isinstance(subject, dict) or subject.keys() != SUBJECT_FIELDS:
            raise ValueError("place facts require an exact subject shape")
        if not place_key(subject["key"]) or any(not nonblank(subject[key]) for key in ("name_zh", "name_en")):
            raise ValueError("invalid place subject")
        if subject["wikidata_qid"] is not None and not qid(subject["wikidata_qid"]):
            raise ValueError("invalid subject Wikidata QID")
    else:
        raise ValueError("unsupported entry_kind")


def load_entries_v2(paths: list[Path], *, as_of: date) -> list[dict]:
    return load_records(paths, validate_record=lambda entry: validate_entry_v2(entry, as_of=as_of))


def main() -> int:
    return validation_cli(load_entries_v2, description=__doc__, label="v2 entries")


if __name__ == "__main__":
    raise SystemExit(main())
