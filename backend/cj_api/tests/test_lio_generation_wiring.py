"""Explicit native4 generator injection leaves the old preview dependency optional."""
from datetime import date
from types import SimpleNamespace
import unittest

from cj_api.local_lio_exploration import ExplorationPlanning


class GenerationWiring(unittest.TestCase):
    def test_plan_now_delegates_to_the_explicit_generator_without_preview_model(self):
        calls=[];events=[];result=object()
        class Generation:
            def plan(self,host,worker,binding,view,*,locale,effective,prior_model_calls):
                calls.append((host,worker,binding,view,locale,effective,prior_model_calls));return result
        planner=ExplorationPlanning(None,SimpleNamespace(),generation=Generation())
        def event(binding,state,kind,value):events.append((kind,value));return state
        worker=SimpleNamespace(_event=event);view=SimpleNamespace(profile={})
        self.assertIs(planner._plan(worker,'binding','state',view,'en',prior_model_calls=1),result)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][4],'en');self.assertEqual(calls[0][-1],1)
        self.assertTrue(any('planning_started'in value for _,value in events))

    def test_saved_rich_calendar_phase_uses_the_explicit_reader(self):
        class Generation:
            def current(self,host,binding):
                return SimpleNamespace(trip=SimpleNamespace(content=b'{"content_version":"structured.4","calendar":{"state":"undated"},"days":[{"day_index":1}]}'))
        legacy=SimpleNamespace(calendar=SimpleNamespace(current=lambda _:self.fail('legacy reader used for S4')))
        planner=ExplorationPlanning(None,legacy,generation=Generation())
        self.assertEqual(planner._phase('binding'),'undated')


if __name__=='__main__':unittest.main()
