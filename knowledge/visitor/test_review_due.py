from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from review_due import expiring_entries
from validate import load_entries

ROOT = Path(__file__).resolve().parent
TODAY = date(2026, 11, 12)


class ReviewDueTests(unittest.TestCase):
    def setUp(self):
        self.example = json.loads((ROOT / "examples/format.json").read_text())[0]

    def entry(self, name, days):
        return {**self.example, "id": f"visitor.test.{name}",
                "expires_on": (TODAY + timedelta(days=days)).isoformat()}

    def test_day_30_included_day_31_excluded_and_stable_order(self):
        entries = [self.entry("outside", 31), self.entry("z", 30),
                   self.entry("tomorrow", 1), self.entry("a", 30)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "entries.json"
            path.write_text(json.dumps(entries))
            valid = load_entries([path], as_of=TODAY)
        self.assertEqual([entry["id"] for entry in expiring_entries(valid, as_of=TODAY)],
                         ["visitor.test.tomorrow", "visitor.test.a", "visitor.test.z"])

    def test_no_due_entries_is_an_explicit_empty_report(self):
        self.assertEqual(expiring_entries([self.entry("later", 31)], as_of=TODAY), [])

    def test_cli_rejects_expired_and_invalid_files_without_partial_success(self):
        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / "good.json"
            bad = Path(directory) / "bad.json"
            good.write_text(json.dumps([self.entry("valid", 1)]))
            for payload in ([self.entry("expired", 0)], [{"id": "missing-fields"}]):
                bad.write_text(json.dumps(payload))
                result = subprocess.run([sys.executable, "-B", str(ROOT / "review_due.py"),
                                         "--as-of", TODAY.isoformat(), str(good), str(bad)],
                                        capture_output=True, text=True)
                with self.subTest(payload=payload):
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("FAIL:", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_real_batch_cli_reports_ten_due_entries(self):
        paths = sorted((ROOT / "entries").glob("*.json"))
        result = subprocess.run([sys.executable, "-B", str(ROOT / "review_due.py"),
                                 "--as-of", TODAY.isoformat(), *map(str, paths)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["count"], 10)
        self.assertEqual(report["window_days"], 30)
        self.assertEqual(report["as_of"], "2026-11-12")
        self.assertEqual(report["entries"][0]["expires_on"], "2026-11-26")
        self.assertEqual(report["entries"][-1]["expires_on"], "2026-12-12")


if __name__ == "__main__":
    unittest.main()
