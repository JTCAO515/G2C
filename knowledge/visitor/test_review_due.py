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

    def run_cli(self, *paths, record_format="legacy"):
        return subprocess.run([sys.executable, "-B", str(ROOT / "review_due.py"), "--format", record_format,
                               "--as-of", TODAY.isoformat(), *map(str, paths)], capture_output=True, text=True)

    def test_cli_rejects_invalid_files_without_partial_success(self):
        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / "good.json"
            bad = Path(directory) / "bad.json"
            good.write_text(json.dumps([self.entry("valid", 1)]))
            expired_bad_source = {**self.entry("expired-bad", 0), "source_urls": ["http://example.com/"]}
            future_check = {**self.entry("future", 5), "checked_on": (TODAY + timedelta(days=1)).isoformat()}
            for payload in ([{"id": "missing-fields"}], [expired_bad_source], [future_check]):
                bad.write_text(json.dumps(payload))
                result = self.run_cli(good, bad)
                with self.subTest(payload=payload):
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("FAIL:", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_cli_lists_expired_entries_instead_of_failing(self):
        """#1757: the review tool reports what expired; readers still refuse those entries."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "entries.json"
            earlier = (TODAY - timedelta(days=60)).isoformat()
            path.write_text(json.dumps([{**self.entry("today", 0), "checked_on": earlier},
                                        self.entry("tomorrow", 1),
                                        {**self.entry("long-ago", -40), "checked_on": earlier}]))
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual([e["id"] for e in report["entries"]], ["visitor.test.tomorrow"])
            self.assertEqual(report["count"], 1)
            self.assertEqual(report["expired_count"], 2)
            self.assertEqual([e["id"] for e in report["expired"]], ["visitor.test.long-ago", "visitor.test.today"])
            with self.assertRaisesRegex(ValueError, "expired"):
                load_entries([path], as_of=TODAY)

    def test_every_format_lists_its_expired_entries(self):
        cases = (("v2", "examples/conditions-v2.json"), ("names", "examples/names-format.json"))
        for record_format, name in cases:
            record = json.loads((ROOT / name).read_text())[0]
            with self.subTest(record_format=record_format), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "records.json"
                path.write_text(json.dumps([{**record, "expires_on": TODAY.isoformat(),
                                             "checked_on": (TODAY - timedelta(days=10)).isoformat()}]))
                result = self.run_cli(path, record_format=record_format)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["expired_count"], 1)

    def test_real_batch_cli_reports_ten_due_entries(self):
        paths = sorted((ROOT / "entries").glob("*.json"))
        result = subprocess.run([sys.executable, "-B", str(ROOT / "review_due.py"),
                                 "--as-of", "2026-11-26", *map(str, paths)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["count"], 10)
        self.assertEqual(report["window_days"], 30)
        self.assertEqual(report["as_of"], "2026-11-26")
        self.assertEqual(report["entries"][0]["expires_on"], "2026-12-10")
        self.assertEqual(report["entries"][-1]["expires_on"], "2026-12-26")


if __name__ == "__main__":
    unittest.main()
