"""Original durable M4 journal controls; no network or real fees."""
from pathlib import Path
import tempfile
import unittest

from cj_api.runtime_budget import Ceilings
from cj_usage.authorization_budget import AuthorizationBudget, authorization_usage
from cj_usage.metered_exit import BudgetUnknown
from test_m4_real_services import NOW, M4_MODEL, M4_BASE


class WindowBudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.budget=AuthorizationBudget(Path(self.directory.name),clock=lambda:NOW)

    def guard(self, limits, selected):
        return lambda db,attempt,kind,raw:limits.check(db,selected,kind)

    def test_unresolved_full_hold_refuses_next_intent_atomically(self):
        self.budget.begin('original','model',b'original')
        before=self.budget.inspect()
        with self.assertRaises(BudgetUnknown):
            self.budget.begin('next','model',b'next',before_intent=self.guard(Ceilings(400,50,1,5),{'original'}))
        self.assertEqual(self.budget.inspect(),before)
        self.assertEqual(before[0]['state'],'INTENT')

    def test_receipt_estimate_then_complete_prospective_hold_must_fit(self):
        self.budget.begin('original','model',b'original')
        self.budget.finish('original',dict(model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',
            receipt_sha256='a'*64,usage=dict(prompt_tokens=100000,completion_tokens=100000,total_tokens=200000)))
        before=self.budget.inspect()
        with self.assertRaises(BudgetUnknown):
            self.budget.begin('next','model',b'next',before_intent=self.guard(Ceilings(400,50,1,5),{'original'}))
        self.assertEqual(self.budget.inspect(),before)
        self.budget.begin('next','model',b'next',before_intent=self.guard(Ceilings(400,50,2,5),{'original'}))
        self.assertEqual(len(self.budget.inspect()),2)

    def test_counts_include_failed_unknown_and_free_facts_without_new_ledger(self):
        self.budget.begin('free','fact',b'free')
        with self.assertRaises(BudgetUnknown):
            self.budget.begin('next','weather',b'next',before_intent=self.guard(Ceilings(400,1,50,5),{'free'}))
        self.assertEqual(len(self.budget.inspect()),1)
        self.budget.begin('outside','model',b'outside')
        self.budget.begin('one','model',b'one',before_intent=self.guard(Ceilings(1,50,50,5),set()))
        with self.assertRaises(BudgetUnknown):
            self.budget.begin('two','model',b'two',before_intent=self.guard(Ceilings(1,50,50,5),{'one'}))
        with self.budget.connect() as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall(),
                             [('attempt',),('producer',)])
            global_usage=authorization_usage(db)
            selected_usage=authorization_usage(db,attempt_ids={'one'},include_M1=False)
        self.assertGreater(global_usage[2]['model'],selected_usage[2]['model'])

    def test_old_attempt_cannot_be_rearmed_even_with_empty_window_selection(self):
        self.budget.begin('original','model',b'original')
        with self.assertRaises(BudgetUnknown):
            self.budget.begin('original','model',b'original',before_intent=self.guard(Ceilings(400,50,50,5),set()))
        self.assertEqual(len(self.budget.inspect()),1)
