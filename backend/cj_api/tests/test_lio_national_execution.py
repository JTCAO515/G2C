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


class NationalExecution(unittest.TestCase):
    def envelope(self,text,*,city='上海',source_index=0,intent='plan',start='2026-11-20',party=2):
        fields={};sources={}
        if start:
            fields['arrival']={'date':dict(state='known',value=start)}
            sources['arrival.date']=[dict(source_index=source_index,quote=start)]
        if party:
            fields['party_size']=dict(state='known',value=party)
            sources['party_size']=[dict(source_index=source_index,quote='两个人')]
        return dict(version='LIO-planning-intake.1',intent=intent,reply='可以先比较旅行安排。',needs_tools=False,
            city=dict(query=city,normalized_name=None,province=None,source_index=source_index,quote=city),duration_days=None,
            extraction=dict(version='NEEDS-extraction.1',fields=fields,unresolved=[],long_term_requests=[]),
            field_sources=sources,current_request=text)

    def run_intake(self,value,*,turns=None,previous=None,resolution=None):
        text=value['current_request'];turns=turns or (PlanningTurn(text,date(2026,11,11)),)
        city=CityReference('310000','上海市','上海市',None,'province','Asia/Shanghai')
        resolution=resolution or dict(status='resolved',candidates=[city.__dict__],requested_name='上海',source={})
        published=[];events=[];lookups=[]
        class Worker:
            memory_run=None;message_context=None;provider=object();lio_city_context=None
            def _registered_stream(self,*args,**kwargs):yield json.dumps(value,ensure_ascii=False)
            def _event(self,binding,state,kind,value='',**kwargs):
                events.append((kind,value));return SimpleNamespace(sequence=state.sequence+1)
        worker=Worker();worker.tools=SimpleNamespace(resolve_city=lambda *a:(lookups.append(a) or resolution))
        planning=NationalLioPlanning(None,lambda *a:published.append(a) or a[2])
        planning.context=lambda *a:(turns,(),previous)
        binding=SimpleNamespace(message_id='national-message',run_id='national-run')
        with patch('cj_api.local_lio_national.register',side_effect=lambda w,b,s,d:s):
            result=planning.execute(worker,binding,SimpleNamespace(sequence=0),text,SimpleNamespace(question_day=date(2026,11,11),locale='zh'))
        return published,events,lookups,result

    def test_device_chinese_request_reaches_structured_intake_not_beijing_regex(self):
        text='计划上海三日豪华游，从2026-11-20开始，两个人'
        value=self.envelope(text);value['duration_days']=3
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
