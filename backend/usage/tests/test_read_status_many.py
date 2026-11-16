"""Bounded original-attempt projection; no cached admission or dispatch rights."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
import unittest
from unittest.mock import patch

from cj_usage.core import Attempt, Receipt
from cj_usage.postgres import CommitUnknown, PostgresRepository, RepositoryUnavailable
from cj_usage.read_status import ReadUnavailable
import test_read_status as storage


class BatchReadTests(unittest.TestCase):
    Conn = storage.ReadTests.Conn
    setUp = storage.ReadTests.setUp
    event = storage.ReadTests.event
    guard = storage.ReadTests.guard

    def read(self, ids=('a',), **kwargs):
        options = dict(guard=self.guard, max_response_bytes=368686,
            expected_period=(0, 1000))
        options.update(kwargs)
        return self.repo.read_status_many(ids, **options)

    def seed_states(self):
        for i, state in enumerate(('reserved', 'unknown', 'released', 'settled')):
            key = 'attempt-' + str(i)
            command = replace(self.ledger.attempts['a'].command,
                attempt_id=key, operation_id='operation-' + str(i))
            receipt = Receipt(key, 'original-receipt', 'synthetic-unit', 0, 0) if state == 'settled' else None
            self.ledger.attempts[key] = Attempt(command, state, receipt, state == 'released')
        self.ledger.runs['run'].steps = len(self.ledger.attempts)
        self.ledger.runs['run'].cancelled = True
        self.row = (7, 1, asdict(self.ledger))
        return tuple('attempt-' + str(i) for i in range(4))

    def test_one_snapshot_preserves_order_and_original_minimal_statuses(self):
        ids = tuple(reversed(self.seed_states()))
        before = deepcopy(self.row)
        raw = self.read(ids)
        rows = json.loads(raw)
        self.assertEqual([r['attempt_id'] for r in rows], list(ids))
        self.assertEqual([r['status'] for r in rows], ['settled', 'released', 'unknown', 'reserved'])
        self.assertEqual(rows[0]['confirmed_units'], 0)
        self.assertEqual(rows[0]['confirmed_output'], 0)
        self.assertTrue(rows[1]['cancelled'])
        self.assertIsNone(rows[2]['receipt_id'])
        self.assertEqual(self.row, before)
        sql = [item[0] for item in self.log if isinstance(item, tuple)]
        self.assertEqual(len(sql), 2)
        self.assertIn('REPEATABLE READ READ ONLY', sql[0])
        self.assertTrue(sql[1].startswith('SELECT '))
        self.assertNotIn('FOR UPDATE', sql[1])
        for key in ('input_digest', 'ledger', 'scope', 'budget', 'config'):
            self.assertNotIn(key, rows[0])
        # Subsequent reads use their own current original snapshot, no cache.
        self.ledger.attempts['a'] = replace(self.ledger.attempts['a'], state='released', cancelled=True)
        self.row = (8, 1, asdict(self.ledger))
        self.assertEqual(json.loads(self.read(('a',)))[0]['status'], 'released')
        self.assertEqual(self.log.count('select'), 2)

    def test_current_binder_runs_after_readonly_before_original_select(self):
        def bind(conn, cur):
            self.assertIs(conn, self.conn)
            self.event('bind')
        self.repo = PostgresRepository(self.factory, 'scope-a', read_binder=bind)
        self.read()
        self.assertLess(self.log.index('set'), self.log.index('bind'))
        self.assertLess(self.log.index('bind'), self.log.index('select'))

    def test_input_count_duplicates_and_total_bounds_rejected_before_connection(self):
        for ids in ((), ['a'], ('a', 'a'), tuple(str(i) for i in range(46))):
            with self.subTest(ids=ids), self.assertRaises(ReadUnavailable):
                self.read(ids)
        with self.assertRaises(ReadUnavailable):
            self.read(max_response_bytes=368687)
        with self.assertRaises(ReadUnavailable):
            self.read(expected_period=None)
        self.assertEqual(self.log, [])

    def test_45_distinct_attempts_in_one_select(self):
        self.ledger.config = replace(self.ledger.config, max_steps=46)
        for i in range(45):
            command = replace(self.ledger.attempts['a'].command, attempt_id=str(i))
            self.ledger.attempts[str(i)] = Attempt(command, 'unknown')
        self.ledger.runs['run'].steps = len(self.ledger.attempts)
        self.row = (7, 1, asdict(self.ledger))
        self.assertEqual(len(json.loads(self.read(tuple(str(i) for i in range(45))))), 45)
        self.assertEqual(self.log.count('select'), 1)

    def test_missing_row_attempt_or_wrong_period_withholds_all(self):
        for ids, period, row in ((('a', 'missing'), (0, 1000), self.row),
                (('a',), (1, 1000), self.row), (('a',), (0, 1000), None)):
            self.row = row
            with self.subTest(ids=ids, period=period), self.assertRaises((ReadUnavailable, RepositoryUnavailable)):
                self.read(ids, expected_period=period)
            self.assertNotIn('commit', self.log)

    def test_per_status_and_total_output_limits_withhold(self):
        with patch('cj_usage.read_status.encode_status', return_value=b'x' * 8193):
            with self.assertRaisesRegex(ReadUnavailable, 'per-attempt'):
                self.read()
        self.assertNotIn('commit', self.log)
        with self.assertRaisesRegex(ReadUnavailable, 'configured bound'):
            self.read(max_response_bytes=1)

    def test_revocation_at_every_io_and_cleanup_boundary_withholds(self):
        for stage in ('cursor', 'set', 'select', 'fetch', 'commit', 'cursor_close', 'connection_close'):
            with self.subTest(stage=stage):
                self.setUp()
                self.hooks[stage] = lambda: setattr(self, 'allowed', False)
                with self.assertRaises(ReadUnavailable):
                    self.read()
                self.assertIn('connection_close', self.log)

    def test_rebinding_and_cleanup_or_ack_failure_withhold(self):
        for stage in ('fetch', 'connection_close'):
            self.setUp()
            self.hooks[stage] = lambda: setattr(self.repo, 'read_binder', lambda conn, cur: None)
            with self.assertRaises(ReadUnavailable):
                self.read()
        for stage in ('cursor_close', 'connection_close', 'commit'):
            self.setUp()
            self.errors[stage] = OSError('synthetic unavailable')
            expected = CommitUnknown if stage == 'commit' else ReadUnavailable
            with self.assertRaises(expected):
                self.read()
            self.assertIn('connection_close', self.log)

    def test_binder_failure_never_selects_and_legacy_single_read_unchanged(self):
        before = deepcopy(self.row)
        def bind(conn, cur):
            raise RepositoryUnavailable('original scope unavailable')
        self.repo = PostgresRepository(self.factory, 'scope-a', read_binder=bind)
        with self.assertRaises(RepositoryUnavailable):
            self.read()
        self.assertNotIn('select', self.log)
        self.assertEqual(self.row, before)
        self.setUp()
        single = self.repo.read_status('a', guard=self.guard, max_response_bytes=8192,
            expected_period=(0, 1000))
        self.assertEqual(json.loads(self.read()), [json.loads(single)])
