import copy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from validate_place_candidates import FIELDS, load_place_candidates, validate_candidate

TODAY = date(2026, 11, 18)
ROOT = Path(__file__).resolve().parent


def make_candidate(**overrides):
    record = {
        "format_version": "visitor-place-candidate.1",
        "id": "place.2026-11-18.guangzhou.attraction.a001",
        "city": "guangzhou",
        "category": "attraction",
        "subcategory": "4A景区",
        "name_zh": "陈家祠",
        "name_en": None,
        "district": "荔湾",
        "address": "广州市中山七路恩龙里34号",
        "description_zh": "广州市 A 级景区名录登记条目（4A/荔湾），详细开放与预约信息待核实。",
        "tags": ["4A"],
        "official_url": None,
        "attraction_info": {"level": "4A", "ticket_note": None, "booking_note": None},
        "restaurant_info": None,
        "sources": [{
            "name": "广州市文化广电旅游局《广州市A级景区名录（2026年6月更新）》",
            "url": "https://www.gz.gov.cn/zwgk/zdly/lysc/cyzl/content/mpost_10899669.html",
            "type": "official_government",
            "language": "zh",
            "published_on": "2026-06-30",
            "valid_until": None,
        }],
        "collected_on": "2026-11-18",
        "status": "待核实",
        "missing": ["官方英文名待核实"],
        "notes": "仅根据官方名录登记，未核对开放与预约。",
        "conflicts": [],
    }
    record.update(overrides)
    return record


def make_restaurant(**overrides):
    record = make_candidate(
        id="place.2026-11-18.guangzhou.restaurant.r001",
        category="restaurant",
        subcategory="米其林必比登",
        name_zh="坚记",
        name_en="Jian Ji",
        district="荔湾",
        address="荔湾区",
        description_zh="2026 米其林指南广州必比登推介餐厅，主打传统面食。",
        tags=["米其林必比登"],
        attraction_info=None,
        restaurant_info={"cuisine": "面食", "reservation_note": None},
        sources=[{
            "name": "2026 广州深圳米其林指南必比登推介名单（转载）",
            "url": "https://www.sina.cn/news/detail/5333861284184580.html",
            "type": "commercial_platform",
            "language": "zh",
            "published_on": "2026-08-19",
            "valid_until": None,
        }],
        missing=["详细地址与营业时间待核实"],
    )
    record.update(overrides)
    return record


class PlaceCandidateFormatTests(unittest.TestCase):
    def setUp(self):
        self.record = make_candidate()

    def test_valid_records(self):
        validate_candidate(self.record, as_of=TODAY)
        validate_candidate(make_restaurant(), as_of=TODAY)

    def test_each_required_field_missing(self):
        for field in FIELDS:
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                del record[field]
                with self.assertRaises(ValueError):
                    validate_candidate(record, as_of=TODAY)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            validate_candidate({**self.record, "verified": True}, as_of=TODAY)

    def test_version_and_status(self):
        for field, value in (("format_version", "visitor-place-candidate.2"),
                             ("status", "已核实")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_candidate(make_candidate(**{field: value}), as_of=TODAY)

    def test_id_coupling(self):
        cases = {
            "id": ["place.2026-11-17.guangzhou.attraction.a001",
                   "place.2026-11-18.shanghai.attraction.a001",
                   "place.2026-11-18.guangzhou.restaurant.a001",
                   "place.2026-11-18.guangzhou.attraction", "visitor.2026-11-18.guangzhou.a001"],
            "city": ["shanghai", "unknown"],
            "category": ["museum"],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_candidate(make_candidate(**{field: value}), as_of=TODAY)

    def test_collected_date(self):
        with self.assertRaises(ValueError):
            validate_candidate(make_candidate(collected_on="2026-11-19",
                                              id="place.2026-11-19.guangzhou.attraction.a001"),
                               as_of=TODAY)
        for value in (None, "2026-1-1", "2026-02-30"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(collected_on=value), as_of=TODAY)

    def test_names_and_description(self):
        for field in ("name_zh", "subcategory"):
            for value in ("", "  ", "\ud800"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_candidate(make_candidate(**{field: value}), as_of=TODAY)
        for field in ("name_en", "district", "address"):
            for value in ("", "  "):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_candidate(make_candidate(**{field: value}), as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_candidate(make_candidate(description_zh="字" * 301), as_of=TODAY)

    def test_tags_and_official_url(self):
        validate_candidate(make_candidate(tags=[], official_url=None), as_of=TODAY)
        validate_candidate(make_candidate(official_url="http://www.gzmtr.com/"), as_of=TODAY)
        for field, value in (("tags", "4A"), ("tags", [""]), ("tags", ["4A", "4A"]),
                             ("official_url", "ftp://example.com/"),
                             ("official_url", "https://example.com/#a")):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(**{field: value}), as_of=TODAY)

    def test_info_objects_and_category_consistency(self):
        for value in ({"level": "4A", "ticket_note": None},
                      {"level": "4A", "ticket_note": None, "booking_note": None, "extra": None},
                      {"level": "", "ticket_note": None, "booking_note": None},
                      {"level": None, "ticket_note": "", "booking_note": None}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(attraction_info=value), as_of=TODAY)
        for field, value in (("attraction_info", None), ("restaurant_info", {"cuisine": None,
                                                                             "reservation_note": None})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_candidate(make_candidate(**{field: value}), as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_candidate(make_restaurant(restaurant_info=None), as_of=TODAY)

    def test_sources(self):
        valid = self.record["sources"][0]
        for value in ([], "https://example.com/", [valid, valid],
                      [{**valid, "url": "ftp://example.com/"}],
                      [{**valid, "type": "official"}],
                      [{"name": "x", "url": "https://example.com/", "type": "other_public",
                        "language": "zh"}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(sources=value), as_of=TODAY)

    def test_missing_notes_conflicts(self):
        validate_candidate(make_candidate(missing=[], notes=None, conflicts=[]), as_of=TODAY)
        for field, value in (("missing", None), ("missing", [""]), ("missing", "未知"),
                             ("notes", ""), ("conflicts", None), ("conflicts", [""])):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(**{field: value}), as_of=TODAY)

    def test_file_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "places.json"
            for raw in ["{", "{}", "[]", '[{"id":"one","id":"two"}]', "[NaN]",
                        json.dumps([self.record, self.record])]:
                path.write_text(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    load_place_candidates([path], as_of=TODAY)
            path.write_text(json.dumps([self.record]))
            with self.assertRaisesRegex(ValueError, "duplicate id"):
                load_place_candidates([path, path], as_of=TODAY)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "places.json"
            path.write_text(json.dumps([self.record, make_restaurant()]))
            result = subprocess.run([sys.executable, "-B", str(ROOT / "validate_place_candidates.py"),
                                     "--as-of", "2026-11-18", str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS: 2 place candidate records", result.stdout)
            path.write_text(json.dumps([make_candidate(status="已核实")]))
            result = subprocess.run([sys.executable, "-B", str(ROOT / "validate_place_candidates.py"),
                                     "--as-of", "2026-11-18", str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
