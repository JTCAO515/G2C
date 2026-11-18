import copy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from validate_tools import FIELDS, load_tools, validate_tool

TODAY = date(2026, 11, 18)
ROOT = Path(__file__).resolve().parent


def make_tool(**overrides):
    record = {
        "format_version": "visitor-tool.1",
        "id": "tool.2026-11-18.alipay",
        "name_zh": "支付宝",
        "name_en": "Alipay",
        "category": "payment",
        "operator": "蚂蚁集团（支付宝）",
        "platform": "手机 App（iOS/Android）；网页",
        "purpose_zh": "候选概括，待核实。",
        "cities": ["nationwide"],
        "interface_languages": ["中文"],
        "preparation": ["境外手机号", "境外银行卡"],
        "official_links": [{
            "name": "支付宝官网",
            "url": "https://www.alipay.com/",
            "type": "official_site",
        }],
        "sources": [{
            "name": "上海市政府英文站",
            "url": "https://english.shanghai.gov.cn/en-FAQs-StudyinShanghai/20231211/a58d4c15179f468fb2c5d72b393f1fd4.html",
            "type": "official_government",
            "language": "en",
            "published_on": "2023-12-11",
            "valid_until": None,
        }],
        "collected_on": "2026-11-18",
        "status": "待核实",
        "missing": ["英文界面未核实"],
        "notes": "仅记录公开页面可见的概括。",
        "conflicts": [],
        "related_entries": ["visitor.mainland.payment-options"],
    }
    record.update(overrides)
    return record


class ToolFormatTests(unittest.TestCase):
    def setUp(self):
        self.record = make_tool()

    def test_valid_record(self):
        validate_tool(self.record, as_of=TODAY)

    def test_each_required_field_missing(self):
        for field in FIELDS:
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                del record[field]
                with self.assertRaises(ValueError):
                    validate_tool(record, as_of=TODAY)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            validate_tool({**self.record, "verified": True}, as_of=TODAY)

    def test_version_and_status(self):
        for field, value in (("format_version", "visitor-tool.2"),
                             ("status", "verified")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_tool(make_tool(**{field: value}), as_of=TODAY)

    def test_id_shape_and_date(self):
        for value in (None, "", "tool.alipay", "visitor.2026-11-18.alipay",
                      "tool.2026-11-17.alipay"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_tool(make_tool(id=value), as_of=TODAY)

    def test_collected_date(self):
        validate_tool(self.record, as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_tool(make_tool(collected_on="2026-11-19",
                                    id="tool.2026-11-19.alipay"), as_of=TODAY)
        for value in (None, "2026-1-1", "2026-02-30"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_tool(make_tool(collected_on=value), as_of=TODAY)

    def test_names_operator_platform_and_purpose(self):
        for field in ("name_zh", "name_en", "operator", "platform", "purpose_zh"):
            for value in ("", "  ", "\ud800"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_tool(make_tool(**{field: value}), as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_tool(make_tool(purpose_zh="字" * 601), as_of=TODAY)

    def test_category(self):
        for value in (None, "", "app", "支付", "other"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_tool(make_tool(category=value), as_of=TODAY)

    def test_cities_languages_and_preparation(self):
        for field, values in (
                ("cities", [[], "nationwide", ["unknown"], ["nationwide", "nationwide"], [None]]),
                ("interface_languages", [[], "中文", [""], ["中文", "中文"]]),
                ("preparation", [[], "护照", [""], ["护照", "护照"]])):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_tool(make_tool(**{field: value}), as_of=TODAY)

    def test_official_links(self):
        validate_tool(make_tool(official_links=[]), as_of=TODAY)
        valid = self.record["official_links"][0]
        for value in ("x", [valid, valid],
                      [{**valid, "url": "ftp://www.alipay.com/"}],
                      [{**valid, "url": "https://www.alipay.com/#a"}],
                      [{**valid, "type": "official"}],
                      [{"name": "x", "url": "https://example.com/"}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_tool(make_tool(official_links=value), as_of=TODAY)

    def test_sources(self):
        valid = self.record["sources"][0]
        for value in ([], "https://example.com/", [valid, valid],
                      [{**valid, "url": "ftp://example.com/"}],
                      [{**valid, "url": "https://example.com/#a"}],
                      [{**valid, "type": "official"}],
                      [{"name": "x", "url": "https://example.com/", "type": "official_tool",
                        "language": "en"}],
                      [{**valid, "published_on": "2026-11-19"}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_tool(make_tool(sources=value), as_of=TODAY)
        validate_tool(make_tool(sources=[{
            "name": "仅有 HTTP 的官方页", "url": "http://www.alipay.com/",
            "type": "official_tool", "language": "zh",
            "published_on": None, "valid_until": None}]), as_of=TODAY)
        for url in ("https://user:password@example.com/", "https://example.com:8443/",
                    " http://example.com/", "https://example.com/\n", "example.com"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_tool(make_tool(sources=[{
                    "name": "x", "url": url, "type": "official_tool",
                    "language": "zh", "published_on": None, "valid_until": None,
                }]), as_of=TODAY)

    def test_missing_notes_conflicts_related(self):
        validate_tool(make_tool(missing=[], notes=None, conflicts=[]), as_of=TODAY)
        for field, value in (("missing", None), ("missing", [""]), ("missing", "未知"),
                             ("notes", ""), ("notes", " "), ("conflicts", None),
                             ("conflicts", [""]), ("related_entries", None),
                             ("related_entries", ["candidate.x"])):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_tool(make_tool(**{field: value}), as_of=TODAY)

    def test_file_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tools.json"
            for raw in ["{", "{}", "[]", '[{"id":"one","id":"two"}]', "[NaN]",
                        json.dumps([self.record, self.record])]:
                path.write_text(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    load_tools([path], as_of=TODAY)
            path.write_text(json.dumps([self.record]))
            with self.assertRaisesRegex(ValueError, "duplicate id"):
                load_tools([path, path], as_of=TODAY)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tools.json"
            path.write_text(json.dumps([self.record]))
            result = subprocess.run(
                [sys.executable, "-B", str(ROOT / "validate_tools.py"),
                 "--as-of", "2026-11-18", str(path)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS: 1 tool candidate records", result.stdout)
            path.write_text(json.dumps([make_tool(status="verified")]))
            result = subprocess.run(
                [sys.executable, "-B", str(ROOT / "validate_tools.py"),
                 "--as-of", "2026-11-18", str(path)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL:", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
