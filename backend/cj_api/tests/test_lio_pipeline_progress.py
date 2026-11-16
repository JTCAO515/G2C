import json
import unittest
from types import SimpleNamespace

from cj_api.local_lio_pipeline_calls import Call,PipelineCalls,PipelineCapacity
from cj_api.lio_exploration_routes import _progress


class PipelineProgressTests(unittest.TestCase):
    def worker(self,*,invalid=False):
        effects=[];sends=[]
        def event(binding,state,kind,value):
            if invalid:raise RuntimeError('current original revoked')
            self.assertEqual(kind,'effect_committed');effects.append(value);return state
        def stream(binding,key,registration,argument,**kwargs):
            sends.append(key);yield '';yield 'observed'
        worker=SimpleNamespace(lio_memory=None,runs=SimpleNamespace(snapshot=lambda _:object()),
            _event=event,_registered_stream=stream)
        return worker,effects,sends

    def test_progress_is_existing_v4_shape_and_uses_the_travelers_locale(self):
        for locale,word in [('zh','地点'),('en','places')]:
            worker,effects,sends=self.worker()
            PipelineCalls(worker,'binding',locale=locale).parallel((Call('gaode','tool.lio_poi2.1',0),))
            value=_progress(SimpleNamespace(status='running',effects=effects),locale)
            self.assertEqual(value['kind'],'waiting')
            self.assertIn(word,value['text'])
            self.assertEqual(len(sends),1)
            self.assertIsNone(_progress(SimpleNamespace(status='completed',effects=effects),locale))

    def test_current_original_rejection_prevents_external_dispatch(self):
        worker,effects,sends=self.worker(invalid=True)
        with self.assertRaisesRegex(RuntimeError,'revoked'):
            PipelineCalls(worker,'binding',locale='en').parallel((Call('gaode','tool.lio_poi2.1',0),))
        self.assertEqual(sends,[])
        self.assertEqual(effects,[])

    def test_budget_denial_does_not_report_a_stage_as_started(self):
        worker,effects,sends=self.worker();calls=PipelineCalls(worker,'binding',locale='en')
        calls.gaode=45
        with self.assertRaises(PipelineCapacity):calls.parallel((Call('gaode','tool.lio_route.1',0),))
        self.assertEqual((effects,sends),([],[]))
