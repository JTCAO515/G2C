"""Read-only answers do not borrow a missing execution root (#1048)."""
import json
from datetime import date
from pathlib import Path
import unittest

from cj_api.lio_planning_grounding import PlanningTurn
from test_lio_planning_flow import answer,context,flow,original,run


CASES={case['case_id']:case for case in json.loads((Path(__file__).resolve().parents[3]/
    'docs/quality/m4-stage0-1048/regressions.v1.json').read_text())['cases']}


def previous_turn(events):
    value=context(events)
    for fact in value['facts'].values():
        for ref in fact['sources']:ref['message_id']='prior-0'if ref['message_id']=='national-message'else ref['message_id']
    for key in ('nonplanning_message_ids','read_only_data_message_ids'):
        value[key]=['prior-0'if mid=='national-message'else mid for mid in value.get(key,[])]
    return value


class ReadOnlyAnswers(unittest.TestCase):
    def test_plan06_undecided_date_and_party_do_not_block_readonly_days(self):
        for locale in ('zh','en'):
            with self.subTest(locale=locale):
                text=CASES['PLAN06']['inputs'][locale][0]
                wire=flow(text,city='北京'if locale=='zh'else'Beijing',days=3,questions=())
                wire.update(planning_request_index=None,needs_tools=False)
                published,events,lookups,_=run(wire,text,locale=locale)
                self.assertEqual((published,lookups),([],[]))
                for day in (1,2,3):self.assertIn('第'+str(day)+'天'if locale=='zh'else'Day '+str(day),answer(events))
                self.assertEqual(context(events)['authority'],'none')
                self.assertEqual(context(events)['facts']['duration_days']['value'],3)
                self.assertEqual(context(events)['facts']['duration_days']['value'],3)

    def test_bare_city_then_days_without_model_root_keeps_data_not_execution(self):
        for locale,city,first,last in (('zh','成都','去成都','三天'),('en','Chengdu','Go to Chengdu','Three days')):
            with self.subTest(locale=locale):
                wire=flow(first,city=city,days=None,questions=('duration_days',),reply='玩几天？'if locale=='zh'else'How many days?')
                wire.update(planning_request_index=None,needs_tools=True)
                _,events,_,_=run(wire,first,locale=locale)
                previous=previous_turn(events)
                wire=flow(last,city=city,days=3,index=1,questions=())
                wire.update(planning_request_index=None,needs_tools=False)
                wire['city'].update(source_index=0,quote=city)
                published,events,lookups,_=run(wire,last,turns=(original(first),original(last)),previous=previous,locale=locale)
                self.assertEqual((published,lookups),([],[]))
                for day in (1,2,3):self.assertIn('第'+str(day)+'天'if locale=='zh'else'Day '+str(day),answer(events))
                self.assertEqual(context(events)['authority'],'none')

    def test_readonly_date_conflict_asks_instead_of_overwriting_stated_end(self):
        text='规划北京三天，2026-12-01到达，2026-12-05离开。'
        wire=flow(text,city='北京',days=3,start='2026-12-01',questions=())
        wire.update(planning_request_index=None,needs_tools=False)
        next(ref for ref in wire['field_sources']if ref['field']=='start_date')['quote']='2026-12-01到达'
        wire['extra_fields']={'departure':{'date':'2026-12-05','time':None,'timezone':None,'place':None}}
        wire['field_sources'].append(dict(field='departure.date',source_index=0,quote='2026-12-05离开'))
        published,events,lookups,_=run(wire,text)
        self.assertEqual((published,lookups),([],[]))
        self.assertIn('起止日期和天数对不上',answer(events))
        self.assertFalse(any(kind=='discussion_input'for kind,_ in events))

    def test_plan05_complete_readonly_preview_when_model_has_no_execution_root(self):
        for locale in ('zh','en'):
            with self.subTest(locale=locale):
                text=CASES['PLAN05']['inputs'][locale][0]
                wire=flow(text,city='北京'if locale=='zh'else'Beijing',days=3,
                    intent='consult',reply='已了解。'if locale=='zh'else'Got it.',questions=())
                wire.update(planning_request_index=None,needs_tools=False)
                published,events,_,_=run(wire,text,locale=locale)
                self.assertEqual(published,[])
                self.assertFalse(any(kind=='registered'for kind,_ in events))
                self.assertIn('北京'if locale=='zh'else'Beijing',answer(events))
                for day in (1,2,3):
                    self.assertIn(('第'+str(day)+'天')if locale=='zh'else('Day '+str(day)),answer(events))
                self.assertNotIn('2026-',answer(events))
                self.assertEqual(context(events)['authority'],'none')

    def test_plan08_readonly_preview_keeps_original_dates_without_a_root_grant(self):
        for locale in ('zh','en'):
            with self.subTest(locale=locale):
                text=CASES['PLAN08']['inputs'][locale][0]
                wire=flow(text,city='北京'if locale=='zh'else'Beijing',days=4,start='2026-11-17',party=1,
                    intent='consult',reply='已了解。'if locale=='zh'else'Got it.',questions=())
                wire.update(planning_request_index=None,needs_tools=False)
                published,events,lookups,_=run(wire,text,turns=(PlanningTurn(text,date(2026,11,15)),),locale=locale)
                self.assertEqual((published,lookups),([],[]))
                for day in (1,2,3,4):self.assertIn('第'+str(day)+'天'if locale=='zh'else'Day '+str(day),answer(events))
                prompt=json.loads(next(value for kind,value in events if kind=='discussion_input'))[1]
                self.assertIn('2026-11-17 through 2026-11-20',prompt)
                self.assertNotIn('itinerary has no start date',prompt)
                self.assertEqual(context(events)['authority'],'none')

    def test_plan09_missing_root_keeps_the_models_sourced_duration_question(self):
        for locale,first,city in (
            ('zh',CASES['PLAN09']['inputs']['zh'][0],'北京'),
            ('en',CASES['PLAN09']['inputs']['en'][0],'Beijing'),
            ('zh','去成都','成都'),('en','Go to Chengdu','Chengdu'),
        ):
            with self.subTest(locale=locale,first=first):
                reply='你想玩几天？'if locale=='zh'else'How many days would you like?'
                wire=flow(first,city=city,days=None,intent='consult',reply=reply,questions=('duration_days',))
                wire.update(planning_request_index=None,needs_tools=True)
                published,events,lookups,result=run(wire,first,locale=locale)
                self.assertEqual((published,lookups),([],[]))
                self.assertEqual(answer(events),reply)
                self.assertIsNotNone(result)
                self.assertEqual(context(events)['authority'],'none')
                self.assertEqual(context(events)['status'],'needs_details')
                self.assertEqual(set(context(events)['facts']),{'city'})

    def test_readonly_city_question_keeps_its_actual_human_source(self):
        first='成都有哪些值得看的地方？';current='请规划成都旅行'
        wire=flow(current,city='成都',days=None,index=1,questions=('duration_days',),reply='想玩几天？')
        wire.update(planning_request_index=None,needs_tools=False)
        wire['city'].update(source_index=0,quote='成都')
        published,events,lookups,_=run(wire,current,turns=(original(first),original(current)))
        self.assertEqual((published,lookups),([],[]))
        self.assertEqual(context(events)['facts']['city']['sources'],[dict(message_id='prior-0',quote='成都')])

    def test_new_explicit_save_reuses_readonly_human_city_and_days(self):
        first='规划成都三天';current='请保存，2026-12-01出发，两个人'
        wire=flow(first,city='成都',days=3,questions=())
        wire.update(planning_request_index=None,needs_tools=False)
        _,events,_,_=run(wire,first)
        previous=previous_turn(events)
        followup=flow(current,city=None,days=None,start='2026-12-01',party=2,intent='save',index=1,questions=())
        followup.update(planning_request_index=1,needs_tools=False)
        published,events,_,_=run(followup,current,turns=(original(first),original(current)),previous=previous)
        self.assertEqual(len(published),1)
        self.assertNotIn('哪个城市',answer(events))
        self.assertNotIn('几天',answer(events))
        # A model-labelled save rooted only at a new "continue" is no grant.
        current='继续'
        forged=flow(current,city=None,days=None,intent='save',index=1,questions=())
        forged.update(planning_request_index=1,needs_tools=False)
        published,_,_,_=run(forged,current,turns=(original(first),original(current)),previous=previous)
        self.assertEqual(published,[])

    def test_readonly_known_date_party_are_data_but_an_old_root_stays_denied(self):
        first='规划成都三天，2026-12-01出发，两个人'
        wire=flow(first,city='成都',days=3,start='2026-12-01',party=2,questions=())
        wire.update(planning_request_index=None,needs_tools=False)
        _,events,_,_=run(wire,first)
        previous=previous_turn(events)
        for text,root,expected in (('请保存',1,1),('继续',0,0),('继续',1,0)):
            with self.subTest(text=text,root=root):
                followup=flow(text,city=None,days=None,intent='save',index=1,questions=())
                followup.update(planning_request_index=root,needs_tools=False)
                published,events,_,_=run(followup,text,turns=(original(first),original(text)),previous=previous)
                self.assertEqual(len(published),expected)

    def test_readonly_data_marker_never_promotes_translated_dates_or_party(self):
        first='规划成都三天。请翻译“2026-12-01出发，两个人”';current='请保存'
        wire=flow(first,city='成都',days=3,questions=())
        wire.update(planning_request_index=None,needs_tools=False)
        wire['field_sources'][0]['quote']='三天'
        _,events,_,_=run(wire,first)
        previous=previous_turn(events)
        followup=flow(current,city=None,days=None,start='2026-12-01',party=2,intent='save',index=1,questions=())
        followup.update(planning_request_index=1,needs_tools=False)
        followup['field_sources']=[dict(field='start_date',source_index=0,quote='2026-12-01出发'),
                                   dict(field='party_size',source_index=0,quote='两个人')]
        published,events,_,_=run(followup,current,turns=(original(first),original(current)),previous=previous)
        self.assertEqual(published,[])
        self.assertNotIn('start_date',context(events)['facts'])
        self.assertNotIn('party_size',context(events)['facts'])

    def test_qa06_failed_human_data_can_support_details_without_a_failed_root_grant(self):
        for locale in ('zh','en'):
            with self.subTest(locale=locale):
                first=CASES['PLAN05']['inputs'][locale][0]
                followup=CASES['QA06']['inputs'][locale][1]
                city='北京'if locale=='zh'else'Beijing'
                wire=flow(followup,city=city,days=3,intent='consult',reply='已了解。'if locale=='zh'else'Got it.',
                    questions=(),index=1)
                wire.update(planning_request_index=0,needs_tools=False)
                wire['city'].update(source_index=0,quote=city)
                wire['field_sources']=[dict(field='duration_days',source_index=0,quote='三日'if locale=='zh'else'three-day')]
                previous=dict(authority='none',status='consult',facts={},uncompleted_request_message_ids=['prior-0'])
                published,events,_,_=run(wire,followup,turns=(original(first),original(followup)),previous=previous,locale=locale)
                self.assertEqual(published,[])
                self.assertFalse(any(kind=='registered'for kind,_ in events))
                for day in (1,2,3):self.assertIn('第'+str(day)+'天'if locale=='zh'else'Day '+str(day),answer(events))
                self.assertEqual(context(events)['authority'],'none')


if __name__=='__main__':unittest.main()
