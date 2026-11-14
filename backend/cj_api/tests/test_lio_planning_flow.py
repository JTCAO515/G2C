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
    return dict(version='LIO-planning-intake.7',intent=intent,reply=reply,question_fields=list(questions),publication_hold=None,planning_request_index=(index if city is not None and days is not None else 0 if index>0 else None),needs_tools=True,
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
    def test_destination_duration_enter_full_undated_plan_without_optional_questions(self):
        for text,city,locale in [('去成都玩三天','成都','zh'),('Chengdu for three days','Chengdu','en')]:
            for intent in ('consult','discuss','plan'):
                with self.subTest(text=text,intent=intent):
                    published,events,lookups,result=run(flow(text,city=city,intent=intent),text,locale=locale)
                    self.assertEqual(published,[]);self.assertEqual(len(lookups),1)
                    for day in range(1,4):self.assertIn('第'+str(day)+'天' if locale=='zh' else 'Day '+str(day),answer(events))
                    self.assertNotIn('哪天开始',answer(events));self.assertNotIn('几个人',answer(events))
                    self.assertNotIn('2026-',answer(events));self.assertEqual(answer(events).count('？' if locale=='zh' else '?'),1)
                    self.assertEqual(context(events)['authority'],'plan')
                    self.assertEqual(context(events)['status'],'plan_preview')
                    self.assertIsNotNone(result)

    def test_missing_semantic_request_index_does_not_grant_save(self):
        text='去成都玩三天';wire=flow(text,questions=(),reply='成都适合安排街区散步。')
        wire.update(planning_request_index=None,needs_tools=False)
        published,events,lookups,result=run(wire,text)
        self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),wire['reply'])
        self.assertEqual(context(events)['authority'],'none');self.assertIsNotNone(result)

    def test_question_fields_cannot_turn_nonplanning_input_into_a_plan(self):
        text='请把“成都三天”翻译成英文。'
        for questions in ((),('start_date',),('party_size',),('start_date','party_size')):
            wire=flow(text,questions=questions,reply='Chengdu for three days.')
            wire.update(planning_request_index=None,needs_tools=False)
            published,events,lookups,result=run(wire,text)
            self.assertEqual((published,lookups),([],[]))
            self.assertEqual(answer(events),wire['reply'])
            self.assertEqual(context(events)['authority'],'none')
            self.assertEqual(context(events)['nonplanning_message_ids'],['national-message'])
            self.assertIsNotNone(result)

    def test_preview_translation_cannot_publish_or_supply_later_execution_facts(self):
        from cj_api.lio_city import CityReference
        city=CityReference('510100','成都市','四川省','成都市','city','Asia/Shanghai')
        resolution=dict(status='resolved',candidates=[city.__dict__],requested_name='成都',source={})
        for questions in ((),('start_date',),('party_size',),('start_date','party_size')):
            with self.subTest(questions=questions):
                first='去成都玩三天'
                previous=context(run(flow(first),first,resolution=resolution)[1])
                for item in previous['facts'].values():
                    for ref in item['sources']:ref['message_id']='prior-0'
                previous['resolved_city_source_message_id']='prior-0'
                text='请把“从2026-11-20开始，两个人”翻译成英文。'
                quoted=flow(text,city=None,days=None,start='2026-11-20',party=2,index=1,
                            questions=questions,reply='Starting 2026-11-20, two people.')
                quoted.update(planning_request_index=None,needs_tools=False)
                history=(original(first),original(text))
                published,events,lookups,_=run(quoted,text,turns=history,previous=previous,resolution=resolution)
                self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),quoted['reply'])
                previous=context(events)
                self.assertNotIn('start_date',previous['facts']);self.assertNotIn('party_size',previous['facts'])
                self.assertIn('national-message',previous['nonplanning_message_ids'])
                previous['nonplanning_message_ids']=['prior-1']
                following='继续'
                replay=flow(following,city=None,days=None,start='2026-11-20',party=2,index=2,questions=())
                replay['planning_request_index']=0
                replay['field_sources']=[dict(ref,source_index=1,quote=text)for ref in replay['field_sources']]
                published,events,_,_=run(replay,following,turns=(*history,original(following)),
                                         previous=previous,resolution=resolution)
                self.assertEqual(published,[]);self.assertIn('第3天',answer(events))
                self.assertNotIn('2026-11-20',answer(events))
                self.assertNotIn('start_date',context(events)['facts'])
                self.assertNotIn('party_size',context(events)['facts'])

    def test_given_relative_or_absolute_start_saves_without_party(self):
        for text,city,start,locale in [
            ("Plan 4 days in Xi'an from tomorrow","Xi'an",'2026-11-12','en'),
            ('去成都玩三天，从2026-11-20开始','成都','2026-11-20','zh')]:
            published,events,lookups,_=run(flow(text,city=city,days=4 if locale=='en' else 3,start=start),text,locale=locale)
            self.assertEqual(len(published),1);self.assertEqual(len(lookups),1)
            self.assertEqual(published[0][3].fields['arrival']['date']['value'],start)
            self.assertEqual(published[0][3].fields['party_size'],{'state':'missing'})
            self.assertNotIn('几个人',answer(events));self.assertNotIn('How many',answer(events))

    def test_host_asks_one_missing_required_fact_and_preserves_reasonable_question(self):
        text='帮我规划成都行程'
        wire=flow(text,days=None,questions=('duration_days',),reply='这趟你想玩几天？')
        wire['planning_request_index']=0
        published,events,lookups,_=run(wire,text)
        self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),wire['reply'])
        wire=flow('帮我规划行程',city=None,days=None,questions=('city','duration_days'))
        wire['planning_request_index']=0
        published,events,lookups,_=run(wire,'帮我规划行程')
        self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),'想去哪个城市？')

    def test_undated_followup_restores_city_duration_and_preserves_original_date_source(self):
        for first,city,reply,locale in [('去成都玩三天','成都','从明天开始','zh'),
                ("Plan 4 days in Xi'an","Xi'an",'Starting tomorrow','en')]:
            initial=flow(first,city=city,days=4 if locale=='en' else 3)
            previous=context(run(initial,first,locale=locale)[1])
            for item in previous['facts'].values():
                for ref in item['sources']:ref['message_id']='prior-0'
            wire=flow(reply,city=None,days=None,start='2026-11-12',index=1,questions=())
            published,events,_,_=run(wire,reply,locale=locale,turns=(original(first),original(reply)),previous=previous)
            self.assertEqual(len(published),1)
            fields=published[0][3].fields
            self.assertEqual(fields['arrival']['date']['value'],'2026-11-12')
            self.assertEqual(fields['party_size'],{'state':'missing'})
            self.assertNotIn('哪天',answer(events));self.assertNotIn('start date',answer(events))
            self.assertEqual(context(events)['facts']['start_date']['sources'],[dict(message_id='national-message',quote=reply)])

    def test_date_answer_finishes_plan_without_party_question(self):
        first='去成都玩三天';second='从2026-11-20开始'
        previous=context(run(flow(first),first)[1])
        for item in previous['facts'].values():
            for ref in item['sources']:ref['message_id']='prior-0'
        wire=flow(second,city=None,days=None,start='2026-11-20',index=1,reply='一共几位？',questions=('party_size',))
        published,events,_,_=run(wire,second,turns=(original(first),original(second)),previous=previous)
        self.assertEqual(len(published),1);self.assertNotIn('几位',answer(events))
        self.assertEqual(published[0][3].fields['arrival']['date']['value'],'2026-11-20')

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

    def test_pending_plan_translation_cannot_supply_or_cache_execution_facts(self):
        first='去成都玩三天';wire=flow(first)
        previous=context(run(wire,first)[1])
        for item in previous['facts'].values():
            for ref in item['sources']:ref['message_id']='prior-0'
        text='请把“从2026-11-20开始，两个人”翻译成英文。'
        consult=flow(text,city=None,days=None,start='2026-11-20',party=2,index=1,questions=(),reply='Starting 2026-11-20, two people.')
        consult.update(planning_request_index=None,needs_tools=False)
        published,events,lookups,_=run(consult,text,turns=(original(first),original(text)),previous=previous)
        self.assertEqual((published,lookups),([],[]));self.assertEqual(answer(events),consult['reply'])
        retained=context(events)
        self.assertNotIn('start_date',retained['facts']);self.assertNotIn('party_size',retained['facts'])
        following='继续';next_wire=flow(following,city=None,days=None,index=2,questions=('start_date','party_size'))
        published,events,lookups,_=run(next_wire,following,turns=(original(first),original(text),original(following)),previous=retained)
        self.assertEqual(published,[]);self.assertIn('第3天',answer(events));self.assertNotIn('2026-11-20',answer(events))
        # The next model also cannot reuse the translation's valid quoted
        # date/people sources as execution facts instead of using the cache.
        retained['nonplanning_message_ids']=['prior-1']
        next_wire.update(start_date='2026-11-20',party_size=2,question_fields=[])
        next_wire['field_sources'].extend([dict(field=field,source_index=1,quote=text)for field in ('start_date','party_size')])
        published,events,lookups,_=run(next_wire,following,turns=(original(first),original(text),original(following)),previous=retained)
        self.assertEqual(published,[]);self.assertIn('第3天',answer(events));self.assertNotIn('2026-11-20',answer(events))

    def test_same_romanized_city_changed_province_does_not_cache_or_publish_old_date(self):
        from cj_api.lio_city import CityReference
        first='计划江苏Suzhou三天，从2026-11-20开始，两个人'
        initial=flow(first,city='Suzhou',start='2026-11-20',party=2,intent='plan',questions=())
        initial['city']['province']='江苏'
        _,_,facts=parse_flow(json.dumps(initial),(original(first),),(),'prior-0',None)
        old=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        previous=dict(authority='plan',status='needs_details',facts=facts,city=dict(status='resolved',candidates=[old],source={}))
        text='重新规划安徽Suzhou三天'
        new=flow(text,city='Suzhou',index=1,intent='plan',questions=('start_date',))
        new['city']['province']='安徽'
        target=CityReference('341300','宿州市','安徽省','宿州市','city','Asia/Shanghai').__dict__
        resolution=dict(status='resolved',candidates=[target],source={})
        published,events,_,_=run(new,text,turns=(original(first),original(text)),previous=previous,resolution=resolution)
        self.assertEqual(published,[]);next_context=context(events)
        self.assertNotIn('start_date',next_context['facts'])
        for item in next_context['facts'].values():
            for ref in item['sources']:
                if ref['message_id']=='national-message':ref['message_id']='prior-1'
        for key in ('resolved_city_source_message_id','date_boundary_message_id'):
            if next_context.get(key)=='national-message':next_context[key]='prior-1'
        following='继续';last=flow(following,city=None,days=None,index=2,intent='plan',questions=('start_date',))
        last['planning_request_index']=1
        published,events,_,_=run(last,following,turns=(original(first),original(text),original(following)),previous=next_context,resolution=resolution)
        self.assertEqual(published,[]);self.assertIn('第3天',answer(events));self.assertNotIn('2026-11-20',answer(events));self.assertNotIn('start_date',context(events)['facts'])
        # Even a later model re-emission from a valid old quote cannot restore
        # the other province's date after the new adcode has been selected.
        last['start_date']='2026-11-20'
        last['field_sources'].append(dict(field='start_date',source_index=0,quote=first))
        published,events,_,_=run(last,following,turns=(original(first),original(text),original(following)),previous=next_context,resolution=resolution)
        self.assertEqual(published,[]);persisted=context(events)
        self.assertEqual(persisted['date_boundary_message_id'],'prior-1')
        last['current_source_index']=3
        published,events,_,_=run(last,following,turns=(original(first),original(text),original(following),original(following)),previous=persisted,resolution=resolution)
        self.assertEqual(published,[]);self.assertNotIn('start_date',context(events)['facts'])

    def test_revocation_survives_consultation_and_old_request_cannot_regrant(self):
        for hold_text,hold_intent in [('先别自动保存','discuss'),('取消','cancel')]:
            first='规划成都三天，从2026-11-20开始'
            initial=flow(first,start='2026-11-20',questions=('party_size',),intent='plan')
            previous=context(run(initial,first)[1])
            def rekey(value,n):
                for item in value['facts'].values():
                    for ref in item['sources']:
                        if ref['message_id']=='national-message':ref['message_id']='prior-'+str(n)
                for key in ('authority_barrier_message_id','resolved_city_source_message_id','date_boundary_message_id'):
                    if value.get(key)=='national-message':value[key]='prior-'+str(n)
                value['nonplanning_message_ids']=['prior-'+str(n)if mid=='national-message'else mid for mid in value.get('nonplanning_message_ids',[])]
            rekey(previous,0)
            hold=flow(hold_text,city=None,days=None,index=1,intent=hold_intent,questions=())
            hold.update(planning_request_index=None,publication_hold=dict(source_index=1,quote=hold_text))
            history=[original(first),original(hold_text)]
            previous=context(run(hold,hold_text,turns=tuple(history),previous=previous)[1]);rekey(previous,1)
            text='酒店和青旅有什么区别？';consult=flow(text,city=None,days=None,index=2,questions=(),reply='青旅可能提供多人间。')
            consult.update(planning_request_index=None,needs_tools=False)
            history.append(original(text))
            previous=context(run(consult,text,turns=tuple(history),previous=previous)[1]);rekey(previous,2)
            self.assertEqual(previous['authority_barrier_message_id'],'prior-1')
            text='两个人';last=flow(text,city=None,days=None,party=2,index=3,questions=())
            last['planning_request_index']=0;history.append(original(text))
            published,events,_,_=run(last,text,turns=tuple(history),previous=previous)
            self.assertEqual(published,[]);self.assertEqual(context(events)['authority'],'none')
            previous=context(events);rekey(previous,3)
            # A genuine new current planning request can grant authority again.
            text='重新规划成都三天，从2026-11-20开始，两个人'
            new=flow(text,start='2026-11-20',party=2,index=4,questions=(),intent='plan')
            history.append(original(text))
            published,_,_,_=run(new,text,turns=tuple(history),previous=previous)
            self.assertEqual(len(published),1)

    def test_new_city_after_hold_and_consultation_never_revives_old_city_date(self):
        from cj_api.lio_city import CityReference
        first='计划江苏Suzhou三天，从2026-11-20开始，两个人'
        initial=flow(first,city='Suzhou',start='2026-11-20',party=2,intent='plan',questions=())
        initial['city']['province']='江苏'
        _,_,facts=parse_flow(json.dumps(initial),(original(first),),(),'prior-0',None)
        old=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        previous=dict(authority='plan',status='needs_details',facts=facts,city=dict(status='resolved',candidates=[old],source={}))
        history=[original(first)]
        def next_context(wire,text,n,resolution=None):
            nonlocal previous
            history.append(original(text))
            result=run(wire,text,turns=tuple(history),previous=previous,resolution=resolution)
            previous=context(result[1])
            for item in previous['facts'].values():
                for ref in item['sources']:
                    if ref['message_id']=='national-message':ref['message_id']='prior-'+str(n)
            for key in ('authority_barrier_message_id','date_boundary_message_id','resolved_city_source_message_id'):
                if previous.get(key)=='national-message':previous[key]='prior-'+str(n)
            previous['nonplanning_message_ids']=['prior-'+str(n)if mid=='national-message'else mid for mid in previous.get('nonplanning_message_ids',[])]
            return result
        text='先别自动保存';hold=flow(text,city=None,days=None,index=1,questions=())
        hold.update(planning_request_index=None,publication_hold=dict(source_index=1,quote=text))
        self.assertEqual(next_context(hold,text,1)[0],[])
        text='酒店和青旅有什么区别？';consult=flow(text,city=None,days=None,index=2,questions=())
        consult.update(planning_request_index=None,needs_tools=False)
        self.assertEqual(next_context(consult,text,2)[0],[])
        self.assertEqual(previous['city']['candidates'][0]['adcode'],'320500')
        text='重新规划安徽Suzhou三天';new=flow(text,city='Suzhou',index=3,intent='plan',start='2026-11-20',party=2,questions=())
        new['city']['province']='安徽'
        new['field_sources']=[dict(ref,source_index=0,quote=first)if ref['field']in ('start_date','party_size')else ref for ref in new['field_sources']]
        target=CityReference('341300','宿州市','安徽省','宿州市','city','Asia/Shanghai').__dict__
        resolution=dict(status='resolved',candidates=[target],source={})
        self.assertEqual(next_context(new,text,3,resolution)[0],[])
        self.assertEqual(previous['date_boundary_message_id'],'prior-3')
        text='继续';last=flow(text,city=None,days=None,index=4,intent='plan',start='2026-11-20',party=2,questions=())
        last['planning_request_index']=3
        last['field_sources']=[dict(ref,source_index=0,quote=first)for ref in last['field_sources']]
        published,events,_,_=next_context(last,text,4,resolution)
        self.assertEqual(published,[]);self.assertIn('第3天',answer(events));self.assertNotIn('2026-11-20',answer(events));self.assertNotIn('start_date',previous['facts'])

    def test_new_destination_supplied_date_survives_later_party_answer(self):
        from cj_api.lio_city import CityReference
        first='计划江苏Suzhou三天，从2026-11-20开始，两个人'
        initial=flow(first,city='Suzhou',start='2026-11-20',party=2,intent='plan',questions=())
        initial['city']['province']='江苏'
        _,_,facts=parse_flow(json.dumps(initial),(original(first),),(),'prior-0',None)
        old=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        previous=dict(authority='plan',status='needs_details',facts=facts,city=dict(status='resolved',candidates=[old],source={}))
        text='重新规划安徽Suzhou三天，从2026-11-21开始，人数未定'
        new=flow(text,city='Suzhou',start='2026-11-21',index=1,intent='plan',questions=('party_size',))
        new['city']['province']='安徽';new['unknown_fields']=['party_size']
        target=CityReference('341300','宿州市','安徽省','宿州市','city','Asia/Shanghai').__dict__
        resolution=dict(status='resolved',candidates=[target],source={})
        published,events,_,_=run(new,text,turns=(original(first),original(text)),previous=previous,resolution=resolution)
        self.assertEqual(len(published),1);self.assertEqual(published[0][3].fields['arrival']['date']['value'],'2026-11-21');previous=context(events)
        for item in previous['facts'].values():
            for ref in item['sources']:
                if ref['message_id']=='national-message':ref['message_id']='prior-1'
        following='两个人';last=flow(following,city=None,days=None,party=2,index=2,questions=())
        last['planning_request_index']=1
        published,_,_,_=run(last,following,turns=(original(first),original(text),original(following)),previous=previous,resolution=resolution)
        self.assertEqual(published,[]) # no second save from an optional-party answer

    def test_legacy_resolved_context_binds_its_actual_message_before_new_facts(self):
        from cj_api.lio_city import CityReference
        from cj_api.local_lio_national import CONTEXT
        first='计划江苏Suzhou三天，从2026-11-20开始，两个人'
        old=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        legacy=dict(authority='plan',status='needs_details',city=dict(status='resolved',candidates=[old],source={}))
        raw=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id='prior-0',text=first,trip_id=None,creation_intent='none')).encode()
        test=self
        class Database:
            @contextmanager
            def connect(self,scope):
                test.assertEqual(scope,'owner');yield self
            def execute(self,sql,args):
                test.assertEqual(args[:3],('owner','chat','generation'))
                if 'LIMIT %s'in sql:return SimpleNamespace(fetchall=lambda:[('prior-0',0,raw,sha256(raw).hexdigest(),date(2026,11,11),'completed')])
                return SimpleNamespace(fetchone=lambda:('prior-0',CONTEXT+json.dumps(legacy)))
        binding=SimpleNamespace(scope='owner',conversation_id='chat',generation='generation',message_sequence=1)
        text='重新规划安徽Suzhou三天，从2026-11-21开始，人数未定'
        _,_,previous=NationalLioPlanning(Database(),None).context(binding,original(text))
        self.assertEqual(previous['resolved_city_source_message_id'],'prior-0');self.assertNotIn('facts',previous)
        new=flow(text,city='Suzhou',start='2026-11-21',index=1,intent='plan',questions=('party_size',))
        new['city']['province']='安徽';new['unknown_fields']=['party_size']
        target=CityReference('341300','宿州市','安徽省','宿州市','city','Asia/Shanghai').__dict__
        resolution=dict(status='resolved',candidates=[target],source={})
        published,events,_,_=run(new,text,turns=(original(first),original(text)),previous=previous,resolution=resolution)
        self.assertEqual(len(published),1);self.assertEqual(published[0][3].fields['arrival']['date']['value'],'2026-11-21');previous=context(events)
        for item in previous['facts'].values():
            for ref in item['sources']:
                if ref['message_id']=='national-message':ref['message_id']='prior-1'
        following='两个人';last=flow(following,city=None,days=None,party=2,index=2,questions=())
        last['planning_request_index']=1
        published,events,_,_=run(last,following,turns=(original(first),original(text),original(following)),previous=previous,resolution=resolution)
        self.assertEqual(published,[]) # no second save from an optional-party answer
        self.assertNotIn('哪天',answer(events))

    def test_mobile_three_turns_keep_unknown_optional_and_apply_preferences(self):
        for texts,city,locale in [
            (('规划北京三日游','没定日期  没定人数','我就想了解三日北京豪华游'),'北京','zh'),
            (('Plan a three-day Beijing trip','Dates and party size are undecided','I just want a luxury three-day Beijing itinerary'),'Beijing','en')]:
            previous=None;history=[]
            for n,text in enumerate(texts):
                history.append(original(text))
                wire=flow(text,city=city if n==0 else None,days=3 if n==0 else None,index=n,questions=())
                wire['planning_request_index']=0
                if n:wire['unknown_fields']=['start_date','party_size']
                published,events,_,_=run(wire,text,locale=locale,turns=tuple(history),previous=previous)
                self.assertEqual(published,[])
                for day in range(1,4):self.assertIn('第'+str(day)+'天' if locale=='zh' else 'Day '+str(day),answer(events))
                self.assertNotIn('哪天开始',answer(events));self.assertNotIn('How many',answer(events))
                prompt=next(value for kind,value in events if kind=='discussion_input')
                self.assertNotIn('我们才刚认识',prompt);self.assertNotIn("We've only just met",prompt)
                self.assertIn(text,prompt)
                if n==2:self.assertIn('豪华' if locale=='zh' else 'luxury',prompt)
                previous=context(events)
                self.assertNotIn('start_date',previous['facts']);self.assertNotIn('party_size',previous['facts'])
                for item in previous['facts'].values():
                    for ref in item['sources']:
                        if ref['message_id']=='national-message':ref['message_id']='prior-'+str(n)
                for key in ('resolved_city_source_message_id','date_boundary_message_id'):
                    if previous.get(key)=='national-message':previous[key]='prior-'+str(n)

    def test_capability_question_bypasses_planning_in_both_languages(self):
        planning=NationalLioPlanning(None,None)
        for text,locale in (('你能干啥','zh'),('你会干嘛','zh'),('你能帮我做什么','zh'),
                            ('What can you do?','en'),('What can you help me with?','en')):
            events=[]
            class Worker:
                def _event(self,binding,state,kind,value=''):
                    events.append((kind,value))
                    return SimpleNamespace(sequence=state.sequence+1)
            with patch.object(planning,'context')as lookup:
                planning.execute(Worker(),None,SimpleNamespace(sequence=0),text,SimpleNamespace(locale=locale))
                lookup.assert_not_called()
                self.assertEqual([kind for kind,_ in events],['text_delta','completed'])
                self.assertIn('排行程'if locale=='zh'else'Plan your days',events[0][1])
