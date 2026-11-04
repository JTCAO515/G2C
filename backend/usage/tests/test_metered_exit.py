"""Synthetic units only: how MeteredExitCore maps a refused reservation."""
from dataclasses import replace
import unittest
from cj_usage.core import Command, Config, Meter
from cj_usage.metered_exit import BudgetExceeded, BudgetUnknown, MeteredExitCore, _PreparedCall
from test_core import TransactionFake


class ScopedFake(TransactionFake):
    scope = 'account'


class Step:
    binding = 'binding'
    ledger_scope = 'account'

    def __init__(self, command):
        self.command = command


class MeteredExitStopTests(unittest.TestCase):
    def setUp(self):
        self.time = 100
        self.repo = ScopedFake()
        self.config = Config('synthetic-unit', 10, 0, 1000, 20, 3, 20, 50)
        self.meter = Meter(self.repo, self.config, lambda: self.time)
        self.core = MeteredExitCore(self.config, lambda binding, account: self.meter, clock=lambda: self.time)

    def call(self, ident):
        command = Command(ident, 'operation', 'run', 'model', 'a'*64, 2, 2)
        return _PreparedCall(Step(command), lambda: (lambda: (chunk for chunk in ['ok'])), 'step-'+ident, lambda: True)

    def test_first_step_settles(self):
        self.assertEqual(list(self.core.stream(self.call('a'))), ['ok'])
        self.assertEqual(self.repo.ledger.attempts['a'].state, 'settled')

    def test_deadline_crossed_before_reserve_is_budget_exhausted(self):
        list(self.core.stream(self.call('a')))
        self.time = 151
        with self.assertRaises(BudgetExceeded) as caught:
            list(self.core.stream(self.call('b')))
        self.assertEqual(caught.exception.step_key, 'step-b')
        self.assertNotIn('b', self.repo.ledger.attempts)

    def test_period_closed_before_reserve_is_budget_exhausted(self):
        list(self.core.stream(self.call('a')))
        self.time = 1000
        with self.assertRaises(BudgetExceeded):
            list(self.core.stream(self.call('b')))
        self.assertNotIn('b', self.repo.ledger.attempts)

    def test_cancelled_run_stays_unknown(self):
        list(self.core.stream(self.call('a')))
        with self.repo.transaction() as ledger:
            ledger.runs['run'] = replace(ledger.runs['run'], cancelled=True)
        with self.assertRaises(BudgetUnknown):
            list(self.core.stream(self.call('b')))

    def test_cancelled_run_after_deadline_stays_unknown(self):
        list(self.core.stream(self.call('a')))
        with self.repo.transaction() as ledger:
            ledger.runs['run'] = replace(ledger.runs['run'], cancelled=True)
        self.time = 151
        with self.assertRaises(BudgetUnknown):
            list(self.core.stream(self.call('b')))


if __name__ == '__main__':
    unittest.main()
