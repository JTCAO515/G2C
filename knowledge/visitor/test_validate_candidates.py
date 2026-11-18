import copy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from validate_candidates import FIELDS, load_candidates, validate_candidate

TODAY = date(2026, 11, 18)
ROOT = Path(__file__).resolve().parent


def make_candidate(**overrides):
    record = {
        "format_version": "visitor-candidate.1",
        "id": "candidate.2026-11-18.guangzhou.canton-tower",
        "title_zh": "广州塔：分时段登塔与实名购票（候选）",
        "summary_zh": "候选概括，待核实。",
        "cities": ["guangzhou"],
        "place": {"name_zh": "广州塔", "name_en": "Canton Tower", "address": None},
        "audience": ["普通散客"],
        "themes": ["attraction", "passport_booking"],
        "sources": [{
            "name": "广州塔官网",
            "url": "https://www.cantontower.com/",
            "type": "official_venue",
            "language": "zh",
            "published_on": None,
            "valid_until": None,
        }],
        "collected_on": "2026-11-18",
        "status": "待核实",
        "missing": ["固定闭馆日"],
        "notes": "仅记录页面可见的参观说明。",
        "conflicts": [],
        "related_entries": ["visitor.mainland.rail-passport"],
    }
    record.update(overrides)
    return record


class CandidateFormatTests(unittest.TestCase):
    def setUp(self):
        self.record = make_candidate()

    def test_valid_record(self):
        validate_candidate(self.record, as_of=TODAY)

    def test_place_may_be_null(self):
        validate_candidate(make_candidate(place=None), as_of=TODAY)

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
        for field, value in (("format_version", "visitor-candidate.2"), ("status", "verified")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_candidate(make_candidate(**{field: value}), as_of=TODAY)

    def test_id_shape_and_date(self):
        for value in (None, "", "candidate.guangzhou", "visitor.2026-11-18.x",
                      "candidate.2026-11-17.guangzhou.canton-tower"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(id=value), as_of=TODAY)

    def test_collected_date(self):
        self.assertEqual(validate_candidate(self.record, as_of=TODAY), None)
        with self.assertRaises(ValueError):
            validate_candidate(make_candidate(collected_on="2026-11-19",
                                              id="candidate.2026-11-19.guangzhou.canton-tower"), as_of=TODAY)
        for value in (None, "2026-1-1", "2026-02-30"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(collected_on=value), as_of=TODAY)

    def test_title_and_summary(self):
        for field in ("title_zh", "summary_zh"):
            for value in ("", "  ", "\ud800"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_candidate(make_candidate(**{field: value}), as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_candidate(make_candidate(summary_zh="字" * 601), as_of=TODAY)

    def test_cities(self):
        for value in ([], "guangzhou", ["unknown"], ["guangzhou", "guangzhou"], [None]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(cities=value), as_of=TODAY)

    def test_audience_and_themes(self):
        for field, values in (
                ("audience", [[], "普通散客", [""], ["普通散客", "普通散客"]]),
                ("themes", [[], "attraction", ["visa"], ["attraction", "attraction"]])):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_candidate(make_candidate(**{field: value}), as_of=TODAY)

    def test_place_shape(self):
        for value in ({}, {"name_zh": "广州塔"}, {"name_zh": "", "name_en": None, "address": None},
                      {"name_zh": "广州塔", "name_en": None, "address": None, "lat": 1.0},
                      {"name_zh": "广州塔", "name_en": "Canton Tower", "address": " "}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(place=value), as_of=TODAY)

    def test_sources(self):
        valid = self.record["sources"][0]
        for value in ([], "https://www.cantontower.com/", [valid, valid],
                      [{**valid, "url": "ftp://www.cantontower.com/"}],
                      [{**valid, "url": "https://www.cantontower.com/#a"}],
                      [{**valid, "type": "official"}],
                      [{"name": "x", "url": "https://example.com/", "type": "other_public",
                        "language": "zh"}],
                      [{**valid, "published_on": "2026-11-19"}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(sources=value), as_of=TODAY)

    def test_source_url_schemes(self):
        validate_candidate(make_candidate(sources=[{
            "name": "仅有 HTTP 的官方页", "url": "http://www.cnhhl.com/index.php/list-12.html",
            "type": "official_venue", "language": "zh",
            "published_on": None, "valid_until": None}]), as_of=TODAY)
        for url in ("https://user:password@example.com/", "https://example.com:8443/",
                    " http://example.com/", "https://example.com/\n", "example.com"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_candidate(make_candidate(sources=[{
                    "name": "x", "url": url, "type": "official_venue", "language": "zh",
                    "published_on": None, "valid_until": None}]), as_of=TODAY)

    def test_missing_and_notes(self):
        validate_candidate(make_candidate(missing=[], notes=None, conflicts=[]), as_of=TODAY)
        for field, value in (("missing", None), ("missing", [""]), ("missing", "未知"),
                             ("notes", ""), ("notes", " "), ("conflicts", None),
                             ("conflicts", [""]), ("related_entries", None),
                             ("related_entries", ["candidate.x"])):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_candidate(make_candidate(**{field: value}), as_of=TODAY)

    def test_file_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.json"
            for raw in ["{", "{}", "[]", '[{"id":"one","id":"two"}]', "[NaN]",
                        json.dumps([self.record, self.record])]:
                path.write_text(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    load_candidates([path], as_of=TODAY)
            path.write_text(json.dumps([self.record]))
            with self.assertRaisesRegex(ValueError, "duplicate id"):
                load_candidates([path, path], as_of=TODAY)
            path.write_text(json.dumps([make_candidate(id="candidate.2026-11-18.shanghai.yuyuan",
                                                       cities=["shanghai"])]))
            self.assertEqual(len(load_candidates([path], as_of=TODAY)), 1)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.json"
            path.write_text(json.dumps([self.record]))
            result = subprocess.run([sys.executable, "-B", str(ROOT / "validate_candidates.py"),
                                     "--as-of", "2026-11-18", str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS: 1 candidate records", result.stdout)
            path.write_text(json.dumps([make_candidate(status="verified")]))
            result = subprocess.run([sys.executable, "-B", str(ROOT / "validate_candidates.py"),
                                     "--as-of", "2026-11-18", str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL:", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
