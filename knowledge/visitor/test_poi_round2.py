import csv
import sys
import tempfile
from datetime import date
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_poi_round2 import ENRICH_FIELDS, validate_enrich, validate_new
from validate_seven_city_poi import FIELDS

AS_OF = date(2026, 11, 18)


def poi(**overrides):
    base = {field: "" for field in FIELDS}
    base.update({
        "row_id": "BJ-0600", "city": "北京", "district": "东城区",
        "category": "餐饮", "subcategory": "小吃店", "name_zh": "测试小吃店",
        "name_en": "Test Snack Shop", "name_en_type": "机器翻译", "address_zh": "未知",
        "source_name": "测试目录", "source_type": "政府目录",
        "source_url": "https://example.com/list", "collected_on": "2026-11-18",
        "review_status": "待复核", "notes": "待复核",
    })
    base.update(overrides)
    return base


def enrich(**overrides):
    base = {field: "" for field in ENRICH_FIELDS}
    base.update({
        "row_id": "BJ-0001", "city": "北京", "field": "address_zh",
        "old_value": "未知", "new_value": "北京市东城区天坛内东里7号",
        "source_name": "测试页", "source_type": "政府网站",
        "source_url": "https://example.com/detail", "collected_on": "2026-11-18",
        "notes": "地址待复核",
    })
    base.update(overrides)
    return base


def write(rows, fields, suffix=".csv"):
    handle = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8", newline="")
    with handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return Path(handle.name)


class Round2Tests(unittest.TestCase):
    def test_valid_new_row(self):
        path = write([poi()], FIELDS)
        self.assertEqual(len(validate_new(path, {"BJ-0001"}, as_of=AS_OF)), 1)

    def test_new_row_cannot_reuse_baseline_id(self):
        path = write([poi(row_id="BJ-0001")], FIELDS)
        with self.assertRaisesRegex(ValueError, "already exists"):
            validate_new(path, {"BJ-0001"}, as_of=AS_OF)

    def test_duplicate_new_row_id_is_rejected(self):
        path = write([poi(), poi()], FIELDS)
        with self.assertRaisesRegex(ValueError, "duplicate row_id"):
            validate_new(path, set(), as_of=AS_OF)

    def test_valid_enrichment(self):
        baseline = {"BJ-0001": poi(row_id="BJ-0001", address_zh="未知")}
        path = write([enrich()], ENRICH_FIELDS)
        self.assertEqual(len(validate_enrich(path, baseline, as_of=AS_OF)), 1)

    def test_enrichment_old_value_must_match(self):
        baseline = {"BJ-0001": poi(row_id="BJ-0001", address_zh="旧地址")}
        path = write([enrich()], ENRICH_FIELDS)
        with self.assertRaisesRegex(ValueError, "old_value"):
            validate_enrich(path, baseline, as_of=AS_OF)

    def test_enrichment_field_must_be_allowed(self):
        baseline = {"BJ-0001": poi(row_id="BJ-0001", address_zh="未知")}
        path = write([enrich(field="source_url", new_value="https://example.com")], ENRICH_FIELDS)
        with self.assertRaisesRegex(ValueError, "not enrichable"):
            validate_enrich(path, baseline, as_of=AS_OF)

    def test_enrichment_subcategory_must_fit_category(self):
        baseline = {"BJ-0001": poi(row_id="BJ-0001", address_zh="未知")}
        path = write([enrich(field="subcategory", new_value="购物中心")], ENRICH_FIELDS)
        with self.assertRaisesRegex(ValueError, "not allowed"):
            validate_enrich(path, baseline, as_of=AS_OF)

    def test_duplicate_enrichment_is_rejected(self):
        baseline = {"BJ-0001": poi(row_id="BJ-0001", address_zh="未知")}
        path = write([enrich(), enrich()], ENRICH_FIELDS)
        with self.assertRaisesRegex(ValueError, "duplicate enrichment"):
            validate_enrich(path, baseline, as_of=AS_OF)


if __name__ == "__main__":
    unittest.main()
