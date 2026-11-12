"""Unified planning rule, original-source retention, and explicit no-save holds."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import json
from hashlib import sha256
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from jsonschema import Draft202012Validator,ValidationError

from cj_agent.lio_intake_flow_schema import response_format,response_format_sha256
from cj_api.lio_flow_intake import parse_flow
from cj_api.lio_planning_grounding import PlanningTurn
from cj_api.local_lio_national import NationalLioPlanning
from cj_needs.domain import InvalidInput
import test_lio_national_execution as execution


def flow(text,*,city='成都',days=3,start=None,party=None,intent='consult',reply='请问哪天出发、几个人一起去？',questions=('start_date','party_size'),index=0):
    sources=[dict(field='duration_days',source_index=index,quote=text)]if days is not None else []
    if start:sources.append(dict(field='start_date',source_index=index,quote=text))
    if party:sources.append(dict(field='party_size',source_index=index,quote=text))
    return dict(version='LIO-planning-intake.7',intent=intent,reply=reply,question_fields=list(questions),publication_hold=None,planning_request_index=index if city is not None and days is not None else None,needs_tools=True,
        current_source_index=index,city=None if city is None else dict(query=city,normalized_name=None,province=None,source_index=index,quote=city),
        duration_days=days,start_date=start,party_size=party,unknown_fields=[],uncertain_fields={},
        field_sources=sources,fixed_items=[],extra_fields={},extra_unknown_fields=[],extra_uncertain_fields={},unresolved=[],long_term_requests=[])


def original(text):return PlanningTurn(text,date(2026,11,11))

def run(wire,text,**kwargs):
    runner=execution.NationalExecution()
    return runner.run_intake(runner.envelope(text),flow_output=wire,**kwargs)


def answer(events):return ''.join(v for k,v in events if k=='text_delta')

def context(events):return json.loads(next(v.split(':',1)[1]for k,v in events if v.startswith('lio_planning_context.1:')))


class PlanningFlow(unittest.TestCase):
    def test_destination_duration_always_enter_planning_and_ask_both_once(self):
        for text,city,locale,reply in [('去成都玩三天','成都','zh','好的，你想去成都玩三天。请问大概什么时候出发？还有几个人一起去呢？'),
              ('Chengdu for three days','Chengdu','en','When would you like to start, and how many people are traveling?')]:
            for intent in ('consult','discuss','plan'):
                with self.subTest(text=text,intent=intent):
                    wire=flow(text,city=city,intent=intent,reply=reply)
                    published,events,lookups,result=run(wire,text,locale=locale)
                    self.assertEqual(published,[]);self.assertEqual(lookups,[])
                    self.assertEqual(answer(events),reply)
                    self.assertEqual(context(events)['authority'],'plan')
                    self.assertEqual(context(events)['status'],'needs_details')
                    self.assertIsNotNone(result) # cannot fall through to native tools

    def test_given_relative_or_absolute_start_only_asks_party(self):
        for text,city,start,locale,reply in [
            ("Plan 4 days in Xi'an from tomorrow","Xi'an",'2026-11-12','en','How many people will be joining you?'),
            ('去成都玩三天，从2026-11-20开始','成都','2026-11-20','zh','这趟一共几位同行？')]:
            wire=flow(text,city=city,days=4 if locale=='en'else 3,start=start,reply=reply,questions=('party_size',))
            published,events,lookups,_=run(wire,text,locale=locale)
            self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),reply)
            self.assertEqual(context(events)['facts']['start_date']['value'],start)

    def test_host_combines_incomplete_question_and_removes_reasking_known_date(self):
        text='去成都玩三天'
        wire=flow(text,reply='哪天开始？',questions=('start_date',))
        events=run(wire,text)[1]
        self.assertIn('哪天开始',answer(events));self.assertIn('几个人',answer(events))
        text='去成都玩三天，从2026-11-20开始'
        wire=flow(text,start='2026-11-20')
        message=answer(run(wire,text)[1])
        self.assertIn('几个人',message);self.assertNotIn('哪天',message)

    def test_followup_retains_date_duration_city_when_model_omits_prior_facts(self):
        for first,city,reply,locale in [
            ('去成都玩三天，从2026-11-20开始','成都','两个人','zh'),
            ("Plan 4 days in Xi'an from tomorrow","Xi'an",'Two people','en')]:
            start='2026-11-12'if locale=='en'else'2026-11-20'
            initial=flow(first,city=city,days=4 if locale=='en'else 3,start=start,questions=('party_size',))
            before=context(run(initial,first,locale=locale)[1])
            before['facts']={key:dict(item,sources=[dict(ref,message_id='prior-0')for ref in item['sources']])for key,item in before['facts'].items()}
            wire=flow(reply,city=None,days=None,party=2,index=1,reply='Ready.',questions=())
            published,events,_,_=run(wire,reply,locale=locale,turns=(original(first),original(reply)),previous=before)
            self.assertEqual(len(published),1)
            fields=published[0][3].fields
            self.assertEqual(fields['arrival']['date']['value'],start)
            self.assertEqual(fields['party_size']['value'],2)
            self.assertNotIn('哪天',answer(events));self.assertNotIn('start date',answer(events))

    def test_partial_answers_only_ask_remaining_fact(self):
        first='去成都玩三天';second='从2026-11-20开始'
        first_wire=flow(first)
        previous=context(run(first_wire,first)[1])
        for item in previous['facts'].values():
            for ref in item['sources']:ref['message_id']='prior-0'
        wire=flow(second,city=None,days=None,start='2026-11-20',index=1,reply='一共几位？',questions=('party_size',))
        published,events,lookups,_=run(wire,second,turns=(original(first),original(second)),previous=previous)
        self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),'一共几位？')

    def test_no_save_holds_win_and_short_answers_cannot_regrant(self):
        for suffix in ('，不用保存行程','，暂不保存行程','; keep the itinerary unsaved','; just discuss'):
            text='规划成都三天，从2026-11-20开始，两个人'+suffix
            wire=flow(text,start='2026-11-20',party=2,intent='plan',reply='先讨论，不保存。',questions=())
            published,events,_,_=run(wire,text)
            self.assertEqual(published,[]);self.assertEqual(context(events)['authority'],'none')
            previous=context(events)
            for item in previous['facts'].values():
                for ref in item['sources']:ref['message_id']='prior-0'
            following='从2026-11-20开始，两个人'
            next_wire=flow(following,city=None,days=None,start='2026-11-20',party=2,index=1,questions=())
            self.assertEqual(run(next_wire,following,turns=(original(text),original(following)),previous=previous)[0],[])

    def test_semantic_hold_uses_original_span_and_never_grants_save(self):
        for suffix in ('无需落盘','先别自动保存','no need to persist'):
            text='规划成都三天，从2026-11-20开始，两个人; '+suffix
            wire=flow(text,start='2026-11-20',party=2,intent='plan',questions=())
            wire['publication_hold']=dict(source_index=0,quote=suffix)
            published,events,_,_=run(wire,text)
            self.assertEqual(published,[]);self.assertEqual(context(events)['authority'],'none')
            bad=deepcopy(wire);bad['publication_hold']['quote']='not in the original'
            with self.assertRaises(InvalidInput):parse_flow(json.dumps(bad),(original(text),),(),'current',None)

    def test_ambiguous_booking_does_not_erase_an_original_publication_hold(self):
        from lio_flat_fixture import facts_fixture
        from test_lio_intake_start_schema import sample
        from cj_api.lio_sourced_intake import BookingSourceUnclear
        data,turns=sample('zh',True)
        wire=facts_fixture(data)
        hold='先别自动保存'
        turns=(*turns,original(hold))
        wire.update(version='LIO-planning-intake.7',current_source_index=3,question_fields=[],
            publication_hold=dict(source_index=3,quote=hold),planning_request_index=None)
        wire['fixed_items'][0]['booking_evidence']=dict(status='booked',source_index=1,quote='已确定')
        refs=tuple(dict(message_id='prior-'+str(n))for n in range(3))
        with self.assertRaises(BookingSourceUnclear)as caught:parse_flow(json.dumps(wire),turns,refs,'current',None)
        self.assertTrue(caught.exception.control.publication_hold)
        published,events,lookups,_=run(wire,hold,turns=turns,previous=dict(authority='plan',status='needs_details'))
        self.assertEqual((published,lookups),([],[]));self.assertEqual(context(events)['authority'],'none')

    def test_original_date_missing_never_defaults_and_bad_model_defaults_are_rejected(self):
        text='去成都玩三天'
        for start in ('2026-11-12','2026-11-11'):
            with self.subTest(start=start),self.assertRaises(InvalidInput):
                parse_flow(json.dumps(flow(text,start=start)),(original(text),),(),'current',None)
        parsed,_,_=parse_flow(json.dumps(flow(text)),(original(text),),(),'current',None)
        self.assertEqual(parsed.start_date,{'state':'missing'})
        self.assertEqual(parsed.extraction['fields']['party_size'],{'state':'missing'})

    def test_cache_cannot_recover_erased_or_other_dialogue_originals(self):
        text='两个人';wire=flow(text,city=None,days=None,party=2)
        foreign=dict(facts={'start_date':dict(value='2026-11-20',sources=[dict(message_id='foreign-message',quote='2026-11-20')])})
        parsed,_,_=parse_flow(json.dumps(wire),(original(text),),(),'current',foreign)
        self.assertEqual(parsed.start_date,{'state':'missing'})
        for unknown in (['start_date'],[]):
            value=deepcopy(wire);value['unknown_fields']=unknown
            value['field_sources'].append(dict(field='start_date',source_index=99,quote='2026-11-20'))
            with self.assertRaises(InvalidInput):parse_flow(json.dumps(value),(original(text),),(),'current',None)

    def test_profiles_are_explicit_and_source_index_exact(self):
        text='去成都玩三天';wire=flow(text)
        Draft202012Validator(response_format(0)['json_schema']['schema']).validate(wire)
        for index in (1,True,-1):
            wrong=dict(wire,current_source_index=index)
            with self.subTest(index=index),self.assertRaises(ValidationError):Draft202012Validator(response_format(0)['json_schema']['schema']).validate(wrong)
            with self.assertRaises(InvalidInput):parse_flow(json.dumps(wrong),(original(text),),(),'current',None)
        self.assertNotEqual(response_format_sha256(0),response_format_sha256(1))
        from cj_api.lio_sourced_intake import parse_sourced
        with self.assertRaises(InvalidInput):parse_sourced(json.dumps(wire),(original(text),))

    def test_ordinary_consultation_needs_no_execution_parameters_or_templates(self):
        for text,reply in [('你可以怎样帮我旅行？','我可以解答旅行问题。'),
                ('Can you compare a hotel and a hostel?','A hostel may offer shared rooms.'),
                ('How can you help with transport?','I can explain transport options.')]:
            wire=flow(text,city=None,days=None,questions=(),reply=reply)
            wire['needs_tools']=False
            published,events,lookups,_=run(wire,text)
            self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),reply)

    def test_unrelated_consultation_does_not_demand_execution_parameters_or_erase_pending_plan(self):
        text='酒店和青旅有什么区别？'
        wire=flow(text,city=None,days=None,questions=(),reply='青旅可能提供多人共住房间。')
        wire['needs_tools']=False
        previous=dict(authority='plan',status='needs_details')
        published,events,lookups,_=run(wire,text,previous=previous)
        self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),wire['reply'])
        self.assertEqual(context(events)['authority'],'plan')
        self.assertEqual(context(events)['status'],'needs_details')

    def test_known_fact_older_than_recent_window_keeps_protected_original_and_erasure_fence(self):
        from cj_message.domain import Unavailable
        from cj_api.local_lio_national import CONTEXT
        def row(n,erased=False):
            raw=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id='m'+str(n),
                text='2026-11-20'if n==1 else '继续',trip_id=None,creation_intent='none')).encode()
            return ('m'+str(n),n,None if erased else raw,sha256(raw).hexdigest(),date(2026,11,11),'completed')
        previous=dict(authority='plan',status='needs_details',facts={'start_date':dict(value='2026-11-20',
            sources=[dict(message_id='m1',quote='2026-11-20')])})
        recent=[row(n)for n in range(9,1,-1)]
        for erased,missing in ((False,False),(True,False),(False,True)):
            test=self
            class Database:
                @contextmanager
                def connect(self,scope):
                    test.assertEqual(scope,'owner')
                    yield self
                def execute(self,sql,args):
                    test.assertEqual(args[:3],('owner','chat','generation'))
                    if 'LIMIT %s'in sql:return SimpleNamespace(fetchall=lambda:recent)
                    if 'LIMIT 1'in sql:return SimpleNamespace(fetchone=lambda:('m9',CONTEXT+json.dumps(previous)))
                    test.assertEqual(args[-1],['m1'])
                    return SimpleNamespace(fetchall=lambda:[]if missing else[row(1,erased)])
            binding=SimpleNamespace(scope='owner',conversation_id='chat',generation='generation',message_sequence=10)
            planner=NationalLioPlanning(Database(),None)
            if erased or missing:
                with self.assertRaises(Unavailable):planner.context(binding,original('两个人'))
            else:
                turns,refs,stored=planner.context(binding,original('两个人'))
                self.assertEqual(turns[0].text,'2026-11-20');self.assertEqual(refs[0]['message_id'],'m1')
                self.assertEqual(stored,previous);self.assertEqual(len(turns),10)

    def test_quoted_translation_and_sufficiency_consultation_never_publish(self):
        for text,reply in [('请把“成都三天，从2026-11-20开始，两个人”翻译成英文。','Chengdu for three days, starting 2026-11-20, two people.'),
                ('成都从2026-11-20开始两个人玩三天够吗？','三天可以先了解主要区域。'),
                ('Translate "Chengdu for three days from 2026-11-20, two people".','成都三天。')]:
            city='Chengdu'if 'Chengdu'in text else'成都'
            wire=flow(text,city=city,start='2026-11-20',party=2,reply=reply,questions=())
            wire.update(planning_request_index=None,needs_tools=False)
            published,events,lookups,_=run(wire,text)
            self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),reply)
            self.assertEqual(context(events)['authority'],'none')

    def test_capability_question_bypasses_planning_in_both_languages(self):
        planning=NationalLioPlanning(None,None)
        for text in ('你能干啥','What can you do?'):
            with patch.object(planning,'context')as lookup:
                self.assertIsNone(planning.execute(None,None,None,text,None))
                lookup.assert_not_called()
