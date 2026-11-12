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

    def test_coarse_week_stays_uncertain_and_does_not_block_intake(self):
        text='计划北京三天，一个人，下周去'
        result=parsed(text,None,quote='下周去',uncertain=True)
        self.assertEqual(result.start_date,dict(state='uncertain',note='下周去'))
        self.assertEqual(result.duration_days,3)

    def test_explicit_iso_date_and_relative_tomorrow_remain_supported(self):
        for quote,expected in (('从2026-11-19开始','2026-11-19'),('从明天开始','2026-11-13')):
            text='计划北京三天，一个人，'+quote
            self.assertEqual(parsed(text,expected,quote=quote).start_date['value'],expected)


if __name__=='__main__':unittest.main(verbosity=2)
