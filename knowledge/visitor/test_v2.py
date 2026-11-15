import copy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from validate import load_entries, validate_entry
from validate import CITIES
from validate_v2 import CONDITION_FIELDS, load_entries_v2, validate_entry_v2
from validate_names import load_names, validate_name

ROOT = Path(__file__).resolve().parent
TODAY = date(2026, 11, 13)


class ConditionsTests(unittest.TestCase):
    def setUp(self):
        self.entry = json.loads((ROOT / "examples/conditions-v2.json").read_text())[0]

    def test_known_unknown_and_no_reservation_examples(self):
        values = load_entries_v2([ROOT / "examples/conditions-v2.json"], as_of=TODAY)
        self.assertEqual(len(values), 3)
        self.assertEqual(values[0]["conditions"]["closed_weekdays"], [1])
        self.assertIsNone(values[1]["conditions"]["closed_weekdays"])
        self.assertEqual(values[2]["conditions"]["closed_weekdays"], [])
        self.assertIs(values[2]["conditions"]["reservation_required"], False)

    def test_missing_fields_and_unknown_keys_rejected(self):
        for key in self.entry:
            value = copy.deepcopy(self.entry)
            del value[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_entry_v2(value, as_of=TODAY)
        for key in CONDITION_FIELDS:
            value = copy.deepcopy(self.entry)
            del value["conditions"][key]
            with self.subTest(condition=key), self.assertRaises(ValueError):
                validate_entry_v2(value, as_of=TODAY)
        for target in ("entry", "subject", "conditions"):
            value = copy.deepcopy(self.entry)
            (value if target == "entry" else value[target])["coordinates"] = [1, 2]
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_entry_v2(value, as_of=TODAY)

    def test_invalid_condition_types_and_inconsistent_meaning(self):
        cases = [
            {"reservation_required": "yes"}, {"reservation_required": 1},
            {"closed_weekdays": [0]}, {"closed_weekdays": [8]}, {"closed_weekdays": [True]},
            {"closed_weekdays": [1, 1]}, {"closed_weekdays": "Monday"},
            {"closed_weekdays": None}, {"closed_weekdays_public_holiday_exception": None},
            {"closed_weekdays": [], "closed_weekdays_public_holiday_exception": True},
            {"advance_booking_days": True}, {"advance_booking_days": -1},
            {"advance_booking_days": 1.5}, {"advance_booking_days": "7"},
            {"advance_booking_rule": None}, {"advance_booking_rule": "guess"},
            {"advance_booking_days": None},
            {"reservation_required": False}, {"reservation_required": None},
        ]
        for changes in cases:
            value = copy.deepcopy(self.entry)
            value["conditions"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_entry_v2(value, as_of=TODAY)

    def test_old_reader_and_old_catalog_are_preserved(self):
        with self.assertRaises(ValueError):
            validate_entry(self.entry, as_of=TODAY)
        legacy = load_entries(sorted((ROOT / "entries").glob("*.json")), as_of=TODAY)
        self.assertEqual(len(legacy), 12)
        with self.assertRaises(ValueError):
            validate_entry_v2(legacy[0], as_of=TODAY)

    def test_real_optional_booking_window_is_not_a_minimum_lead_requirement(self):
        entries = load_entries_v2(sorted((ROOT / "entries-v2").glob("*.json")), as_of=TODAY)
        self.assertEqual(len(entries), 3)
        venue = next(entry for entry in entries if entry["entry_kind"] == "fact")
        self.assertIs(venue["conditions"]["reservation_required"], False)
        self.assertEqual(venue["conditions"]["advance_booking_days"], 7)
        self.assertEqual(venue["conditions"]["advance_booking_rule"], "window_max")
        self.assertEqual(venue["conditions"]["closed_weekdays"], [1])
        self.assertIs(venue["conditions"]["closed_weekdays_public_holiday_exception"], True)
        channels = [entry for entry in entries if entry["entry_kind"] == "official_channel"]
        self.assertEqual(len(channels), 2)
        self.assertTrue(all(value is None for entry in channels for value in entry["conditions"].values()))

    def test_official_channel_is_not_a_visa_eligibility_fact(self):
        value = copy.deepcopy(self.entry)
        value.update(entry_kind="official_channel", topic="visa_entry", subject=None,
                     source_urls=["https://www.nia.gov.cn/n741440/n741577/index.html"],
                     conditions={key: None for key in CONDITION_FIELDS})
        validate_entry_v2(value, as_of=TODAY)
        for changes in ({"entry_kind": "fact"},
                        {"source_urls": ["https://www.beijing.gov.cn/"]},
                        {"source_urls": ["https://www.wikidata.org/wiki/Q1"]},
                        {"conditions": {**value["conditions"], "reservation_required": False}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_entry_v2({**value, **changes}, as_of=TODAY)

    def test_strict_file_boundary_and_expiry_still_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.json"
            for raw in ('[{"id":"a","id":"b"}]', "[NaN]", json.dumps([self.entry, self.entry])):
                path.write_text(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    load_entries_v2([path], as_of=TODAY)
            path.write_text(json.dumps([self.entry]))
            with self.assertRaisesRegex(ValueError, "expired"):
                load_entries_v2([path], as_of=date(2026, 11, 27))


class NameFormatTests(unittest.TestCase):
    def setUp(self):
        self.name = json.loads((ROOT / "examples/names-format.json").read_text())[0]

    def test_synthetic_name_format(self):
        self.assertEqual(len(load_names([ROOT / "examples/names-format.json"], as_of=TODAY)), 1)

    def test_reviewed_names_cover_seven_cities(self):
        records = load_names(sorted((ROOT / "names").glob("*.json")), as_of=TODAY)
        self.assertEqual(len(records), 7)
        self.assertEqual({city for record in records for city in record["cities"]}, CITIES)
        self.assertTrue(all(not record["id"].startswith("visitor.example.") for record in records))

    def test_name_review_includes_all_labels_at_the_30_day_boundary(self):
        paths = sorted((ROOT / "names").glob("*.json"))
        result = subprocess.run([sys.executable, "-B", str(ROOT / "review_due.py"),
                                 "--format", "names", "--as-of", "2027-01-12", *map(str, paths)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["count"], 7)
        expected = load_names(paths, as_of=date(2027, 1, 12))
        self.assertEqual({entry["wikidata_qid"] for entry in report["entries"]},
                         {entry["wikidata_qid"] for entry in expected})
        self.assertTrue(all(entry["expires_on"] == "2027-02-11" for entry in report["entries"]))

    def test_duplicate_place_key_or_qid_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "names.json"
            duplicate_qid = {**self.name, "id": "visitor.example.other", "place_key": "other.place"}
            duplicate_key = {**self.name, "id": "visitor.example.other", "wikidata_qid": "Q2",
                             "source_urls": ["https://www.wikidata.org/wiki/Q2"]}
            for other in (duplicate_qid, duplicate_key):
                path.write_text(json.dumps([self.name, other]))
                with self.subTest(other=other), self.assertRaisesRegex(ValueError, "duplicate name"):
                    load_names([path], as_of=TODAY)

    def test_missing_labels_qid_source_mismatch_license_and_coordinates(self):
        changes = [
            {"wikidata_qid": "q1"}, {"wikidata_qid": "Q0"}, {"wikidata_qid": None},
            {"name_zh": ""}, {"name_en": None}, {"license": "unknown"},
            {"source_urls": ["https://www.wikidata.org/wiki/Q2"]},
            {"source_urls": ["https://query.wikidata.org/"]},
            {"coordinates": [1, 2]}, {"latitude": 1}, {"longitude": 2},
        ]
        for patch in changes:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_name({**self.name, **patch}, as_of=TODAY)
        for key in self.name:
            value = dict(self.name)
            del value[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                validate_name(value, as_of=TODAY)

    def test_review_report_keeps_new_fields_and_qid_without_enabling_old_reader(self):
        cases = [("v2", ROOT / "examples/conditions-v2.json", "conditions"),
                 ("names", ROOT / "examples/names-format.json", "wikidata_qid")]
        for record_format, path, key in cases:
            args = [sys.executable, "-B", str(ROOT / "review_due.py"), "--as-of", TODAY.isoformat(),
                    "--format", record_format, str(path)]
            result = subprocess.run(args, capture_output=True, text=True)
            with self.subTest(record_format=record_format):
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["record_format"], record_format)
                self.assertIn(key, report["entries"][0])
                original = json.loads(path.read_text())[0]
                self.assertEqual(report["entries"][0][key], original[key])
                old = subprocess.run([*args[:5], str(path)], capture_output=True, text=True)
                self.assertNotEqual(old.returncode, 0)


if __name__ == "__main__":
    unittest.main()
