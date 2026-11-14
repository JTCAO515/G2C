"""Rejected structured intake never grants writes or a fabricated answer."""
from datetime import date
from hashlib import sha256
import json
from types import SimpleNamespace
import unittest

from cj_agent.provider import ProviderUnknown
from cj_api.local_lio_national import NationalLioPlanning,CONTEXT
from cj_api.lio_flow_intake import parse_flow
from cj_api.lio_planning_grounding import PlanningTurn
from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_needs.domain import InvalidInput
from test_lio_planning_flow import flow


class RejectedFallback(unittest.TestCase):
    def setup_case(self,raw,*,fault=None):
        text='请帮我规划成都三天'
        binding=SimpleNamespace(message_id='rejected-current',run_id='rejected-run',message_sequence=2)
        original=SimpleNamespace(locale='zh',question_day=date(2026,11,14))
        events=[];calls=[]
        class Worker:
            provider=object();memory_run=None;message_context=None
            def _registered_stream(self,*args,**kwargs):
                calls.append((args,kwargs))
                if fault is not None:raise fault
                return iter((raw,))
            def _event(self,binding,state,kind,value=''):
                events.append((kind,value));return state
        planner=NationalLioPlanning(None,SimpleNamespace(scene_context=lambda *a:None))
        previous=dict(authority='plan',status='needs_details',facts={})
        planner.context=lambda *a:((PlanningTurn(text,original.question_day),),(),previous)
        return planner,Worker(),binding,SimpleNamespace(sequence=0),text,original,events,calls

    def test_invalid_schema_and_source_still_reject_before_general_answer(self):
        text='请帮我规划成都三天'
        bad_source=flow(text,questions=())
        bad_source.update(version='LIO-planning-intake.8')
        bad_source['field_sources'][0]['quote']='invented source text'
        for raw in ('{',json.dumps({'version':'LIO-planning-intake.8'}),json.dumps(bad_source)):
            with self.subTest(raw=raw):
                with self.assertRaises((InvalidInput,ValueError)):
                    parse_flow(raw,(PlanningTurn(text,date(2026,11,14)),),(),'rejected-current',None,schema=OptionalIntake)
                planner,worker,binding,state,text,original,events,calls=self.setup_case(raw)
                with self.assertLogs('cj_usage.audit',level='WARNING')as logs:
                    result=planner.execute(worker,binding,state,text,original)
                self.assertIsNone(result) # ordinary Worker continuation, no static answer
                self.assertEqual(len(calls),1)
                self.assertEqual([kind for kind,_ in events],['effect_committed'])
                context=json.loads(events[0][1].removeprefix(CONTEXT))
                self.assertEqual(context['authority'],'none')
                self.assertEqual(context['facts'],{})
                self.assertEqual(context['authority_barrier_message_id'],binding.message_id)
                self.assertIn(sha256(raw.encode()).hexdigest(),' '.join(logs.output))
                self.assertNotIn('invented source text',' '.join(logs.output))

    def test_unknown_original_model_attempt_is_not_retried_or_downgraded(self):
        failure=ProviderUnknown('original transport outcome unknown')
        planner,worker,binding,state,text,original,events,calls=self.setup_case('',fault=failure)
        with self.assertRaises(ProviderUnknown)as caught:
            planner.execute(worker,binding,state,text,original)
        self.assertIs(caught.exception,failure)
        self.assertEqual(events,[])
        self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
