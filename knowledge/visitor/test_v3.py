from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
import subprocess
import sys
import unittest
from zoneinfo import ZoneInfo

from review_due import FORMATS, expiring_entries
from validate import CITIES, TOPICS, validate_entry
from validate_names import validate_name
from validate_v2 import validate_entry_v2
from validate_v3 import V3_CITIES, load_entries_v3, validate_entry_v3

ROOT = Path(__file__).resolve().parent
TODAY = date(2026, 11, 20)


class NineCityContentTests(unittest.TestCase):
    def setUp(self):
        self.observed_on = datetime.now(ZoneInfo('Asia/Shanghai')).date()
        self.records = load_entries_v3(sorted((ROOT / 'entries-v3').glob('*.json')), as_of=self.observed_on)
        self.entry = deepcopy(self.records[0])
        # Boundary probes retain their fixed clock; the real catalog is checked above.
        self.entry.update(checked_on=TODAY.isoformat(), expires_on='2026-12-16')

    def test_new_city_first_visit_cells_and_explicit_unknown_conditions(self):
        basics = [e for e in self.records if e['id'].startswith('visitor.v3.taizhou-suzhou.')]
        actual = {(city, e['topic']) for e in basics for city in e['cities']}
        self.assertEqual(actual, {(city, topic) for city in V3_CITIES - CITIES for topic in TOPICS})
        self.assertTrue(all(e['subject'] is None for e in basics))
        self.assertTrue(all(v is None for e in basics for v in e['conditions'].values()))

    def test_old_formats_do_not_silently_accept_new_cities_or_version(self):
        legacy = json.loads((ROOT / 'examples/format.json').read_text())[0]
        v2 = json.loads((ROOT / 'examples/conditions-v2.json').read_text())[0]
        name = json.loads((ROOT / 'examples/names-format.json').read_text())[0]
        for record, validator in ((legacy, validate_entry), (v2, validate_entry_v2), (name, validate_name)):
            for city in V3_CITIES - CITIES:
                with self.subTest(validator=validator.__name__, city=city), self.assertRaises(ValueError):
                    validator({**record, 'cities': [city]}, as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_entry_v2(self.entry, as_of=TODAY)

    def test_city_wide_facts_cannot_publish_venue_booking_or_closure_rules(self):
        for key, value in [('reservation_required', False), ('closed_weekdays', [])]:
            entry = deepcopy(self.entry)
            entry['conditions'][key] = value
            if key == 'closed_weekdays':
                entry['conditions']['closed_weekdays_public_holiday_exception'] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_entry_v3(entry, as_of=TODAY)

    def test_explicit_place_conditions_preserve_optional_booking_meaning(self):
        entry = json.loads((ROOT / 'entries-v2/venue-conditions.json').read_text())[0]
        entry['format_version'] = 'visitor-entry.3'
        validate_entry_v3(entry, as_of=self.observed_on)
        self.assertFalse(entry['conditions']['reservation_required'])
        self.assertEqual(entry['conditions']['advance_booking_rule'], 'window_max')

    def test_new_host_approvals_do_not_expand_topic_city_or_subdomain_scope(self):
        for url in ['https://www.gov.cn/news/example.html', 'https://www.zjtz.gov.cn/example.html',
                    'https://www.ahsz.gov.cn/example.html', 'https://other.zjtz.gov.cn/example.html']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_entry_v3({**self.entry, 'source_urls': [url]}, as_of=TODAY)
        channel = {**self.entry, 'topic': 'seasonal_holiday', 'entry_kind': 'official_channel',
                   'source_urls': ['https://www.gov.cn/zhengce/holiday-example.html']}
        validate_entry_v3(channel, as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_entry_v3({**channel, 'topic': 'visa_entry'}, as_of=TODAY)
        channel.update(topic='visa_entry', source_urls=['https://www.nia.gov.cn/index.html'])
        validate_entry_v3(channel, as_of=TODAY)
        with self.assertRaises(ValueError):
            validate_entry_v3({**channel, 'entry_kind': 'fact'}, as_of=TODAY)

    def test_date_city_shape_and_version_boundaries_remain_strict(self):
        for patch in [{'cities': ['suzhou']}, {'cities': ['taizhou']},
                      {'checked_on': '2026-11-21'}, {'expires_on': '2026-11-19'},
                      {'expires_on': TODAY.isoformat()},
                      {'format_version': 'visitor-entry.2'}, {'extra': True}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_entry_v3({**self.entry, **patch}, as_of=TODAY)

    def test_v3_review_retains_scope_fields_and_old_cli_default(self):
        self.assertEqual(FORMATS['legacy'][0].__name__, 'load_entries')
        paths = sorted((ROOT / 'entries-v3').glob('*.json'))
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'review_due.py'),
                                 '--format', 'v3', '--as-of', self.observed_on.isoformat(), *map(str, paths)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        expected = expiring_entries(self.records, as_of=self.observed_on)
        self.assertEqual(report['count'], len(expected))
        for value in report['entries']:
            original = next(e for e in expected if e['id'] == value['id'])
            self.assertEqual(value, {k: original[k] for k in FORMATS['v3'][1]})


if __name__ == '__main__':
    unittest.main()
