import copy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from validate import FIELDS, load_entries, validate_entry

ROOT = Path(__file__).resolve().parent
TODAY = date(2026, 11, 12)


class VisitorFormatTests(unittest.TestCase):
    def setUp(self):
        self.entry = json.loads((ROOT / "examples/format.json").read_text())[0]

    def test_three_examples(self):
        self.assertEqual(len(load_entries([ROOT / "examples/format.json"], as_of=TODAY)), 3)

    def test_each_required_field_missing(self):
        for field in FIELDS:
            with self.subTest(field=field):
                entry = copy.deepcopy(self.entry)
                del entry[field]
                with self.assertRaises(ValueError):
                    validate_entry(entry, as_of=TODAY)

    def test_bad_field_values(self):
        cases = {
            "id": [None, "", "other.payment"],
            "topic": [[], "visa", ""],
            "cities": [[], "beijing", ["unknown"], ["beijing", "beijing"], [None]],
            "text_zh": [None, "", "  ", "\ud800"],
            "text_en": [None, "", "  ", "\udfff"],
            "source_urls": [[], "https://example.com/", [None], ["http://example.com/"],
                            ["https://user:password@example.com/"], ["https://example.com/#part"],
                            ["https://example.com:bad/"], ["https://example.com/\n"],
                            ["https://example.com/", "https://example.com/"]],
            "checked_on": [None, "20261112", "2026-1-12", "2026-02-30", "2026-11-13"],
            "expires_on": [None, "20261212", "2026-2-01", "2026-02-30", "2026-11-12", "2026-11-11"],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    entry = copy.deepcopy(self.entry)
                    entry[field] = value
                    with self.assertRaises(ValueError):
                        validate_entry(entry, as_of=TODAY)

    def test_unknown_field_and_wrong_entry_shape(self):
        for entry in ([], None, {**self.entry, "approved": True}):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                validate_entry(entry, as_of=TODAY)

    def test_expiry_day_is_exclusive(self):
        validate_entry(self.entry, as_of=date(2026, 12, 11))
        for day in (date(2026, 12, 12), date(2026, 12, 13)):
            with self.subTest(day=day), self.assertRaisesRegex(ValueError, "expired"):
                validate_entry(self.entry, as_of=day)

    def test_file_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "entries.json"
            cases = ["{", "{}", "[]", '[{"id":"one","id":"two"}]', "[NaN]",
                     json.dumps([self.entry, self.entry])]
            for raw in cases:
                path.write_text(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    load_entries([path], as_of=TODAY)
            path.write_text(json.dumps([self.entry]))
            with self.assertRaisesRegex(ValueError, "duplicate id"):
                load_entries([path, path], as_of=TODAY)
            path.write_bytes(b"\xff")
            with self.assertRaises(ValueError):
                load_entries([path], as_of=TODAY)
            path.unlink()
            with self.assertRaises(ValueError):
                load_entries([path], as_of=TODAY)

    def test_cli_success_and_expired_failure(self):
        for day, expected in (("2026-11-12", 0), ("2026-12-12", 1)):
            result = subprocess.run([sys.executable, "-B", str(ROOT / "validate.py"),
                                     "--as-of", day, str(ROOT / "examples/format.json")],
                                    capture_output=True, text=True)
            with self.subTest(day=day):
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertIn("PASS:" if expected == 0 else "FAIL:", result.stdout + result.stderr)
                if expected:
                    self.assertNotIn("PASS:", result.stdout)


if __name__ == "__main__":
    unittest.main()
