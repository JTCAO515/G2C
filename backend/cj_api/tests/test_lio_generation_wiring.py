"""Explicit native4 generator injection leaves the old preview dependency optional."""
from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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


    def test_unknown_edge_proximity_asks_for_evidence_without_publication(self):
        from cj_api.local_lio_pipeline_generation import PipelineGeneration
        import cj_api.local_lio_pipeline_generation as generation
        for locale,question in (('zh','能补充酒店的具体位置吗？'),
                                ('en','Can you provide the exact hotel location?')):
            for retained in (False,True):
                with self.subTest(locale=locale,retained=retained):
                    events=[]
                    host=SimpleNamespace(current=lambda _:object()if retained else None,
                        _finish=lambda worker,binding,state,body,scene,lang:body)
                    worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),
                        _event=lambda binding,state,kind,value:events.append((kind,value))or state)
                    prepared=SimpleNamespace(projection=SimpleNamespace(fields={'party_size':{'state':'known','value':1}}))
                    capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=None))
                    with patch.multiple(generation,prepare_generation=unittest.mock.DEFAULT,
                            retrieve_skeleton=unittest.mock.DEFAULT,compile_retrieved_plan=unittest.mock.DEFAULT,
                            order_retrieved_plan=unittest.mock.DEFAULT,route_ordered_plan=unittest.mock.DEFAULT,
                            publish_retrieved_plan=unittest.mock.DEFAULT)as stages:
                        stages['prepare_generation'].return_value=prepared
                        stages['retrieve_skeleton'].return_value=({},(),capture)
                        stages['order_retrieved_plan'].return_value=SimpleNamespace(content=None,
                            status='UNKNOWN',reason='EDGE_DAY_PROXIMITY_UNCONFIRMED')
                        body=PipelineGeneration().plan(host,worker,'binding','view',locale=locale,
                            effective={},prior_model_calls=1)
                        self.assertIn(question,body)
                        self.assertIn('附近'if locale=='zh'else'near the hotel',body)
                        self.assertEqual(('原行程保留'if locale=='zh'else'original itinerary is kept')in body,retained)
                        stages['route_ordered_plan'].assert_not_called()
                        stages['publish_retrieved_plan'].assert_not_called()
                        self.assertEqual(len(events),1)


if __name__=='__main__':unittest.main()
