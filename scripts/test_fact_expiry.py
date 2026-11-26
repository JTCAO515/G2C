"""Offline checks for scripts/fact_expiry.py (#1757): changing a test entry's date raises the alarm.

Usage: python3 -B -m unittest -v scripts.test_fact_expiry
"""
from contextlib import redirect_stdout
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import fact_expiry

ROOT = fact_expiry.ROOT
AS_OF = date(2026, 12, 1)


class Fixture:
    """A copy of the real fact files, so a test changes one date and keeps every other shape."""

    def __init__(self, path):
        self.root = Path(path)
        for folder in fact_expiry.VISITOR_DIRS:
            shutil.copytree(ROOT / folder, self.root / folder)
        (self.root / fact_expiry.ARRIVAL_RULES).parent.mkdir(parents=True)
        shutil.copy(ROOT / fact_expiry.ARRIVAL_RULES, self.root / fact_expiry.ARRIVAL_RULES)
        self.far_future()

    def edit(self, rel, change):
        path = self.root / rel
        data = json.loads(path.read_text(encoding='utf-8'))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def far_future(self):
        """Every date moved out of any window, so each test sees only the date it sets."""
        for folder in fact_expiry.VISITOR_DIRS:
            for path in (self.root / folder).glob('*.json'):
                self.edit(path.relative_to(self.root), lambda records: [r.update(expires_on='2099-01-01') for r in records])

        def arrival(data):
            data['checked_at'] = '2099-01-01'
            for policy in data['policies']:
                policy['checked_at'] = '2099-01-01'
                if policy.get('valid_until') is not None:
                    policy['valid_until'] = '2099-01-01'
        self.edit(fact_expiry.ARRIVAL_RULES, arrival)

    def first_entry_file(self):
        return next((self.root / 'knowledge/visitor/entries').glob('*.json')).relative_to(self.root)

    def run(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = fact_expiry.main(['--as-of', AS_OF.isoformat(), *argv], root=self.root)
        return code, out.getvalue()


class FactExpiryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Fixture(self.tmp.name)
        env = {k: v for k, v in os.environ.items() if k != 'GITHUB_STEP_SUMMARY'}
        patcher = patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_entry_expiry(self, days, period=30):
        """Expire the first entry `days` after AS_OF, checked `period` days before that."""
        rel = self.fixture.first_entry_file()
        expires = AS_OF + timedelta(days=days)
        self.fixture.edit(rel, lambda records: records[0].update(
            expires_on=expires.isoformat(), checked_on=(expires - timedelta(days=period)).isoformat()))
        return rel

    def test_real_repository_data_is_readable(self):
        items = fact_expiry.collect()
        self.assertTrue(any(i.kind == 'expires' for i in items))
        self.assertTrue(any(i.kind == 'review' and i.id == 'arrival-rules' for i in items))
        self.assertTrue(any(i.kind == 'policy_end' for i in items))

    def test_quiet_when_nothing_is_due(self):
        code, out = self.fixture.run()
        self.assertEqual(code, 0)
        self.assertNotIn('::', out)

    def test_entry_due_within_14_days_warns_and_passes(self):
        for days in (1, 13, 14):
            rel = self.set_entry_expiry(days)
            code, out = self.fixture.run()
            with self.subTest(days=days):
                self.assertEqual(code, 0)
                self.assertIn(f'::warning file={rel.as_posix()},', out)
                self.assertIn(f'还剩 {days} 天', out)
                self.assertNotIn('::error', out)

    def test_entry_due_after_14_days_is_quiet(self):
        self.set_entry_expiry(15)
        code, out = self.fixture.run()
        self.assertEqual(code, 0)
        self.assertNotIn('::', out)

    def test_expired_entry_is_an_error_annotation_but_does_not_fail(self):
        for days in (0, -30):
            self.set_entry_expiry(days)
            code, out = self.fixture.run()
            with self.subTest(days=days):
                self.assertEqual(code, 0)
                self.assertIn('::error file=', out)
                self.assertIn('已过期', out)

    def test_short_review_cycle_warns_for_half_its_period(self):
        """A 14-day cycle (passport booking rules) warns in its last 7 days, not from the day it was checked."""
        for days, warns in ((13, False), (8, False), (7, True), (1, True)):
            self.set_entry_expiry(days, period=14)
            out = self.fixture.run()[1]
            with self.subTest(days=days):
                self.assertEqual('::warning' in out, warns)
        self.set_entry_expiry(1, period=1)
        self.assertIn('::warning', self.fixture.run()[1])  # never a zero-day lead
        self.set_entry_expiry(14, period=28)
        self.assertIn('::warning', self.fixture.run()[1])  # half of 28 reaches the full window

    def test_window_is_configurable(self):
        self.set_entry_expiry(20, period=60)
        self.assertNotIn('::warning', self.fixture.run()[1])
        self.assertIn('::warning', self.fixture.run('--window', '30')[1])

    def test_arrival_rules_review_and_policy_end_warn(self):
        def review_due_soon(data):
            data['checked_at'] = (AS_OF - timedelta(days=data['review_every_days'] - 5)).isoformat()
        self.fixture.edit(fact_expiry.ARRIVAL_RULES, review_due_soon)
        out = self.fixture.run()[1]
        self.assertIn('arrival-rules', out)
        self.assertIn('复核到期', out)

        def policy_ends_soon(data):
            data['checked_at'] = '2099-01-01'
            data['policies'][0]['valid_until'] = (AS_OF + timedelta(days=3)).isoformat()
        self.fixture.edit(fact_expiry.ARRIVAL_RULES, policy_ends_soon)
        code, out = self.fixture.run()
        self.assertEqual(code, 0)
        self.assertIn('政策截止', out)
        self.assertIn('还剩 4 天', out)  # the policy holds through valid_until

    def test_unreadable_date_fails_so_the_check_is_never_blind(self):
        rel = self.fixture.first_entry_file()
        for field, bad in (('expires_on', '2026-1-01'), ('expires_on', None), ('expires_on', '2026-02-30'),
                           ('checked_on', '20261101')):
            self.fixture.edit(rel, lambda records: records[0].update({field: bad}))
            code, out = self.fixture.run()
            with self.subTest(field=field, bad=bad):
                self.assertEqual(code, 1)
                self.assertIn('::error title=', out)

    def test_missing_folder_fails(self):
        shutil.rmtree(self.fixture.root / fact_expiry.VISITOR_DIRS[-1])
        self.assertEqual(self.fixture.run()[0], 1)

    def test_job_summary_lists_the_items(self):
        self.set_entry_expiry(3)
        summary = Path(self.tmp.name) / 'summary.md'
        with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary)}):
            self.assertEqual(self.fixture.run()[0], 0)
        text = summary.read_text(encoding='utf-8')
        self.assertIn('将到期', text)
        self.assertIn('提前 14 天与复核周期一半取较短者', text)

    def test_annotation_text_is_escaped(self):
        item = fact_expiry.Item('a.json', 'x%\ny', 'expires', '2026-12-02', 30)
        line = fact_expiry.annotations([], [item], as_of=AS_OF)[0]
        self.assertNotIn('\n', line)
        self.assertIn('x%25%0Ay', line)

    def test_every_served_visitor_folder_is_watched(self):
        """A new live entry folder must be added to VISITOR_DIRS; candidates and examples are not served."""
        not_served = {'candidates', 'examples', 'tool-candidates', 'place-candidates', 'reviews', 'coverage'}
        served = set()
        for path in (ROOT / 'knowledge/visitor').glob('*/*.json'):
            if path.parent.name not in not_served and '"expires_on"' in path.read_text(encoding='utf-8'):
                served.add(path.parent.relative_to(ROOT).as_posix())
        self.assertEqual(served - set(fact_expiry.VISITOR_DIRS), set())


if __name__ == '__main__':
    unittest.main()
