"""Soft proposal preference must never replace original hard constraints."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from cj_api.local_lio_pipeline import order_retrieved_plan
from cj_feasibility.rich_assembly import Activity,Assembly
from cj_feasibility.rich_solver import Window


class SoftOrderPreference(unittest.TestCase):
    def compiled(self):
        return SimpleNamespace(document={'items':[]},proposed_subjects={'lunch':['party']},
            order_activities=(Activity('lunch',(Window(11*3600,14*3600),),True,'lunch'),
                              Activity('fixed',(Window(9*3600,10*3600),),None)))

    def test_tight_source_can_fall_back_to_full_original_window_without_moving_fixed_item(self):
        compiled=self.compiled();seen=[];good=Assembly('CONDITIONAL_SCHEDULE','source-valid',b'{}')
        def solve(*args,**kwargs):
            activities=kwargs['activities'];seen.append(activities)
            return Assembly('CONFLICT','EXPLICIT_CONSTRAINTS_INFEASIBLE')if len(seen)==1 else good
        with patch('cj_api.local_lio_pipeline._assemble_retrieved',side_effect=solve):
            actual=order_retrieved_plan(object(),compiled,object(),locale='en',stop=object())
        self.assertIs(actual,good);self.assertEqual(len(seen),2)
        self.assertEqual(seen[0][0].windows,(Window(11*3600,13*3600),))
        self.assertEqual(seen[1],compiled.order_activities)
        self.assertEqual(seen[0][1],compiled.order_activities[1])

    def test_unknown_and_real_known_conflicts_never_become_another_search(self):
        for result in (Assembly('UNKNOWN','SOURCE_UNCONFIRMED'),Assembly('CONFLICT','KNOWN_OPENING_CONFLICT')):
            with patch('cj_api.local_lio_pipeline._assemble_retrieved',return_value=result)as solve:
                self.assertIs(order_retrieved_plan(object(),self.compiled(),object(),locale='en',stop=object()),result)
                self.assertEqual(solve.call_count,1)


if __name__=='__main__':unittest.main()
