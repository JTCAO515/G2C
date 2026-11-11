"""Canonical start and source-bound fixed facts; public C wording, no live calls."""
from copy import deepcopy
from datetime import date
import json
from types import SimpleNamespace
import unittest
from jsonschema import Draft202012Validator,ValidationError
from cj_agent.lio_intake_start_schema import response_format
from cj_api.lio_national_intake import parse,fields_for,fixed_sources_complete,StartDateConflict,FixedTimezoneConflict
from cj_api.lio_city import CityReference
from cj_needs.domain import InvalidInput
import test_lio_national_execution as fixtures

ZH_FIXED='第一天我9:00–10:00要在酒店集合，这项安排已确定，保持不变'
EN_FIXED='On day 1 I have a fixed hotel meetup from 9 to 10 a.m.; keep it unchanged'


def sample(locale='zh',party=False):
    first='去成都玩三天' if locale=='zh' else 'Plan a three-day trip to Chengdu.'
    start='从明天开始' if locale=='zh' else 'Start tomorrow'
    fixed=ZH_FIXED if locale=='zh' else EN_FIXED
    follow=start+'。 '+fixed+('；酒店名称和位置尚未确定。' if locale=='zh' else '. The hotel name and location are not known yet.')
    texts=[first,follow]
    if party:texts.append('只有我一人，酒店集合也只有我本人参加。' if locale=='zh' else 'It is just me; the hotel meetup is also only for me.')
    turns=tuple(SimpleNamespace(text=t,question_day=date(2026,11,12)) for t in texts)
    def event(clock):return dict(date=dict(state='known',value='2026-11-13'),time=dict(state='known',value=clock),timezone=dict(state='missing'),place=dict(state='missing'))
    item=dict(item_id='hotel',kind='appointment',label='酒店集合' if locale=='zh' else 'hotel meetup',
        source_ref=dict(source_index=1,quote=fixed),detail_refs=[],applies_to=['self'],locked=dict(state='known',value=True),
        booking_status=dict(state='missing'),start=event('09:00'),end=event('10:00'))
    fields={'fixed_items':[item],'party_size':dict(state='missing')};sources=dict(start_date=[dict(source_index=1,quote=start)],
        duration_days=[dict(source_index=0,quote='三天' if locale=='zh' else 'three-day')])
    if party:
        fields['party_size']=dict(state='known',value=1);sources['party_size']=[dict(source_index=2,quote=texts[2])]
        item['detail_refs']=[dict(source_index=2,quote=texts[2])]
    value=dict(version='LIO-planning-intake.4',intent='plan',reply='请补充人数。',needs_tools=False,
        city=dict(query='成都' if locale=='zh' else 'Chengdu',normalized_name=None,province=None,source_index=0,quote=first),
        current_source_index=len(turns)-1,duration_days=3,start_date=dict(state='known',value='2026-11-13'),
        extraction=dict(version='LIO-execution-extraction.1',fields=fields,unresolved=[],long_term_requests=[]),field_sources=sources)
    return value,turns


CITY=CityReference('510100','成都市','四川省','成都市','city','Asia/Shanghai')


def checked(value,turns):
    Draft202012Validator(response_format(len(turns)-1)['json_schema']['schema']).validate(value)
    return parse(json.dumps(value),turns,version='LIO-planning-intake.4')


def prepared(intake,turns):return fields_for(intake,CITY,message_id='start-date',run_id='run-start',source_text='\n'.join(t.text for t in turns))[0]


class StartSchema(unittest.TestCase):
    def test_bilingual_start_is_not_lost_inside_fixed_item_and_missing_person_only_is_asked(self):
        for locale in ('zh','en'):
            with self.subTest(locale=locale):
                value,turns=sample(locale);original=deepcopy(value)
                intake=checked(value,turns);fields=prepared(intake,turns)
                self.assertEqual(fields['arrival']['date']['value'],'2026-11-13')
                self.assertEqual(fields['departure']['date']['value'],'2026-11-15')
                self.assertEqual(intake.sources['arrival.date'],value['field_sources']['start_date'])
                self.assertEqual(intake.extraction['fields']['fixed_items'][0]['description'],value['extraction']['fields']['fixed_items'][0]['source_ref']['quote'])
                self.assertEqual(value,original)
                legacy=fixtures.NationalExecution().envelope(turns[-1].text,start=None,party=None)
                published,events,_,_=fixtures.NationalExecution().run_intake(legacy,turns=turns,
                    previous=dict(authority='plan',status='needs_details'),model_output=value)
                self.assertEqual(published,[])
                self.assertTrue(any('几个人' in text for kind,text in events if kind=='text_delta'))
                self.assertFalse(any('哪天开始' in text for kind,text in events if kind=='text_delta'))

    def test_person_answer_then_fixed_source_and_missing_timezone_compile_without_invention(self):
        for locale in ('zh','en'):
            value,turns=sample(locale,True);intake=checked(value,turns);fields=prepared(intake,turns)
            self.assertTrue(fixed_sources_complete(intake,fields,turns,CITY))
            fixed,=fields['fixed_items']
            self.assertEqual((fixed['start']['time']['value'],fixed['end']['time']['value']),('09:00','10:00'))
            self.assertEqual(fixed['start']['timezone'],dict(state='known',value='Asia/Shanghai'))
            self.assertEqual(fixed['booking_status'],dict(state='missing'))
            legacy=fixtures.NationalExecution().envelope(turns[-1].text,start=None,party=None)
            published,_,_,_=fixtures.NationalExecution().run_intake(legacy,turns=turns,
                previous=dict(authority='plan',status='needs_details'),model_output=value)
            self.assertEqual(len(published),1)

    def test_start_requires_its_own_source_and_cannot_reanchor_on_person_answer_day(self):
        value,turns=sample('en',True)
        turns=(*turns[:-1],SimpleNamespace(text=turns[-1].text,question_day=date(2026,11,13)))
        self.assertEqual(checked(value,turns).start_date['value'],'2026-11-13')
        value['start_date']['value']='2026-11-14'
        with self.assertRaises(InvalidInput):parse(json.dumps(value),turns,version='LIO-planning-intake.4')
        value,turns=sample();value['field_sources'].pop('start_date')
        with self.assertRaises(InvalidInput):parse(json.dumps(value),turns,version='LIO-planning-intake.4')

    def test_missing_canonical_start_is_not_inferred_from_known_arrival_or_fixed_dates(self):
        value,turns=sample('zh',True);value['start_date']={'state':'missing'}
        value['extraction']['fields']['arrival']={k:dict(state='missing') for k in ('date','time','timezone','place')}
        value['extraction']['fields']['arrival']['date']=dict(state='known',value='2026-11-13')
        value['field_sources']['arrival.date']=value['field_sources']['start_date'];value['field_sources'].pop('start_date')
        legacy=fixtures.NationalExecution().envelope(turns[-1].text,start=None,party=None)
        published,events,_,_=fixtures.NationalExecution().run_intake(legacy,turns=turns,
            previous=dict(authority='plan',status='needs_details'),model_output=value)
        self.assertEqual(published,[])
        self.assertTrue(any('行程也从这天开始吗' in text for kind,text in events if kind=='text_delta'))

    def test_conflicting_arrival_asks_and_does_not_overwrite_or_register(self):
        value,turns=sample('zh',True);value['extraction']['fields']['arrival']={k:dict(state='missing') for k in ('date','time','timezone','place')}
        value['extraction']['fields']['arrival']['date']=dict(state='known',value='2026-11-12')
        value['field_sources']['arrival.date']=[dict(source_index=1,quote='从明天开始')]
        # Keep the contradictory arrival explicitly grounded in its own prior statement.
        turns=(turns[0],SimpleNamespace(text=turns[1].text+' 到达日是2026-11-12。',question_day=turns[1].question_day),turns[2])
        value['field_sources']['arrival.date']=[dict(source_index=1,quote='2026-11-12')]
        intake=checked(value,turns)
        with self.assertRaises(StartDateConflict):prepared(intake,turns)
        legacy=fixtures.NationalExecution().envelope(turns[-1].text,start=None,party=None)
        published,events,_,_=fixtures.NationalExecution().run_intake(legacy,turns=turns,
            previous=dict(authority='plan',status='needs_details'),model_output=value)
        self.assertEqual(published,[])
        self.assertTrue(any('开始日与已给的到达日不同' in text for kind,text in events if kind=='text_delta'))

    def test_fixed_source_label_and_item_detail_association_are_independent_guards(self):
        value,turns=sample('zh',True)
        bad=deepcopy(value);bad['extraction']['fields']['fixed_items'][0]['source_ref']['source_index']=0
        with self.assertRaises(InvalidInput):parse(json.dumps(bad),turns,version='LIO-planning-intake.4')
        bad=deepcopy(value);bad['extraction']['fields']['fixed_items'][0]['label']='未提供的酒店'
        with self.assertRaises(InvalidInput):parse(json.dumps(bad),turns,version='LIO-planning-intake.4')
        unclear=deepcopy(value);unclear['extraction']['fields']['fixed_items'][0]['detail_refs']=[dict(source_index=2,quote='只有我一人')]
        self.assertTrue(checked(unclear,turns).fixed_detail_ambiguous)
        legacy=fixtures.NationalExecution().envelope(turns[-1].text,start=None,party=None)
        published,events,_,_=fixtures.NationalExecution().run_intake(legacy,turns=turns,
            previous=dict(authority='plan',status='needs_details'),model_output=unclear)
        self.assertEqual(published,[])
        self.assertTrue(any('针对哪一项' in text for kind,text in events if kind=='text_delta'))

    def test_missing_zone_is_derived_but_explicit_unknown_or_conflicting_zone_is_not(self):
        for state in ('unknown','uncertain'):
            value,turns=sample('zh',True)
            zone=dict(state=state,**({'note':'timezone not settled'} if state=='uncertain' else {}))
            value['extraction']['fields']['fixed_items'][0]['start']['timezone']=zone
            intake=checked(value,turns)
            with self.assertRaises(FixedTimezoneConflict):prepared(intake,turns)
            self.assertEqual(intake.extraction['fields']['fixed_items'][0]['start']['timezone'],zone)
        for marker in ('America/Los_Angeles','UTC+8','CST','CET','CEST','EET','EEST','HKT','SGT','XYZ timezone'):
            value,turns=sample('zh',True);ref=value['extraction']['fields']['fixed_items'][0]['source_ref'];old=ref['quote'];ref['quote']+=' '+marker
            turns=(turns[0],SimpleNamespace(text=turns[1].text.replace(old,ref['quote'],1),question_day=turns[1].question_day),turns[2])
            with self.assertRaises(FixedTimezoneConflict):prepared(checked(value,turns),turns)

    def test_explicit_offsets_zulu_or_unknown_clock_zone_never_default_to_destination(self):
        for suffix in (' (+01:00)',' (+0100)',' Z',' z',' XYZ','（+01:00）','（+0100）','（XYZ）','（＋０１：００）','（−01:00）'):
            with self.subTest(suffix=suffix):
                value,turns=sample('zh',True);ref=value['extraction']['fields']['fixed_items'][0]['source_ref'];old=ref['quote']
                ref['quote']=old.replace('9:00–10:00','9:00–10:00'+suffix)
                turns=(turns[0],SimpleNamespace(text=turns[1].text.replace(old,ref['quote'],1),question_day=turns[1].question_day),turns[2])
                with self.assertRaises(FixedTimezoneConflict):prepared(checked(value,turns),turns)
        value,turns=sample('en',True)
        self.assertTrue(fixed_sources_complete(checked(value,turns),prepared(checked(value,turns),turns),turns,CITY))

    def test_clock_or_locked_marker_omission_cannot_publish_after_compilation(self):
        value,turns=sample('zh',True);value['extraction']['fields']['fixed_items'][0]['start']['time']['value']='08:00'
        intake=checked(value,turns);self.assertFalse(fixed_sources_complete(intake,prepared(intake,turns),turns,CITY))
        value,turns=sample('zh',True)
        other='第二天全体午餐已预订12:00到13:00，不可更改'
        turns=(turns[0],SimpleNamespace(text=turns[1].text+' '+other,question_day=turns[1].question_day),turns[2])
        intake=checked(value,turns);self.assertFalse(fixed_sources_complete(intake,prepared(intake,turns),turns,CITY))

    def test_source_bound_extraction_version_is_explicit_and_nonexecution_start_is_null(self):
        value,turns=sample();value['extraction']['version']='NEEDS-extraction.1'
        with self.assertRaises(InvalidInput):parse(json.dumps(value),turns,version='LIO-planning-intake.4')
        value,turns=sample();value.update(intent='discuss',extraction=None,duration_days=None,field_sources={},start_date=None)
        self.assertIsNone(checked(value,turns).start_date)
        value['start_date']={'state':'missing'}
        with self.assertRaises(ValidationError):Draft202012Validator(response_format(1)['json_schema']['schema']).validate(value)
        with self.assertRaises(InvalidInput):parse(json.dumps(value),turns,version='LIO-planning-intake.4')


    def test_one_primary_cannot_merge_two_distinct_locked_commitments(self):
        for joiner in ('；','，并且',' and also ', '、然后'):
            with self.subTest(joiner=joiner):
                value,turns=sample('zh',True);first=value['extraction']['fields']['fixed_items'][0]['source_ref']['quote']
                second='第一天我9:00–10:00要在博物馆集合，这项安排已确定，保持不变'
                combined=first+joiner+second
                turns=(turns[0],SimpleNamespace(text=turns[1].text.replace(first,combined,1),question_day=turns[1].question_day),turns[2])
                value['extraction']['fields']['fixed_items'][0]['source_ref']['quote']=combined
                intake=checked(value,turns)
                self.assertFalse(fixed_sources_complete(intake,prepared(intake,turns),turns,CITY))

    def test_generic_detail_cannot_authorize_two_primary_arrangements(self):
        value,turns=sample('zh',True)
        a='第一天我在酒店甲集合，这项安排已确定，保持不变'
        b='第二天我在酒店乙集合，这项安排已确定，保持不变'
        detail='集合本人09:00到10:00'
        texts=[turns[0].text,'从明天开始。'+a+'；'+b,'只有我一人。'+detail]
        turns=tuple(SimpleNamespace(text=t,question_day=date(2026,11,12)) for t in texts)
        item=value['extraction']['fields']['fixed_items'][0]
        items=[]
        for n,quote in enumerate((a,b)):
            fixed=deepcopy(item);fixed.update(item_id='hotel-'+str(n),label='集合',source_ref=dict(source_index=1,quote=quote),
                detail_refs=[dict(source_index=2,quote=detail)])
            for edge in ('start','end'):fixed[edge]['date']['value']='2026-11-'+str(13+n)
            items.append(fixed)
        value['extraction']['fields']['fixed_items']=items
        value['field_sources']['party_size']=[dict(source_index=2,quote='只有我一人')]
        self.assertTrue(checked(value,turns).fixed_detail_ambiguous)
        legacy=fixtures.NationalExecution().envelope(texts[-1],start=None,party=None)
        published,events,_,_=fixtures.NationalExecution().run_intake(legacy,turns=turns,
            previous=dict(authority='plan',status='needs_details'),model_output=value)
        self.assertEqual(published,[])
        self.assertTrue(any('针对哪一项' in text for kind,text in events if kind=='text_delta'))
        # Distinct original names and explicitly named details resolve both.
        da='酒店甲集合本人09:00到10:00';db='酒店乙集合本人09:00到10:00'
        turns=(*turns[:-1],SimpleNamespace(text='只有我一人。'+da+'；'+db,question_day=date(2026,11,12)))
        for fixed,label,quote in zip(items,('酒店甲集合','酒店乙集合'),(da,db)):
            fixed['label']=label;fixed['detail_refs']=[dict(source_index=2,quote=quote)]
        intake=checked(value,turns)
        self.assertFalse(intake.fixed_detail_ambiguous)
        self.assertTrue(fixed_sources_complete(intake,prepared(intake,turns),turns,CITY))
