"""Synthetic units only: how MeteredExitCore maps a refused reservation."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from cj_usage.core import Blocked, Command, Config, Meter, Receipt
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

    def test_period_closed_without_run_is_budget_exhausted(self):
        # A background job's first and only step: a fresh run_id, period already over.
        self.time = 1000
        with self.assertRaises(BudgetExceeded) as caught:
            list(self.core.stream(self.call('a')))
        self.assertEqual(caught.exception.step_key, 'step-a')
        self.assertNotIn('a', self.repo.ledger.attempts)
        self.assertNotIn('run', self.repo.ledger.runs)

    def test_clock_before_period_start_stays_unknown(self):
        # Only a proven period end is exhaustion; an early clock proves nothing.
        self.time = -1
        with self.assertRaises(BudgetUnknown):
            list(self.core.stream(self.call('a')))
        self.assertNotIn('a', self.repo.ledger.attempts)
        self.assertNotIn('run', self.repo.ledger.runs)

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


class RegisteredToolOutputTests(unittest.TestCase):
    def setUp(self):
        from cj_run.step_usage import ledger_scope_for
        from cj_usage.registered_exit import RegisteredExit, Registration, InvocationInput
        self.config=Config('provider_call',800,0,1000,24,12,65536,600)
        self.binding=SimpleNamespace(scope='owner',run_id='run')
        self.repo=ScopedFake()
        self.repo.scope=ledger_scope_for(self.binding.scope,self.config)
        self.meter=Meter(self.repo,self.config,lambda:100)
        self.exit=RegisteredExit(self.config,lambda binding,account:self.meter,clock=lambda:100,
            output_limits=dict(model=12000,tool=48000,memory=12000),environment='local',
            registrations={'tool.synthetic':Registration('tool',lambda argument:
                InvocationInput(b'original-synthetic-tool',lambda:lambda:(chunk for chunk in ['result'])))})
        # Settled original calls total the observed regression precondition.
        for ident,kind,limit,actual in (('previous-model','model',12000,10000),
                                        ('previous-tool','tool',48000,10611)):
            command=Command(ident,ident,'run',kind,'a'*64,1,limit)
            self.meter.reserve(command); self.meter.claim(ident)
            self.meter.settle(Receipt(ident,'receipt-'+ident,'provider_call',1,actual))

    def prepare(self,*,bounded=True):
        from cj_usage.registered_exit import OperationStore
        def create(store,binding,key,registration,kind,input_bytes,output_limit):
            command=Command('next-tool','next-tool','run',kind,'b'*64,1,output_limit)
            return SimpleNamespace(binding=binding,ledger_scope=self.repo.scope,command=command)
        with patch.object(OperationStore,'create',create):
            return self.exit.prepare_operation(SimpleNamespace(valid=lambda binding:True),
                self.binding,'tool.next','tool.synthetic',None,stage='answer',reserve_final_model=bounded)

    def test_bounded_original_tool_admits_and_leaves_final_model_room(self):
        legacy=self.prepare(bounded=False)
        with self.assertRaisesRegex(Blocked,'limit_exceeded'):
            self.meter.reserve(legacy.step.command)
        bounded=self.prepare()
        self.assertEqual(bounded.step.command.output_limit,32925)
        self.assertEqual(list(self.exit.stream(bounded)),['result'])
        final=Command('final-model','final-model','run','model','c'*64,1,12000)
        self.meter.reserve(final)
        self.assertLessEqual(Meter.output_exposure(self.repo.ledger,'run'),65536)
        self.assertEqual(self.config.budget,800)
        self.assertEqual(self.exit.output_limits['tool'],48000)

    def test_unknown_output_hold_is_counted_and_never_replayed(self):
        held=Command('unknown','unknown','run','tool','c'*64,1,32000)
        self.meter.reserve(held); self.meter.claim('unknown')
        prepared=self.prepare()
        self.assertEqual(prepared.step.command.output_limit,925)
        self.assertEqual(self.meter.query('unknown').state,'unknown')
        self.assertIsNone(self.meter.query('unknown').receipt)

    def test_no_tool_room_refuses_before_new_operation_or_dispatch(self):
        held=Command('unknown','unknown','run','tool','c'*64,1,32925)
        self.meter.reserve(held); self.meter.claim('unknown')
        from cj_usage.registered_exit import OperationStore
        with patch.object(OperationStore,'create') as create,self.assertRaises(BudgetExceeded):
            self.exit.prepare_operation(SimpleNamespace(valid=lambda binding:True),self.binding,
                'tool.next','tool.synthetic',None,stage='answer',reserve_final_model=True)
        create.assert_not_called()
        self.assertEqual(set(self.repo.ledger.attempts),{'previous-model','previous-tool','unknown'})


if __name__ == '__main__':
    unittest.main()
