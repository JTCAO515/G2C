"""Original982 rejection plus literal-source controls; no model/business replay."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import unittest

from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_api.lio_flow_intake import parse_flow
from cj_api.lio_planning_grounding import PlanningTurn
from cj_api.lio_sourced_intake import BookingSourceUnclear
from cj_needs.domain import InvalidInput

CASE=json.loads((Path(__file__).parent/'fixtures/lio982-source-rejection.json').read_bytes())
REFS=({'message_id':'fixture-city-original'},)
TURNS=tuple(PlanningTurn(text,day)for text,day in zip(CASE['turns'],(date(2026,11,12),date(2026,11,14))))


def parse(value,turns=TURNS,previous=None):
    return parse_flow(json.dumps(value),turns,REFS,'fixture-date-followup',previous,schema=OptionalIntake)


def literal_control():
    value=json.loads(CASE['original_output_utf8'])
    # Offline variant only. Production still rejects the untouched original;
    # this is not a server alias/translation or automatic repair path.
    value['city'].update(query='Chengdu',quote='Chengdu')
    return value


class CrossLanguageSources(unittest.TestCase):
    def test_original_complete_output_still_rejects_its_translated_quote(self):
        self.assertEqual(sha256(CASE['original_output_utf8'].encode()).hexdigest(),CASE['original_output_sha256'])
        with self.assertRaisesRegex(InvalidInput,'field quote is not in the original message'):
            parse(json.loads(CASE['original_output_utf8']))

    def test_english_original_city_remains_source0_when_only_dates_and_fixed_meetup_are_added(self):
        intake,questions,facts=parse(literal_control())
        self.assertEqual(intake.city['query'],'Chengdu')
        self.assertEqual((intake.city['quote'],intake.city['source_index']),('Chengdu',0))
        self.assertIsNone(intake.city['province'])
        self.assertEqual(intake.start_date,dict(state='known',value='2026-11-15'))
        self.assertEqual(questions,[])
        fields=intake.extraction['fields']
        self.assertEqual(fields['party_size'],dict(state='unknown'))
        fixed,=fields['fixed_items']
        self.assertEqual(fixed['applies_to'],['self'])
        self.assertEqual((fixed['start']['time']['value'],fixed['end']['time']['value']),('09:00','10:00'))
        self.assertEqual(fixed['start']['place'],dict(state='unknown'))
        self.assertEqual(fixed['end']['place'],dict(state='unknown'))
        self.assertEqual(fixed['booking_status'],dict(state='missing'))
        self.assertEqual(facts['city']['sources'][0]['message_id'],'fixture-city-original')

    def test_same_chinese_continuation_preserves_unknown_people_and_unbooked_meetup(self):
        first='我想去成都玩三天。'
        fixed='第一天我9:00到10:00要在酒店集合，保持不变'
        follow='明天开始。'+fixed+'。酒店名称和位置尚未确定，不要声称已经预订。'
        value=literal_control();value['city'].update(query='成都',quote='成都')
        value['field_sources'][0]['quote']='明天';value['field_sources'][1]['quote']='三天'
        item=value['fixed_items'][0]
        item.update(kind='appointment',label='酒店集合',quote=fixed,start_timezone=None,end_timezone=None)
        intake,questions,_=parse(value,(PlanningTurn(first,date(2026,11,12)),PlanningTurn(follow,date(2026,11,14))))
        self.assertEqual(intake.start_date,dict(state='known',value='2026-11-15'))
        self.assertEqual(questions,[])
        self.assertEqual(intake.extraction['fields']['party_size'],dict(state='unknown'))
        self.assertEqual(intake.extraction['fields']['fixed_items'][0]['booking_status'],dict(state='missing'))

    def test_accepted_earlier_city_is_retained_from_its_real_reference(self):
        from test_lio_planning_flow import flow
        initial=flow(CASE['turns'][0],city='Chengdu',index=0,intent='plan',questions=())
        initial.update(version='LIO-planning-intake.8',needs_tools=False)
        initial['field_sources']=[dict(field='duration_days',source_index=0,quote='three days')]
        _,_,facts=parse_flow(json.dumps(initial),TURNS[:1],(),'fixture-city-original',None,schema=OptionalIntake)
        following=literal_control();following['city']=None
        intake,questions,_=parse(following,previous=dict(facts=facts,authority='plan',status='needs_details'))
        self.assertEqual(intake.city['query'],'Chengdu')
        self.assertEqual(intake.city['quote'],'Chengdu')
        self.assertEqual(intake.city['source_index'],0)
        self.assertEqual(questions,[])

    def test_wrong_source_index_translation_and_fabricated_reservation_are_not_repaired(self):
        for city in (dict(query='成都',quote='成都',source_index=0),
                     dict(query='Chengdu',quote='Chengdu',source_index=1)):
            value=literal_control();value['city'].update(city)
            with self.subTest(city=city),self.assertRaises(InvalidInput):parse(value)
        value=literal_control();value['fixed_items'][0]['booking_evidence']=dict(
            status='booked',source_index=1,quote='fixed hotel meetup')
        with self.assertRaises(BookingSourceUnclear):parse(value)


if __name__=='__main__':unittest.main()
