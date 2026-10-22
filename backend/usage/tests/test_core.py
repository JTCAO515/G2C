"""Synthetic integer units only: NOT USD, tokens, pricing or real provider usage."""
from contextlib import contextmanager
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import RLock
import unittest
from cj_usage.core import Blocked, Command, Config, Ledger, Meter, Receipt
from cj_usage.local_exit import LocalExit


class TransactionFake:
    """Test-only serializable rollback substitute; NOT durable or a database."""
    def __init__(self):
        self.ledger = Ledger()
        self.lock = RLock()

    @contextmanager
    def transaction(self):
        with self.lock:
            working = deepcopy(self.ledger)
            yield working
            self.ledger = deepcopy(working)


class Tests(unittest.TestCase):
    def setUp(self):
        self.time = 100
        self.repo = TransactionFake()
        self.config = Config('synthetic-unit', 10, 0, 1000, 20, 3, 20, 50)
        self.meter = Meter(self.repo, self.config, lambda: self.time)

    def cmd(self, ident='a', **kwargs):
        return replace(Command(ident, 'operation', 'run', 'model', 'a'*64, 6, 2), **kwargs)

    def receipt(self, ident='a', actual=3, **kwargs):
        return replace(Receipt(ident, 'receipt-'+ident, 'synthetic-unit', actual, 1), **kwargs)

    def test_missing_invalid_configuration(self):
        for cfg in (None, {}, False):
            with self.assertRaises(Blocked): Meter(self.repo, cfg, lambda: 0)
        for field, val in [('unit', ''), ('budget', True), ('budget', 0),
                           ('max_seconds', float('nan')), ('period_end', 0)]:
            with self.assertRaises(Blocked): replace(self.config, **{field: val})
        with self.assertRaises(Blocked): Meter(self.repo, self.config, None)

    def test_default_exit_never_calls_provider(self):
        with self.assertRaisesRegex(Blocked, 'provider_disabled'):
            LocalExit(self.meter).execute(self.cmd())
        self.assertEqual(self.repo.ledger.attempts, {})

    def test_idempotence_and_conflict(self):
        a = self.meter.reserve(self.cmd())
        self.assertEqual(a, self.meter.reserve(self.cmd()))
        for field, val in [('reserve', 5), ('input_digest', 'b'*64), ('run_id', 'other'),
                           ('operation_id', 'other'), ('kind', 'memory')]:
            with self.assertRaisesRegex(Blocked, 'id_conflict'):
                self.meter.reserve(replace(self.cmd(), **{field: val}))
        self.assertEqual(self.repo.ledger.runs['run'].steps, 1)

    def test_concurrent_budget_never_over_reserved(self):
        def reserve(i):
            try:
                return self.meter.reserve(self.cmd(str(i), reserve=1, output_limit=1))
            except Blocked: return None
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(reserve, range(50)))
        self.assertEqual(sum(x is not None for x in results), 10)
        self.assertEqual(Meter.exposure(self.repo.ledger), 10)

    def test_concurrent_duplicate_dispatch_once(self):
        calls = []
        def execute(c):
            calls.append(c.attempt_id)
            return self.receipt()
        adapter = LocalExit(self.meter, execute)
        def attempt(_):
            try: return adapter.execute(self.cmd())
            except Blocked: return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(attempt, range(20)))
        self.assertEqual(calls, ['a'])
        self.assertEqual(Meter.exposure(self.repo.ledger), 3)

    def test_cancel_unclaimed_releases_and_late_receipt_refused(self):
        self.meter.reserve(self.cmd())
        self.meter.cancel('run')
        self.assertEqual(Meter.exposure(self.repo.ledger), 0)
        with self.assertRaises(Blocked): self.meter.claim('a')
        with self.assertRaises(Blocked): self.meter.settle(self.receipt())
        with self.assertRaises(Blocked): self.meter.reserve(self.cmd('b'))

    def test_timeout_cancel_unknown_retains_then_late_settles_once(self):
        def timeout(c): raise TimeoutError('synthetic')
        with self.assertRaises(TimeoutError): LocalExit(self.meter, timeout).execute(self.cmd())
        self.meter.cancel('run')
        self.assertEqual(self.meter.query('a').state, 'unknown')
        self.assertEqual(Meter.exposure(self.repo.ledger), 6)
        self.time = 2000  # Receipt remains reconcilable after period/deadline.
        a = self.meter.settle(self.receipt())
        self.assertTrue(a.cancelled)
        self.assertEqual(a, self.meter.settle(self.receipt()))
        self.assertEqual(Meter.exposure(self.repo.ledger), 3)
        with self.assertRaises(Blocked): self.meter.settle(self.receipt(actual=4))

    def test_actual_above_reservation_recorded_not_clipped(self):
        self.meter.reserve(self.cmd()); self.meter.claim('a')
        a = self.meter.settle(self.receipt(actual=12))
        self.assertTrue(a.exceeded)
        self.assertEqual(Meter.exposure(self.repo.ledger), 12)
        with self.assertRaises(Blocked): self.meter.reserve(self.cmd('b', run_id='other'))

    def test_output_aggregate_and_tool_step_limits(self):
        cfg = replace(self.config, max_output=3)
        m = Meter(self.repo, cfg, lambda: self.time)
        m.reserve(self.cmd(reserve=1))
        with self.assertRaises(Blocked): m.reserve(self.cmd('b', reserve=1))
        for field in ('max_tools', 'max_steps'):
            repo = TransactionFake()
            m = Meter(repo, replace(self.config, **{field: 1}), lambda: self.time)
            m.reserve(self.cmd(kind='tool', reserve=1))
            with self.assertRaises(Blocked): m.reserve(self.cmd('b', kind='tool', reserve=1))

    def test_clock_deadline_and_period(self):
        self.meter.reserve(self.cmd())
        self.time = 150
        with self.assertRaises(Blocked): self.meter.claim('a')
        self.time = 99
        with self.assertRaisesRegex(Blocked, 'clock_regressed'): self.meter.claim('a')
        for now in (float('nan'), float('inf'), True, 1000):
            self.time = now
            with self.assertRaises(Blocked): self.meter.reserve(self.cmd('b', reserve=1))

    def test_configuration_cannot_reset_existing_ledger(self):
        self.meter.reserve(self.cmd())
        m = Meter(self.repo, replace(self.config, budget=100), lambda: self.time)
        with self.assertRaisesRegex(Blocked, 'configuration_conflict'): m.reserve(self.cmd('b'))

    def test_bad_receipt_retains_exposure(self):
        self.meter.reserve(self.cmd()); self.meter.claim('a')
        with self.assertRaises(Blocked): self.meter.settle(self.receipt(unit='USD'))
        self.assertEqual(Meter.exposure(self.repo.ledger), 6)
        self.meter.settle(self.receipt())
        self.meter.reserve(self.cmd('b')); self.meter.claim('b')
        with self.assertRaises(Blocked): self.meter.settle(self.receipt('b', receipt_id='receipt-a'))

    def test_unknown_commit_ack_does_not_dispatch(self):
        class AckLost(TransactionFake):
            @contextmanager
            def transaction(self):
                with super().transaction() as l: yield l
                raise OSError('commit ACK unknown')
        calls = []
        m = Meter(AckLost(), self.config, lambda: self.time)
        with self.assertRaises(OSError):
            LocalExit(m, lambda c: calls.append(c)).execute(self.cmd())
        self.assertEqual(calls, [])

    def test_claim_commit_ack_lost_retains_unknown_without_execution(self):
        class ClaimAckLost(TransactionFake):
            @contextmanager
            def transaction(self):
                with super().transaction() as ledger:
                    yield ledger
                if any(a.state == 'unknown' for a in self.ledger.attempts.values()):
                    raise OSError('claim ACK unknown')
        repo = ClaimAckLost()
        calls = []
        m = Meter(repo, self.config, lambda: self.time)
        with self.assertRaises(OSError):
            LocalExit(m, lambda c: calls.append(c)).execute(self.cmd())
        self.assertEqual(calls, [])
        self.assertEqual(repo.ledger.attempts['a'].state, 'unknown')
        self.assertEqual(Meter.exposure(repo.ledger), 6)

    def test_wrong_attempt_receipt_cannot_settle_other_work(self):
        self.meter.reserve(self.cmd('b', reserve=1))
        self.meter.claim('b')
        with self.assertRaisesRegex(Blocked, 'receipt_invalid'):
            LocalExit(self.meter, lambda c: self.receipt('b')).execute(self.cmd())
        self.assertEqual(self.meter.query('a').state, 'unknown')
        self.assertEqual(self.meter.query('b').state, 'unknown')

    def test_output_overrun_stops_pending_claim_and_preserves_actual(self):
        self.meter.reserve(self.cmd(reserve=1))
        self.meter.reserve(self.cmd('b', reserve=1))
        self.meter.claim('a')
        result = self.meter.settle(self.receipt(output=100))
        self.assertTrue(result.exceeded)
        self.assertEqual(result.receipt.output, 100)
        with self.assertRaises(Blocked): self.meter.claim('b')

    def test_query_snapshot_cannot_mutate_repository(self):
        self.meter.reserve(self.cmd())
        a = self.meter.query('a')
        with self.assertRaises(AttributeError): a.state = 'released'
        self.assertEqual(Meter.exposure(self.repo.ledger), 6)

    def test_background_memory_same_budget(self):
        self.meter.reserve(self.cmd())
        with self.assertRaisesRegex(Blocked, 'limit_exceeded'):
            LocalExit(self.meter, lambda c: self.receipt('b')).execute(
                self.cmd('b', kind='memory', run_id='background'))


if __name__ == '__main__': unittest.main()
