"""Versioned facade uses actual canonical checker and CP-SAT, synthetic facts."""
from dataclasses import replace
from threading import Event
import json
import unittest

from cj_feasibility.v1 import (VERSION, INPUT_PROFILE, check_constraints,
    check_edit_scope, solve_constraints)
from cj_feasibility.validator import Candidate, VERSION as LEGACY_VERSION
from test_validator import history, item, event, known
from test_solver import route_problem, limits


class FeasibilityV1Tests(unittest.TestCase):
    def test_sixty_minute_route_cannot_fit_fixed_fifteen_and_bilingual(self):
        p=route_problem(selected=False)
        result=solve_constraints(p,limits(),stop=Event())
        self.assertEqual((result.version,result.input_profile,result.operation),
                         (VERSION,INPUT_PROFILE,'solve'))
        self.assertEqual(result.status,'CONDITIONAL_UNSAT')
        self.assertEqual(result.report.overall,'UNKNOWN')
        self.assertIsNone(result.report.candidate)
        self.assertTrue(result.report.zh);self.assertTrue(result.report.en)

    def test_checked_conditional_candidate_keeps_old_output_version(self):
        p=route_problem()
        result=solve_constraints(p,limits(),stop=Event())
        self.assertEqual(result.status,'CONDITIONAL_SOLUTION')
        self.assertTrue(result.report.verification.accepted)
        self.assertNotEqual(result.report.version,VERSION)
        self.assertEqual(p.candidate.content,p.before.content)

    def test_missing_route_and_timeout_do_not_prove_unsat(self):
        p=route_problem()
        missing=replace(p.routes[0].window,buffer=None)
        result=solve_constraints(replace(p,routes=(replace(p.routes[0],window=missing),)),limits(),stop=Event())
        self.assertEqual(result.status,'UNKNOWN')
        timeout=solve_constraints(p,limits(max_solve_seconds=1e-12),stop=Event())
        self.assertEqual(timeout.status,'TIMEOUT')
        stopped=Event();stopped.set()
        self.assertEqual(solve_constraints(p,limits(),stop=stopped).status,'UNKNOWN')

    def test_scope_protection_uses_original_checker(self):
        before,rs=history({'fixed_items':[item('a',locked=True),item('b',locked=False)]})
        content=json.loads(before.content);content['fixed_items'][0]['start']=event('2026-10-22','11:00')
        candidate=Candidate(before.needs_id,before.version,json.dumps(content,ensure_ascii=False,separators=(',',':')).encode())
        result=check_edit_scope(before,rs,candidate,selected_fields=frozenset({'fixed_items'}),selected_item_ids=frozenset({'a'}))
        self.assertEqual(result.status,'CONFLICT')
        self.assertIn('LOCKED_ITEM_CHANGED',[x.code for x in result.report.checks])
        unselected=check_edit_scope(before,rs,candidate,selected_fields=frozenset(),selected_item_ids=frozenset())
        self.assertEqual(unselected.status,'CONFLICT')

    def test_missing_dates_and_incomparable_budget_remain_visible(self):
        start=event();start['date']={'state':'unknown'}
        before,rs=history({'fixed_items':[item('a',start=start)], 'budget_total':known('100'),
                           'budget_currency':known('USD')})
        result=check_constraints(before,rs)
        self.assertEqual(result.version,VERSION)
        self.assertEqual(result.report.version,LEGACY_VERSION)
        self.assertIn('ITEM_TIME_UNKNOWN',[x.code for x in result.report.checks])
        self.assertEqual(result.status,'UNKNOWN')
        self.assertTrue(all(x.zh and x.en for x in result.report.checks))


if __name__=='__main__':unittest.main()
