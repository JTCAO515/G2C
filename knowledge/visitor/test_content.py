from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
import unittest

from validate import CITIES, TOPICS, load_entries

ROOT = Path(__file__).resolve().parent


class FirstBatchTests(unittest.TestCase):
    def test_first_batch_format_and_all_35_city_topic_cells(self):
        entries = load_entries(sorted((ROOT / "entries").glob("*.json")),
                               as_of=date(2026, 11, 12))
        self.assertEqual(len(entries), 12)
        actual = {(city, entry["topic"]) for entry in entries for city in entry["cities"]}
        self.assertEqual(actual, {(city, topic) for city in CITIES for topic in TOPICS})
        self.assertTrue(all(not entry["id"].startswith("visitor.example.") for entry in entries))

    def test_sources_stay_within_the_confirmed_host_inventory(self):
        # This checks catalog consistency; JT's approval is linked in SOURCES.md.
        hosts = {urlsplit(line.split("|")[2].strip()).hostname
                 for line in (ROOT / "SOURCES.md").read_text().splitlines()
                 if line.startswith("| ") and line.split("|")[2].strip().startswith("https://")}
        entries = load_entries(sorted((ROOT / "entries").glob("*.json")),
                               as_of=date(2026, 11, 12))
        for entry in entries:
            for url in entry["source_urls"]:
                with self.subTest(id=entry["id"], url=url):
                    self.assertIn(urlsplit(url).hostname, hosts)


if __name__ == "__main__":
    unittest.main()
