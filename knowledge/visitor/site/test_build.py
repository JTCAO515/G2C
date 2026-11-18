"""Tests for the Pages artifact's input boundary."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from build import GROUPS, VISITOR, build, read_records


class PagesDataTests(unittest.TestCase):
    def setUp(self):
        self.today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.visitor = Path(self.tmp.name)
        for directory, _ in GROUPS:
            shutil.copytree(VISITOR / directory, self.visitor / directory)

    def test_reads_each_formal_format_without_examples(self):
        records = read_records(self.visitor, self.today)
        expected = sum(len(json.loads(path.read_text(encoding='utf-8')))
                       for directory, _ in GROUPS for path in (self.visitor / directory).glob('*.json'))
        self.assertEqual(len(records), expected)
        self.assertEqual(len({record['id'] for record in records}), expected)
        self.assertTrue(any(record.get('format_version') == 'visitor-name.1' for record in records))
        self.assertTrue(any(record.get('format_version') == 'visitor-entry.3' for record in records))

    def test_expired_entries_can_be_marked_but_future_checks_are_rejected(self):
        path = self.visitor / 'entries' / 'city-services.json'
        records = json.loads(path.read_text(encoding='utf-8'))
        records[0]['checked_on'] = (self.today - timedelta(days=3)).isoformat()
        records[0]['expires_on'] = (self.today - timedelta(days=2)).isoformat()
        path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(read_records(self.visitor, self.today)[0]['expires_on'], (self.today - timedelta(days=2)).isoformat())
        records[0]['checked_on'] = (self.today + timedelta(days=1)).isoformat()
        records[0]['expires_on'] = (self.today + timedelta(days=2)).isoformat()
        path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'future'):
            read_records(self.visitor, self.today)

    def test_nonempty_output_is_not_published(self):
        output = self.visitor / 'output'
        output.mkdir()
        (output / 'unexpected.txt').write_text('stale', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'output directory must be empty'):
            build(output, allow_dirty=True)

    def test_duplicate_ids_across_formats_fail_the_build(self):
        legacy = json.loads((self.visitor / 'entries' / 'city-services.json').read_text(encoding='utf-8'))
        path = self.visitor / 'entries-v2' / 'venue-conditions.json'
        records = json.loads(path.read_text(encoding='utf-8'))
        records[0]['id'] = legacy[0]['id']
        path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate record id'):
            read_records(self.visitor, self.today)


if __name__ == '__main__':
    unittest.main()
