"""Validate the seven-city POI candidate CSVs; no network IO."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = [
    "row_id", "city", "district", "category", "subcategory", "name_zh", "name_en",
    "name_en_type", "name_en_source_url", "address_zh", "source_name", "source_type",
    "source_url", "collected_on", "review_status", "notes", "name_zh_alt", "name_en_alt",
    "brand_or_parent", "branch_name", "attraction_level", "cuisine", "signature_dishes",
    "intro_zh", "accommodation_type", "venue_type", "nearest_metro", "official_website",
    "source_published_on", "address_source_url", "extra_source_urls", "name_en_note",
    "source_category", "tags",
]

CITY_PREFIX = {
    "北京": "BJ", "上海": "SH", "广州": "GZ", "深圳": "SZ",
    "成都": "CD", "重庆": "CQ", "桂林": "GL",
}
PREFIX_CITY = {v: k for k, v in CITY_PREFIX.items()}
CITIES = frozenset(CITY_PREFIX)

SUBCATEGORIES = {
    "餐饮": frozenset({
        "本地菜馆", "老字号", "小吃店", "早餐店", "茶馆", "咖啡馆", "素食餐厅",
        "夜市餐饮摊点", "美食街", "烘焙甜品", "精致餐厅", "其他餐饮",
    }),
    "酒店住宿": frozenset({
        "酒店", "度假酒店", "精品酒店", "民宿", "青年旅舍", "公寓式酒店",
        "经济型酒店", "其他住宿",
    }),
    "景点与文博": frozenset({
        "景区", "历史遗址", "博物馆", "美术馆", "纪念馆", "寺庙", "教堂", "清真寺",
        "公园", "动物园", "观景点", "主题乐园", "文化场馆", "其他景点",
    }),
    "街道与街区": frozenset({
        "历史街巷", "步行街", "美食街", "夜市", "文化街区", "滨水步道",
    }),
    "商场与市场": frozenset({
        "购物中心", "百货", "奥特莱斯", "传统市场", "特色商业街", "文创市集",
        "免税店", "特色商店",
    }),
}
NAME_EN_TYPES = frozenset({"官方英文", "来源已有英文", "机器翻译", "拼音转写"})
SOURCE_TYPES = frozenset({
    "政府目录", "政府网站", "场馆官网", "品牌官网", "行业目录", "官方媒体",
    "商业平台", "地图平台", "其他公开来源",
})
STATUS = "待复核"
ROW_ID = re.compile(r"(BJ|SH|GZ|SZ|CD|CQ|GL)-[0-9]{4}")
REQUIRED = (
    "row_id", "city", "district", "category", "subcategory", "name_zh", "name_en",
    "name_en_type", "address_zh", "source_name", "source_type", "source_url",
    "collected_on", "review_status",
)


def nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_url(value: str) -> bool:
    if not value or any(ch.isspace() for ch in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (parsed.scheme in ("http", "https") and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and not parsed.fragment and parsed.port in (None, 80, 443))


def parse_date(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


def check_extra_urls(value: str) -> None:
    if not value:
        return
    for item in value.split(";"):
        if not item.strip():
            raise ValueError("extra_source_urls contains an empty item")
        name, sep, url = item.rpartition("|")
        if not sep or not name.strip() or not valid_url(url.strip()):
            raise ValueError("extra_source_urls items must be name|URL")


def validate_row(row: dict[str, str], *, as_of: date, source: str) -> None:
    missing = [field for field in REQUIRED if not nonblank(row.get(field, ""))]
    if missing:
        raise ValueError(f"{source}: missing {missing}")
    if row["city"] not in CITIES:
        raise ValueError(f"{source}: unknown city {row['city']!r}")
    if not ROW_ID.fullmatch(row["row_id"]):
        raise ValueError(f"{source}: invalid row_id {row['row_id']!r}")
    if not row["row_id"].startswith(CITY_PREFIX[row["city"]] + "-"):
        raise ValueError(f"{source}: row_id prefix does not match city")
    if row["category"] not in SUBCATEGORIES:
        raise ValueError(f"{source}: unknown category {row['category']!r}")
    if row["subcategory"] not in SUBCATEGORIES[row["category"]]:
        raise ValueError(f"{source}: subcategory {row['subcategory']!r} not allowed for {row['category']}")
    if row["name_en_type"] not in NAME_EN_TYPES:
        raise ValueError(f"{source}: unknown name_en_type {row['name_en_type']!r}")
    if not re.search(r"[A-Za-z]", row["name_en"]):
        raise ValueError(f"{source}: name_en must contain Latin letters")
    en_url = row.get("name_en_source_url", "")
    if row["name_en_type"] in {"官方英文", "来源已有英文"}:
        if not valid_url(en_url):
            raise ValueError(f"{source}: published English name requires a direct URL")
    elif en_url:
        raise ValueError(f"{source}: machine/pinyin English must not claim a source URL")
    if row["source_type"] not in SOURCE_TYPES:
        raise ValueError(f"{source}: unknown source_type {row['source_type']!r}")
    if not valid_url(row["source_url"]):
        raise ValueError(f"{source}: invalid source_url")
    if row.get("official_website") and not valid_url(row["official_website"]):
        raise ValueError(f"{source}: invalid official_website")
    if row.get("address_source_url") and not valid_url(row["address_source_url"]):
        raise ValueError(f"{source}: invalid address_source_url")
    check_extra_urls(row.get("extra_source_urls", ""))
    if row["review_status"] != STATUS:
        raise ValueError(f"{source}: review_status must be {STATUS}")
    collected = parse_date(row["collected_on"])
    if collected > as_of:
        raise ValueError(f"{source}: collected_on is in the future")
    if row.get("source_published_on"):
        published = parse_date(row["source_published_on"])
        if published > collected:
            raise ValueError(f"{source}: source_published_on is after collected_on")
    if not nonblank(row.get("notes", "")):
        raise ValueError(f"{source}: notes must state review caveats")


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise ValueError(f"{path.name}: header must exactly match the documented columns")
        return [dict(row) for row in reader]


def validate_file(path: Path, *, as_of: date) -> list[dict[str, str]]:
    rows = load_rows(path)
    if not rows:
        raise ValueError(f"{path.name}: no candidate rows")
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        if set(row) != set(FIELDS):
            raise ValueError(f"{path.name}:{index}: wrong column count")
        validate_row(row, as_of=as_of, source=f"{path.name}:{index}")
        if row["row_id"] in seen:
            raise ValueError(f"{path.name}:{index}: duplicate row_id {row['row_id']}")
        seen.add(row["row_id"])
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    total = 0
    by_path: dict[str, list[dict[str, str]]] = {}
    try:
        for path in args.paths:
            rows = validate_file(path, as_of=args.as_of)
            by_path[path.name] = rows
            total += len(rows)
            print(f"PASS {path.name}: {len(rows)} rows")
    except (OSError, ValueError, csv.Error) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    city_paths = {name: rows for name, rows in by_path.items() if name != "all-cities.csv"}
    combined = by_path.get("all-cities.csv")
    if combined is not None and city_paths:
        # City files must not repeat a row_id among themselves.
        seen: set[str] = set()
        for rows in city_paths.values():
            for row in rows:
                if row["row_id"] in seen:
                    print(f"FAIL duplicate row_id across files: {row['row_id']}", file=sys.stderr)
                    return 1
                seen.add(row["row_id"])
        # The combined file must be exactly the union of the city files.
        if {row["row_id"] for row in combined} != seen:
            print("FAIL all-cities.csv row_ids must match the union of city files", file=sys.stderr)
            return 1
        if set(row["city"] for rows in city_paths.values() for row in rows) != CITIES:
            print("FAIL city files must cover seven cities", file=sys.stderr)
            return 1

    city_rows: dict[str, int] = {}
    counted = city_paths.values() if (combined is not None and city_paths) else by_path.values()
    for rows in counted:
        for row in rows:
            city_rows[row["city"]] = city_rows.get(row["city"], 0) + 1
    if combined is not None and city_paths:
        total = len(combined)
    print(f"PASS total: {total} rows; " + "、".join(f"{city} {count}" for city, count in sorted(city_rows.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
