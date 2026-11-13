"""Date truth controls from #907's read-only diagnostic inventory, not model E2E proof."""
from datetime import date,timedelta
import json
from types import SimpleNamespace
import unittest

from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_api.lio_flow_intake import parse_flow
from cj_api.lio_planning_grounding import PlanningTurn
from cj_api.local_lio_national import NationalLioPlanning
from cj_needs.domain import InvalidInput
from test_lio_planning_flow import flow
import test_lio_national_execution as national_execution


# Exact diagnostic phrasing is retained; date_quote identifies original source,
# not a repaired model response. Original China question day is 2026-11-13.
CASES=(
 ('Z1','规划三天北京豪华游 26.12.01出发 两个人','北京',3,2,'2026-12-01','26.12.01'),
 ('Z2','规划三天上海豪华游 26年12月1日出发 两个人出行','上海',3,2,'2026-12-01','26年12月1日'),
 ('Z3','帮我规划成都4天，12月1日出发，一个人','成都',4,1,'2026-12-01','12月1日'),
 ('Z4','去西安玩五天，明天出发，三个人，经济一点','西安',5,3,'2026-11-14','明天'),
 ('Z5','下周二去杭州玩四天，就我一个人','杭州',4,1,'2026-11-17','下周二'),
 ('Z6','大后天去厦门玩三天','厦门',3,None,'2026-11-16','大后天'),
 ('Z9','规划南京三日游 2026.12.01 出发','南京',3,None,'2026-12-01','2026.12.01'),
 ('Z10','周六出发去苏州玩两天，我和老婆','苏州',2,2,'2026-11-14','周六'),
 ('Z12','下礼拜三开始，北京三天，四个人，经济游','北京',3,4,'2026-11-18','下礼拜三'),
 ('Z13','元旦去哈尔滨玩四天，两个人','哈尔滨',4,2,'2027-01-01','元旦'),
 ('Z17','规划北京三天，明天开始，第一天9:00–10:00酒店集合已确定，两个人','北京',3,2,'2026-11-14','明天'),
 ('Z18','26/12/01 出发，三亚五天豪华游，一家三口','三亚',5,3,'2026-12-01','26/12/01'),
 ('Z20','3天后出发去桂林玩四天，一个人','桂林',4,1,'2026-11-16','3天后'),
 ('E1','Plan 3 days in Beijing from 26.12.01 for two, luxury','Beijing',3,2,'2026-12-01','26.12.01'),
 ('E2','Plan a 4-day Shanghai trip starting Dec 1, 2026, just me','Shanghai',4,1,'2026-12-01','Dec 1, 2026'),
 ('E3',"5 days in Xi'an from tomorrow, 3 people, budget","Xi'an",5,3,'2026-11-14','tomorrow'),
 ('E4','Chengdu for 4 days next Tuesday, solo','Chengdu',4,1,'2026-11-17','next Tuesday'),
 ('E7','Trip to Guangzhou, 3 days, starting 12/1, two of us','Guangzhou',3,2,'2026-12-01','12/1'),
 ('E8','Plan Nanjing 3 days from Saturday, me and my wife','Nanjing',3,2,'2026-11-14','Saturday'),
 ('E10','Plan 4 days in Xiamen starting the day after tomorrow, 4 adults','Xiamen',4,4,'2026-11-15','the day after tomorrow'),
 ('E13','Plan Changsha 3 days from tomorrow, morning/afternoon/evening each day, 2 people','Changsha',3,2,'2026-11-14','tomorrow'),
 ('E14','帮我 plan 北京 3 days，tomorrow 出发，2 people','北京',3,2,'2026-11-14','tomorrow'),
 ('E15','下周二 go Shanghai 四天，one person, cheap','Shanghai',4,1,'2026-11-17','下周二'),
 ('E16','Shenzhen 五天 luxury trip，26年12月1日 start，两个人','Shenzhen',5,2,'2026-12-01','26年12月1日'),
 ('E17','Plan 3 days in Suzhou from 2026-12-01; day 1 hotel meetup 09:00–10:00 is fixed; 2 people','Suzhou',3,2,'2026-12-01','2026-12-01'),
 ('E18','Sanya 6 days, leaving in 3 days, family of three','Sanya',6,3,'2026-11-16','in 3 days'),
 ('E20',"Plan 3 days in Harbin starting New Year's Day, 2 people",'Harbin',3,2,'2027-01-01',"New Year's Day"),
)


def intake(text,city,days,party,start,quote):
    value=flow(text,city=city,days=days,start=start,party=party,questions=())
    value['version']='LIO-planning-intake.8'
    for source in value['field_sources']:
        if source['field']=='start_date':source['quote']=quote
    return value


class DiagnosticDates(unittest.TestCase):
    def test_original_diagnostic_date_notation_is_checked_exactly(self):
        for key,text,city,days,party,start,quote in CASES:
            value=intake(text,city,days,party,start,quote)
            with self.subTest(case=key):
                result=parse_flow(json.dumps(value),(PlanningTurn(text,date(2026,11,13)),),(),'diagnostic-original',None,schema=OptionalIntake)[0]
                self.assertEqual(result.start_date,dict(state='known',value=start))
                self.assertEqual(result.duration_days,days)
                self.assertEqual(result.extraction['fields']['party_size'],dict(state='missing')if party is None else dict(state='known',value=party))
            if key!='Z17' and key!='E17':
                wrong=intake(text,city,days,party,'2026-12-05'if start!='2026-12-05'else'2026-12-06',quote)
                with self.subTest(case=key,wrong=True),self.assertRaises(InvalidInput):
                    parse_flow(json.dumps(wrong),(PlanningTurn(text,date(2026,11,13)),),(),'diagnostic-wrong-date',None,schema=OptionalIntake)

    def test_known_nonplanning_questions_do_not_enter_the_intake(self):
        planner=NationalLioPlanning(None,None)
        for text,locale in (('第一次来中国建议怎么玩','zh'),('First time in China, any tips?','en')):
            self.assertIsNone(planner.execute(None,None,None,text,SimpleNamespace(locale=locale)))

    def test_coarse_week_and_undecided_dates_remain_unknown_not_today(self):
        for text,city,days in (('规划广州六天豪华游，没定日期，没定人数','广州',6),('去重庆玩七天','重庆',7),
                               ('I want to visit Hangzhou for 6 days, dates not decided','Hangzhou',6),
                               ('Plan 7 days in Yunnan, luxury, no dates yet, 2 people','Yunnan',7)):
            value=flow(text,city=city,days=days,start=None,party=None,questions=())
            value.update(version='LIO-planning-intake.8',unknown_fields=['start_date'])
            result=parse_flow(json.dumps(value),(PlanningTurn(text,date(2026,11,13)),),(),'undated-original',None,schema=OptionalIntake)[0]
            self.assertEqual(result.start_date,dict(state='unknown'))
            self.assertFalse(result.publication_hold)

    def test_three_turn_date_and_people_replies_reuse_original_facts(self):
        for language,city,texts in (
            ('zh','昆明',('去昆明玩五天','12月3日出发','三个人')),
            ('en','Kunming',('Plan Kunming 5 days','Dec 3','three people')),
        ):
            turns=[];refs=[];previous=None
            for index,text in enumerate(texts):
                turns.append(PlanningTurn(text,date(2026,11,13)+timedelta(days=index)))
                value=flow(text,city=city if index==0 else None,days=5 if index==0 else None,
                           start='2026-12-03'if index==1 else None,party=3 if index==2 else None,index=index,questions=())
                value.update(version='LIO-planning-intake.8',planning_request_index=0)
                result,_,facts=parse_flow(json.dumps(value),tuple(turns),tuple(refs),'turn-'+str(index),previous,schema=OptionalIntake)
                self.assertEqual(result.duration_days,5)
                if index:self.assertEqual(result.start_date['value'],'2026-12-03')
                if index==2:self.assertEqual(result.extraction['fields']['party_size'],dict(state='known',value=3))
                refs.append(dict(message_id='turn-'+str(index)))
                previous=dict(facts=facts)

    def test_explicit_range_day_count_conflict_asks_without_needs_or_trip_publication(self):
        from cj_api.lio_city import CityReference
        city=CityReference('370200','青岛市','山东省','青岛市','city','Asia/Shanghai')
        resolution=dict(status='resolved',candidates=[city.__dict__],requested_name='青岛',source={})
        for text,quote,locale in (('12月1日到12月5日去青岛，玩三天','12月1日到12月5日','zh'),
                                  ('Plan Qingdao Dec 1 to Dec 5, 3 days','Dec 1 to Dec 5','en')):
            value=flow(text,city='青岛'if locale=='zh'else'Qingdao',days=3,start='2026-12-01',party=None,questions=())
            value.update(version='LIO-planning-intake.8')
            value['extra_fields']={'departure':dict(date='2026-12-05',time=None,timezone=None,place=None)}
            for reference in value['field_sources']:
                if reference['field']=='start_date':reference['quote']=quote
            value['field_sources'].append(dict(field='departure.date',source_index=0,quote=quote))
            runner=national_execution.NationalExecution()
            published,events,_,_=runner.run_intake(runner.envelope(text),flow_output=value,resolution=resolution,locale=locale,
                                                 turns=(PlanningTurn(text,date(2026,11,13)),))
            self.assertEqual(published,[])
            self.assertFalse(any(kind=='registered'for kind,_ in events))
            self.assertTrue(any(kind=='completed'for kind,_ in events))
            answer=''.join(value for kind,value in events if kind=='text_delta')
            self.assertIn('日期范围'if locale=='zh'else'date range',answer)


if __name__=='__main__':unittest.main()
