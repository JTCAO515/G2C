"""Actual national intake orchestration and publication fences; no supplier calls."""
from dataclasses import replace
from datetime import date
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cj_api.lio_city import CityReference
from cj_api.lio_national_intake import parse
from cj_api.lio_planning_grounding import PlanningTurn
from cj_api.local_lio_national import NationalLioPlanning
from cj_message.lio_plan_needs import BOUND_EFFECT


class NationalExecution(unittest.TestCase):
    def envelope(self,text,*,city='上海',source_index=0,intent='plan',start='2026-11-20',party=2):
        fields={};sources={}
        if start:
            fields['arrival']={'date':dict(state='known',value=start)}
            fields['departure']={'date':dict(state='known',value=start)}
            sources['arrival.date']=[dict(source_index=source_index,quote=start)]
            sources['departure.date']=[dict(source_index=source_index,quote=start)]
        if party:
            fields['party_size']=dict(state='known',value=party)
            sources['party_size']=[dict(source_index=source_index,quote='两个人')]
        return dict(version='LIO-planning-intake.1',intent=intent,reply='可以先比较旅行安排。',needs_tools=False,
            city=dict(query=city,normalized_name=None,province=None,source_index=source_index,quote=city),duration_days=None,
            extraction=dict(version='NEEDS-extraction.1',fields=fields,unresolved=[],long_term_requests=[]),
            field_sources=sources,current_request=text)

    def run_intake(self,value,*,turns=None,previous=None,resolution=None,same_destination=True):
        text=value['current_request'];turns=turns or (PlanningTurn(text,date(2026,11,11)),)
        city=CityReference('310000','上海市','上海市',None,'province','Asia/Shanghai')
        resolution=resolution or dict(status='resolved',candidates=[city.__dict__],requested_name='上海',source={})
        published=[];events=[];lookups=[]
        class Worker:
            memory_run=None;message_context=None;provider=object();lio_city_context=None;lio_memory=None
            def _registered_stream(self,*args,**kwargs):yield json.dumps(value,ensure_ascii=False)
            def _event(self,binding,state,kind,value='',**kwargs):
                events.append((kind,value));return SimpleNamespace(sequence=state.sequence+1)
        worker=Worker();worker.tools=SimpleNamespace(resolve_city=lambda *a:(lookups.append(a) or resolution))
        class Save:
            def __call__(self,*args):published.append(args);return args[2]
            def supports_destination(self,binding,city):return same_destination
        planning=NationalLioPlanning(None,Save())
        planning.context=lambda *a:(turns,(),previous)
        binding=SimpleNamespace(message_id='national-message',run_id='national-run')
        with patch('cj_api.local_lio_national.register',side_effect=lambda w,b,s,d:events.append(('registered',BOUND_EFFECT)) or s):
            result=planning.execute(worker,binding,SimpleNamespace(sequence=0),text,SimpleNamespace(question_day=date(2026,11,11),locale='zh'))
        return published,events,lookups,result

    def test_device_chinese_request_reaches_structured_intake_not_beijing_regex(self):
        text='计划上海三日豪华游，从2026-11-20开始，两个人'
        value=self.envelope(text);value['duration_days']=3
        value['extraction']['fields'].pop('departure');value['field_sources'].pop('departure.date')
        value['field_sources']['duration_days']=[dict(source_index=0,quote='三日')]
        published,events,lookups,_=self.run_intake(value)
        self.assertEqual(len(published),1)
        fields=published[0][3].fields
        self.assertEqual(fields['arrival']['place']['value'],'上海市')
        self.assertEqual(fields['departure']['date']['value'],'2026-11-22')
        self.assertEqual(len(lookups),1)

    def test_date_only_answer_does_not_regrant_after_refused_save(self):
        text='上海2026-11-20，两个人'
        value=self.envelope(text)
        published,events,_,_=self.run_intake(value,previous=dict(authority='none',status='discussion'))
        self.assertEqual(published,[])
        self.assertEqual(events[-1][0],'completed')

    def test_date_reply_continues_only_original_positive_pending_authority(self):
        text='上海2026-11-20，两个人'
        for authority,expected in [('plan',1),('none',0)]:
            with self.subTest(authority=authority):
                value=self.envelope(text)
                value['extraction']['fields']['departure']={'date':dict(state='known',value='2026-11-20')}
                value['field_sources']['departure.date']=[dict(source_index=0,quote='2026-11-20')]
                published,_,_,_=self.run_intake(value,previous=dict(authority=authority,status='needs_details'))
                self.assertEqual(len(published),expected)

    def test_missing_party_or_start_asks_without_publication(self):
        for start,party in [(None,2),('2026-11-20',None)]:
            with self.subTest(start=start,party=party):
                text='计划上海2026-11-20，两个人'
                published,events,_,_=self.run_intake(self.envelope(text,start=start,party=party))
                self.assertEqual(published,[])
                self.assertTrue(any(kind=='text_delta' and ('几个人' in value or '哪天' in value) for kind,value in events))

    def test_ambiguous_city_never_publishes_or_chooses_first(self):
        value=self.envelope('计划上海2026-11-20，两个人')
        candidates=[CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__,
                    CityReference('341300','宿州市','安徽省','宿州市','city','Asia/Shanghai').__dict__]
        published,events,_,_=self.run_intake(value,resolution=dict(status='ambiguous',candidates=candidates,source={}))
        self.assertEqual(published,[])
        self.assertTrue(any('江苏省' in text and '安徽省' in text for kind,text in events if kind=='text_delta'))

    def test_translation_confirmation_uses_only_prior_single_provider_candidate(self):
        text='上海2026-11-20，两个人'
        value=parse(json.dumps(self.envelope(text)),(PlanningTurn(text,date(2026,11,11)),))
        city=CityReference('440100','广州市','广东省','广州市','city','Asia/Shanghai').__dict__
        previous=dict(city=dict(status='confirmation_required',candidates=[city],source={'original':'receipt'}))
        self.assertEqual(NationalLioPlanning._previous_city(value,previous,'Yes')['candidates'],[city])
        previous['city']['candidates'].append(dict(city,adcode='440300',name='深圳市'))
        self.assertIsNone(NationalLioPlanning._previous_city(value,previous,'Yes'))

    def test_withdrawal_and_conditional_holds_win_over_model_plan(self):
        for tail in ('，不要保存','，先讨论','，等我确认','; only if it is open','; do not save'):
            with self.subTest(tail=tail):
                value=self.envelope('计划上海2026-11-20，两个人'+tail)
                published,_,_,_=self.run_intake(value)
                self.assertEqual(published,[])

    def test_bad_model_date_quote_is_rejected_before_city_lookup(self):
        value=self.envelope('计划上海2026-11-20，两个人')
        value['extraction']['fields']['arrival']['date']['value']='2026-12-20'
        from cj_agent.provider import ProviderUnknown
        with self.assertRaises(ProviderUnknown):self.run_intake(value)


    def test_discussion_revokes_before_missing_or_ambiguous_city_question(self):
        value=self.envelope("Let's just discuss destinations.",intent='discuss',start=None,party=None)
        value['city']=None
        _,events,_,_=self.run_intake(value,previous=dict(authority='plan',status='needs_city'))
        context=json.loads(next(v.split(':',1)[1] for k,v in events if v.startswith('lio_planning_context.1:')))
        self.assertEqual(context['authority'],'none')
        complete=self.envelope('上海2026-11-20，两个人')
        published,_,_,_=self.run_intake(complete,previous=context)
        self.assertEqual(published,[])
        value['city']=dict(query='destinations',normalized_name=None,province=None,source_index=0,quote='destinations')
        city=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        _,events,_,_=self.run_intake(value,previous=dict(authority='plan',status='needs_details'),
            resolution=dict(status='ambiguous',candidates=[city,dict(city,adcode='341300',name='宿州市',province='安徽省')],source={}))
        context=json.loads(next(v.split(':',1)[1] for k,v in events if v.startswith('lio_planning_context.1:')))
        self.assertEqual(context['authority'],'none')

    def test_model_only_province_cannot_suppress_original_ambiguity(self):
        from test_lio_city import data
        from cj_api.lio_city import resolve
        text='计划Suzhou 2026-11-20，两个人'
        value=self.envelope(text,city='Suzhou');value['city']['province']='江苏'
        intake=parse(json.dumps(value),(PlanningTurn(text,date(2026,11,11)),))
        self.assertIsNone(intake.city['province'])
        self.assertEqual(resolve(data(),intake.city['query'],intake.city['province'])['status'],'ambiguous')
        text+='，江苏';value['current_request']=text
        intake=parse(json.dumps(value),(PlanningTurn(text,date(2026,11,11)),))
        self.assertEqual(resolve(data(),intake.city['query'],intake.city['province'])['status'],'resolved')

    def test_relative_date_stays_with_its_original_question_day(self):
        from cj_needs.domain import InvalidInput
        for phrase,correct in [('明天','2026-11-12'),('后天','2026-11-13'),('tomorrow','2026-11-12'),('the day after tomorrow','2026-11-13')]:
            with self.subTest(phrase=phrase):
                text='计划上海，从'+phrase+'开始，两个人'
                value=self.envelope(text,start='2027-01-10')
                for edge in ('arrival','departure'):value['field_sources'][edge+'.date']=[dict(source_index=0,quote=phrase)]
                turns=(PlanningTurn(text,date(2026,11,11)),)
                with self.assertRaises(InvalidInput):parse(json.dumps(value),turns)
                for edge in ('arrival','departure'):value['extraction']['fields'][edge]['date']['value']=correct
                self.assertEqual(parse(json.dumps(value),turns).extraction['fields']['arrival']['date']['value'],correct)

    def test_incomplete_or_omitted_fixed_item_asks_even_when_model_unresolved_is_empty(self):
        text='计划上海2026-11-20，两个人，我已订酒店'
        for omit in (False,True):
            with self.subTest(omitted=omit):
                value=self.envelope(text)
                if not omit:
                    event={k:dict(state='missing') for k in ('date','time','timezone','place')}
                    value['extraction']['fields']['fixed_items']=[dict(item_id='hotel',kind='hotel',description='我已订酒店',
                        applies_to=['party'],locked=dict(state='known',value=True),booking_status=dict(state='known',value='booked'),
                        start=event,end=event)]
                    value['field_sources']['fixed_items']=[dict(source_index=0,quote='我已订酒店')]
                published,events,_,_=self.run_intake(value)
                self.assertEqual(published,[])
                self.assertTrue(any('谁参加' in v for k,v in events if k=='text_delta'))


    def test_explicit_province_correction_does_not_reuse_same_spelling_city(self):
        text='计划安徽省Suzhou，从2026-11-20开始，两个人'
        value=self.envelope(text,city='Suzhou');value['city']['province']='安徽省'
        intake=parse(json.dumps(value),(PlanningTurn(text,date(2026,11,11)),))
        old=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        previous=dict(city=dict(status='resolved',candidates=[old],source={}))
        self.assertIsNone(NationalLioPlanning._previous_city(intake,previous,text))
        value['current_request']=text.replace('安徽省','江苏省');value['city']['province']='江苏省'
        intake=parse(json.dumps(value),(PlanningTurn(value['current_request'],date(2026,11,11)),))
        self.assertEqual(NationalLioPlanning._previous_city(intake,previous,value['current_request'])['candidates'],[old])

    def test_fixed_values_must_match_original_clocks_dates_subject_and_lock(self):
        import copy
        declaration='全体酒店集合已预约2026-11-20 09:00到10:00，不可更改'
        text='计划上海2026-11-20到2026-11-22，两个人。'+declaration
        value=self.envelope(text)
        value['extraction']['fields']['departure']['date']['value']='2026-11-22'
        value['field_sources']['departure.date'][0]['quote']='2026-11-22'
        def event(day,clock):
            return dict(date=dict(state='known',value=day),time=dict(state='known',value=clock),
                timezone=dict(state='known',value='Asia/Shanghai'),place=dict(state='missing'))
        item=dict(item_id='hotel',kind='appointment',description=declaration,applies_to=['party'],
            locked=dict(state='known',value=True),booking_status=dict(state='known',value='booked'),
            start=event('2026-11-20','09:00'),end=event('2026-11-20','10:00'))
        value['extraction']['fields']['fixed_items']=[item]
        value['field_sources']['fixed_items']=[dict(source_index=0,quote=declaration)]
        self.assertEqual(len(self.run_intake(value)[0]),1)
        for change in ('date','clock','subject','lock'):
            with self.subTest(change=change):
                altered=copy.deepcopy(value);fixed=altered['extraction']['fields']['fixed_items'][0]
                if change=='date':
                    for edge in ('start','end'):fixed[edge]['date']['value']='2026-11-21'
                elif change=='clock':
                    fixed['start']['time']['value']='13:00';fixed['end']['time']['value']='14:00'
                elif change=='subject':fixed['applies_to']=['self']
                else:fixed['locked']['value']=False
                published,events,_,_=self.run_intake(altered)
                self.assertEqual(published,[])
                self.assertTrue(any('谁参加' in v for k,v in events if k=='text_delta'))
        second='全体午餐已预订2026-11-21 12:00到13:00，不可更改'
        for joiner in ('；','，并且',' and also '):
            with self.subTest(joiner=joiner):
                value['current_request']=text+joiner+second
                self.assertEqual(self.run_intake(value)[0],[])

    def test_natural_fixed_day_number_keeps_explicit_self_and_unbooked_status(self):
        for declaration in ('第一天我9:00–10:00要在酒店集合，这项安排已确定，保持不变',
                            'On day 1 I have a fixed hotel meetup from 9 to 10 a.m., keep it unchanged',
                            'On day 1 I have a fixed hotel meetup from 9 to 10 a.m.; keep it unchanged'):
            with self.subTest(declaration=declaration):
                text='计划上海2026-11-20，仅我一人。'+declaration
                value=self.envelope(text,party=1)
                value['field_sources']['party_size'][0]['quote']='仅我一人'
                def event(clock):
                    return dict(date=dict(state='known',value='2026-11-20'),time=dict(state='known',value=clock),
                        timezone=dict(state='known',value='Asia/Shanghai'),place=dict(state='missing'))
                value['extraction']['fields']['fixed_items']=[dict(item_id='hotel',kind='appointment',description=declaration,
                    applies_to=['self'],locked=dict(state='known',value=True),booking_status=dict(state='unknown'),
                    start=event('09:00'),end=event('10:00'))]
                value['field_sources']['fixed_items']=[dict(source_index=0,quote=declaration)]
                self.assertEqual(len(self.run_intake(value)[0]),1)


    def test_a_negated_province_does_not_filter_the_city_candidates(self):
        text='计划Suzhou，从2026-11-20开始，两个人，我指安徽宿州，不是江苏苏州'
        value=self.envelope(text,city='Suzhou');value['city']['province']='江苏'
        intake=parse(json.dumps(value),(PlanningTurn(text,date(2026,11,11)),))
        self.assertIsNone(intake.city['province'])
        value['city']['province']='安徽'
        self.assertEqual(parse(json.dumps(value),(PlanningTurn(text,date(2026,11,11)),)).city['province'],'安徽')


    def test_different_destination_retains_current_trip_and_requests_new_conversation(self):
        published,events,_,_=self.run_intake(self.envelope('计划上海2026-11-20，两个人'),same_destination=False)
        self.assertEqual(published,[])
        self.assertTrue(any('新开对话' in v for k,v in events if k=='text_delta'))
        self.assertFalse(any(k=='registered' and v==BOUND_EFFECT for k,v in events))


    def test_latest_province_denial_revokes_prior_affirmative_and_cached_city(self):
        old='计划Suzhou，江苏，2026-11-20，两个人'
        current='不是江苏，是安徽'
        value=self.envelope(old,city='Suzhou');value['current_request']=current;value['city']['province']='江苏'
        turns=(PlanningTurn(old,date(2026,11,11)),PlanningTurn(current,date(2026,11,11)))
        intake=parse(json.dumps(value),turns)
        self.assertIsNone(intake.city['province'])
        city=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        self.assertIsNone(NationalLioPlanning._previous_city(intake,dict(city=dict(status='resolved',candidates=[city],source={})),current))
        same=old+'，不是江苏而是安徽'
        value['current_request']=same
        self.assertIsNone(parse(json.dumps(value),(PlanningTurn(same,date(2026,11,11)),)).city['province'])

    def test_national_names_preserve_conditional_ambiguity_and_locked_item_fences(self):
        from test_lio_edit_selection import itinerary,known
        from cj_api.lio_edit_selection import select_lio_edit
        trip,_=itinerary()
        for text in ("Replace the second afternoon with Riverside Park but don't apply.",
                     '把第二天下午换成人民公园不要改。',
                     'Replace the second afternoon with Riverside Park or West Lake.'):
            with self.subTest(text=text):
                result=select_lio_edit(trip,text,'en','hold',starts_on=date(2026,11,11),national_names=True)
                self.assertEqual(result.status,'clarify')
        for label in ('上海博物馆','杜甫草堂','象鼻山','广州塔','西湖'):
            result=select_lio_edit(trip,'把第二天下午换成'+label,'zh','national',starts_on=date(2026,11,11),national_names=True)
            self.assertEqual(result.status,'preview')
        locked,_=itinerary(known(True))
        self.assertEqual(select_lio_edit(locked,'把第二天下午换成西湖','zh','locked',starts_on=date(2026,11,11),national_names=True).status,'protected')


    def test_equal_district_name_requires_original_administrative_code(self):
        from base64 import b64encode
        from contextlib import contextmanager
        from cj_api.local_lio_planning import LioPlanSave
        from cj_needs.domain import Snapshot
        from cj_needs.contract_v1 import encode_snapshot
        binding=SimpleNamespace(scope='owner',conversation_id='chat')
        snapshot=Snapshot('source-needs',1,json.dumps(dict(arrival=dict(date=dict(state='known',value='2026-11-20'),
            time=dict(state='missing'),timezone=dict(state='known',value='Asia/Shanghai'),place=dict(state='known',value='朝阳区')))).encode())
        current=SimpleNamespace(needs_source=json.dumps(dict(snapshot=b64encode(encode_snapshot(snapshot)).decode())))
        code=['110105']
        class Database:
            @contextmanager
            def connect(self,scope):
                assert scope=='owner'
                yield SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchall=lambda:[('lio_city_resolution.1:'+json.dumps(
                    dict(status='resolved',candidates=[dict(adcode=code[0])])),)]))
        save=LioPlanSave(Database(),SimpleNamespace(repository=object()),None,source_window=True)
        with patch('cj_trip.planning_context.read_current',return_value=current):
            self.assertFalse(save.supports_destination(binding,CityReference('220104','朝阳区','吉林省','长春市','district','Asia/Shanghai')))
            self.assertTrue(save.supports_destination(binding,CityReference('110105','朝阳区','北京市','北京市','district','Asia/Shanghai')))

    def test_disambiguating_original_destination_keeps_its_sourced_dates(self):
        old='计划Suzhou，从2026-11-20开始，两个人'
        current='我指安徽宿州'
        value=self.envelope(old,city='Suzhou');value['current_request']=current
        value['city']=dict(query='宿州',normalized_name=None,province='安徽',source_index=1,quote='宿州')
        js=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        ah=CityReference('341300','宿州市','安徽省','宿州市','city','Asia/Shanghai').__dict__
        previous=dict(authority='plan',status='ambiguous',city=dict(status='ambiguous',candidates=[js,ah],source={}))
        published,_,_,_=self.run_intake(value,turns=(PlanningTurn(old,date(2026,11,11)),PlanningTurn(current,date(2026,11,11))),
            previous=previous,resolution=dict(status='resolved',candidates=[ah],source={}))
        self.assertEqual(len(published),1)
        self.assertEqual(published[0][3].fields['arrival']['date']['value'],'2026-11-20')

    def test_changed_province_cannot_borrow_dates_even_when_city_quote_is_older(self):
        old='计划江苏Suzhou，从2026-11-20开始，两个人'
        current='我指安徽的Suzhou'
        value=self.envelope(old,city='Suzhou');value['current_request']=current;value['city']['province']='安徽'
        js=CityReference('320500','苏州市','江苏省','苏州市','city','Asia/Shanghai').__dict__
        ah=CityReference('341300','宿州市','安徽省','宿州市','city','Asia/Shanghai').__dict__
        previous=dict(authority='plan',status='needs_details',city=dict(status='resolved',candidates=[js],source={}))
        published,events,_,_=self.run_intake(value,turns=(PlanningTurn(old,date(2026,11,11)),PlanningTurn(current,date(2026,11,11))),
            previous=previous,resolution=dict(status='resolved',candidates=[ah],source={}))
        self.assertEqual(published,[])
        self.assertTrue(any('哪天' in v for k,v in events if k=='text_delta'))


    def test_keep_unchanged_cannot_be_omitted_when_fixed_word_is_absent(self):
        text='计划上海2026-11-20，两个人。On day 1 I have a hotel meetup from 9 to 10 a.m.; keep it unchanged'
        published,events,_,_=self.run_intake(self.envelope(text))
        self.assertEqual(published,[])
        self.assertTrue(any('谁参加' in v for k,v in events if k=='text_delta'))
