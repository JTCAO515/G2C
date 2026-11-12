"""A week is not a specific departure day; weekdays bind their original day."""
from datetime import date
import json
import unittest
from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_api.lio_flow_intake import parse_flow
from cj_api.lio_planning_grounding import PlanningTurn
from cj_needs.domain import InvalidInput
from test_lio_planning_flow import flow


def parsed(text,start,*,quote=None,uncertain=False):
    value=flow(text,city='北京',days=3,start=start,party=1,questions=())
    value['version']='LIO-planning-intake.8'
    if uncertain:value['uncertain_fields']={'start_date':quote}
    for source in value['field_sources']:
        if source['field']=='start_date':source['quote']=quote or text
    return parse_flow(json.dumps(value),(PlanningTurn(text,date(2026,11,12)),),(),'synthetic-original',None,schema=OptionalIntake)[0]


class DatePrecision(unittest.TestCase):
    def test_week_without_day_cannot_authorize_a_specific_date(self):
        for quote in ('下周','计划下周去','next week'):
            text='计划北京三天，一个人，'+quote
            with self.subTest(quote=quote),self.assertRaises(InvalidInput):parsed(text,'2026-11-19',quote=quote)

    def test_next_weekday_rejects_wrong_day_or_wrong_week(self):
        for phrase in ('下周二出发','next Tuesday','Tuesday next week'):
            text='计划北京三天，一个人，'+phrase
            self.assertEqual(parsed(text,'2026-11-17',quote=phrase).start_date,dict(state='known',value='2026-11-17'))
            for wrong in ('2026-11-19','2026-11-24'):
                with self.subTest(phrase=phrase,wrong=wrong),self.assertRaises(InvalidInput):parsed(text,wrong,quote=phrase)

    def test_range_quote_binds_start_without_matching_every_weekday(self):
        phrase='下周二到周五，周二开始'
        self.assertEqual(parsed('计划北京三天，一个人，'+phrase,'2026-11-17',quote=phrase).start_date['value'],'2026-11-17')

    def test_week_after_next_is_not_a_next_week_substring(self):
        phrase='下下周二出发'
        self.assertEqual(parsed('计划北京三天，一个人，'+phrase,'2026-11-24',quote=phrase).start_date['value'],'2026-11-24')
        with self.assertRaises(InvalidInput):parsed('计划北京三天，一个人，'+phrase,'2026-11-17',quote=phrase)

    def test_weekend_without_a_day_is_not_an_exact_departure(self):
        for phrase in ('next weekend','下周末','this weekend'):
            with self.subTest(phrase=phrase),self.assertRaises(InvalidInput):
                parsed('计划北京三天，一个人，'+phrase,'2026-12-01',quote=phrase)

    def test_legacy_profile_compiler_stays_frozen(self):
        from test_lio_national_execution import NationalExecution
        from cj_api.lio_national_intake import parse
        text='计划上海三天，下周二到周五，周二开始，两个人'
        value=NationalExecution().envelope(text,start='2026-11-17')
        for field in ('arrival.date','departure.date'):
            value['field_sources'][field][0]['quote']='下周二到周五，周二开始'
        result=parse(json.dumps(value),(PlanningTurn(text,date(2026,11,12)),))
        self.assertEqual(result.extraction['fields']['arrival']['date']['value'],'2026-11-17')

    def test_coarse_departure_cannot_authorize_a_precise_saved_window(self):
        text='计划上海从2026-11-13玩到下周'
        value=flow(text,city='上海',days=None,start='2026-11-13',party=None,questions=())
        value.update(version='LIO-planning-intake.8',planning_request_index=0)
        value['extra_fields']={'departure':{'date':'2026-12-25','time':None,'timezone':None,'place':None}}
        value['field_sources'].append(dict(field='departure.date',source_index=0,quote='下周'))
        from test_lio_national_execution import NationalExecution
        from cj_agent.provider import ProviderUnknown
        with self.assertRaises(ProviderUnknown):
            NationalExecution().run_intake(NationalExecution().envelope(text),flow_output=value)

    def test_full_week_range_can_bind_each_endpoint(self):
        phrase='下周二到下周五，周二开始'
        self.assertEqual(parsed('计划北京三天，一个人，'+phrase,'2026-11-17',quote=phrase).start_date['value'],'2026-11-17')

    def test_denied_corrected_and_alternative_weekdays_cannot_grant_a_date(self):
        for phrase in ('不是下周二，而是下下周二','下周二或下周五','not next Tuesday but next Friday'):
            text='计划北京三天，一个人，'+phrase
            with self.subTest(phrase=phrase),self.assertRaises(InvalidInput):
                parsed(text,'2026-11-17',quote=phrase)
        with self.assertRaises(InvalidInput):
            parsed('计划北京三天，一个人，不是下周二','2026-11-17',quote='下周二')

    def test_short_week_quote_cannot_clip_denial_after_it_or_select_a_repeat(self):
        for text,quote in (('计划北京三天，一个人，下周二不行','下周二'),
                           ('计划北京三天，一个人，next Tuesday is not possible','next Tuesday'),
                           ('计划北京三天，一个人，下周二可以吗？不是下周二。','下周二')):
            with self.subTest(text=text),self.assertRaises(InvalidInput):parsed(text,'2026-11-17',quote=quote)

    def test_coarse_week_stays_uncertain_and_does_not_block_intake(self):
        text='计划北京三天，一个人，下周去'
        result=parsed(text,None,quote='下周去',uncertain=True)
        self.assertEqual(result.start_date,dict(state='uncertain',note='下周去'))
        self.assertEqual(result.duration_days,3)

    def test_weekday_uses_original_message_day_not_later_answer_day(self):
        text='计划北京三天，一个人，下周二出发'
        value=flow(text,city='北京',days=3,start='2026-11-17',party=1,questions=())
        value.update(version='LIO-planning-intake.8',current_source_index=1)
        turns=(PlanningTurn(text,date(2026,11,12)),PlanningTurn('继续',date(2026,11,19)))
        result=parse_flow(json.dumps(value),turns,(dict(message_id='first'),),'second',None,schema=OptionalIntake)[0]
        self.assertEqual(result.start_date['value'],'2026-11-17')
        value['start_date']='2026-11-24'
        with self.assertRaises(InvalidInput):parse_flow(json.dumps(value),turns,(dict(message_id='first'),),'second',None,schema=OptionalIntake)

    def test_explicit_iso_date_and_relative_tomorrow_remain_supported(self):
        for quote,expected in (('从2026-11-19开始','2026-11-19'),('从明天开始','2026-11-13')):
            text='计划北京三天，一个人，'+quote
            self.assertEqual(parsed(text,expected,quote=quote).start_date['value'],expected)


if __name__=='__main__':unittest.main(verbosity=2)
