"""Build31 literal source dates; old profiles, missing sources and ambiguity stay closed."""
from datetime import date
import json
import unittest

from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_api.lio_national_intake import literal_dates
from cj_api.lio_flow_intake import parse_flow
from cj_api.lio_planning_grounding import PlanningTurn
from cj_needs.domain import InvalidInput
from test_lio_planning_flow import flow


def parsed(text,expected,*,quote=None):
    value=flow(text,city='北京' if '北京'in text else 'Beijing',days=3,start=expected,party=2,questions=())
    value['version']='LIO-planning-intake.8'
    for source in value['field_sources']:
        if source['field']=='start_date':source['quote']=quote or text
    return parse_flow(json.dumps(value),(PlanningTurn(text,date(2026,11,13)),),(),'date-original',None,schema=OptionalIntake)[0]


class DateFormats(unittest.TestCase):
    def test_jt_date_forms_and_year_first_variants(self):
        for notation in ('26.12.01','26年12月1日','2026.12.1','2026/12/01','2026-12-01'):
            for text in ('规划三天北京豪华游 '+notation+'出发 两个人',
                         'Plan a three-day luxury trip to Beijing starting '+notation+' for two people.'):
                with self.subTest(text=text):
                    result=parsed(text,'2026-12-01',quote=notation)
                    self.assertEqual(result.start_date,dict(state='known',value='2026-12-01'))
                    self.assertEqual(result.duration_days,3)

    def test_invalid_dates_and_model_changed_dates_are_not_repaired(self):
        for notation in ('26.13.01','26.02.30','26年0月1日','2026/12/32'):
            with self.subTest(notation=notation),self.assertRaises(InvalidInput):
                parsed('规划北京三天 '+notation+'出发 两个人','2026-12-01',quote=notation)
        for wrong in ('1926-12-01','2126-12-01','2026-11-01','2026-12-02'):
            with self.subTest(wrong=wrong),self.assertRaises(InvalidInput):
                parsed('规划北京三天 26.12.01出发 两个人',wrong,quote='26.12.01')

    def test_clipped_denials_alternatives_and_repeated_dates_cannot_grant_a_start(self):
        for text,quote in (('规划北京三天，两个人，不是26.12.01出发','26.12.01'),
                           ('规划北京三天，两个人，26.12.01不行','26.12.01'),
                           ('规划北京三天，两个人，26.12.01或26.12.02出发','26.12.01或26.12.02'),
                           ('Plan Beijing for three days, two people, not 26.12.01.','26.12.01')):
            with self.subTest(text=text),self.assertRaises(InvalidInput):parsed(text,'2026-12-01',quote=quote)

    def test_original_source_index_and_day_do_not_shift_on_continuation(self):
        first='规划北京三天 26年12月1日出发 两个人'
        value=flow(first,city='北京',days=3,start='2026-12-01',party=2,questions=())
        value.update(version='LIO-planning-intake.8',current_source_index=1)
        result=parse_flow(json.dumps(value),(PlanningTurn(first,date(2026,11,13)),PlanningTurn('继续',date(2026,11,20))),
                          (dict(message_id='original-date'),),'continuation',None,schema=OptionalIntake)[0]
        self.assertEqual(result.start_date['value'],'2026-12-01')

    def test_missing_duration_source_stays_rejected(self):
        text='规划三天北京豪华游 26.12.01出发 两个人'
        value=flow(text,city='北京',days=3,start='2026-12-01',party=2,questions=())
        value.update(version='LIO-planning-intake.8')
        value['field_sources']=[ref for ref in value['field_sources']if ref['field']!='duration_days']
        with self.assertRaisesRegex(InvalidInput,'original bounded duration required'):
            parse_flow(json.dumps(value),(PlanningTurn(text,date(2026,11,13)),),(),'source-missing',None,schema=OptionalIntake)

    def test_only_complete_year_first_calendar_literals_are_recognized(self):
        for text in ('26.12','12.01','126.12.01','26.12.011','2026.12/01'):
            with self.subTest(text=text):self.assertEqual(literal_dates(text),[])


if __name__=='__main__':unittest.main()
