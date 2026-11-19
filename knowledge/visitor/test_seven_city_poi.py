import csv
from datetime import date
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_seven_city_poi import FIELDS, load_rows, main, validate_file, validate_row

AS_OF = date(2026, 11, 18)


def row(**overrides):
    base = {field: "" for field in FIELDS}
    base.update({
        "row_id": "BJ-0001",
        "city": "北京",
        "district": "东城区",
        "category": "景点与文博",
        "subcategory": "博物馆",
        "name_zh": "测试博物馆",
        "name_en": "Test Museum",
        "name_en_type": "机器翻译",
        "address_zh": "未知",
        "source_name": "测试目录",
        "source_type": "政府目录",
        "source_url": "https://example.com/list",
        "collected_on": "2026-11-18",
        "review_status": "待复核",
        "notes": "机器翻译，待复核",
    })
    base.update(overrides)
    return base


class SevenCityPoiTests(unittest.TestCase):
    def write(self, rows):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
        with handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return Path(handle.name)

    def test_valid_row(self):
        validate_row(row(), as_of=AS_OF, source="test")
        path = self.write([row()])
        self.assertEqual(len(validate_file(path, as_of=AS_OF)), 1)

    def test_published_english_requires_url(self):
        with self.assertRaisesRegex(ValueError, "direct URL"):
            validate_row(row(name_en_type="官方英文"), as_of=AS_OF, source="test")
        validate_row(row(name_en_type="官方英文", name_en_source_url="https://example.com/en"),
                     as_of=AS_OF, source="test")

    def test_machine_english_must_not_claim_url(self):
        with self.assertRaisesRegex(ValueError, "must not claim"):
            validate_row(row(name_en_source_url="https://example.com/en"), as_of=AS_OF, source="test")

    def test_subcategory_must_match_category(self):
        with self.assertRaisesRegex(ValueError, "not allowed"):
            validate_row(row(subcategory="购物中心"), as_of=AS_OF, source="test")

    def test_row_id_prefix_must_match_city(self):
        with self.assertRaisesRegex(ValueError, "prefix"):
            validate_row(row(city="上海"), as_of=AS_OF, source="test")

    def test_duplicate_row_id_is_rejected(self):
        path = self.write([row(), row()])
        with self.assertRaisesRegex(ValueError, "duplicate row_id"):
            validate_file(path, as_of=AS_OF)

    def test_future_collection_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "future"):
            validate_row(row(collected_on="2026-11-19"), as_of=AS_OF, source="test")

    def test_combined_file_can_ship_with_city_files(self):
        prefixes = {"北京": "BJ", "上海": "SH", "广州": "GZ", "深圳": "SZ",
                    "成都": "CD", "重庆": "CQ", "桂林": "GL"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for city, prefix in prefixes.items():
                item = row(row_id=f"{prefix}-0001", city=city)
                rows.append(item)
                self.write_to(root / f"{prefix}.csv", [item])
            self.write_to(root / "all-cities.csv", rows)
            argv = [str(root / n) for n in
                    ["BJ.csv", "SH.csv", "GZ.csv", "SZ.csv", "CD.csv", "CQ.csv", "GL.csv", "all-cities.csv"]]
            self.assertEqual(main(argv + ["--as-of", "2026-11-18"]), 0)

    def test_combined_file_must_match_city_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            city = self.write_to(root / "BJ.csv", [row(row_id="BJ-0001")])
            combined = self.write_to(root / "all-cities.csv", [row(row_id="BJ-0002")])
            self.assertEqual(main([str(city), str(combined), "--as-of", "2026-11-18"]), 1)

    def write_to(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_wrong_header_is_rejected(self):
        path = self.write([row()])
        rows = load_rows(path)
        self.assertEqual(set(rows[0]), set(FIELDS))


if __name__ == "__main__":
    unittest.main()
