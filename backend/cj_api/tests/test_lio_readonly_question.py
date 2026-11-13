"""A malformed fact envelope cannot block or authorize a control-only question."""
from copy import deepcopy
from datetime import date
import json
import unittest

from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_api.lio_flow_intake import ReadOnlyPlanningQuestion,parse_flow
from cj_api.lio_planning_grounding import PlanningTurn
from cj_needs.domain import InvalidInput
import test_lio_national_execution as execution
from test_lio_planning_flow import flow


def response(text='规划北京行程',city='北京',locale='zh'):
    value=flow(text,city=city,days=None,start=None,party=None,intent='plan',questions=('duration_days',),
               reply='好的，去**北京**。你打算玩几天？'if locale=='zh'else'How many days would you like to spend in Beijing?')
    value.update(version='LIO-planning-intake.8',planning_request_index=0,needs_tools=False,
                 unknown_fields=['start_date','party_size','start_date','party_size'])
    value['city']['quote']=text
    value['field_sources']=[dict(field=field,quote='',source_index=0)for field in ('start_date','duration_days','party_size')]
    return value


def parsed(value,text,*,schema=OptionalIntake,previous=None,refs=()):
    return parse_flow(json.dumps(value,ensure_ascii=False),(PlanningTurn(text,date(2026,11,13)),),refs,
                      'question-original',previous,schema=schema)


class ReadOnlyQuestion(unittest.TestCase):
    def test_original_question_controls_survive_without_accepting_invalid_fact_metadata(self):
        for text,city,locale in (('规划北京行程','北京','zh'),('Plan a trip to Beijing.','Beijing','en')):
            wire=response(text,city,locale)
            question,fields,facts=parsed(wire,text)
            self.assertIsInstance(question,ReadOnlyPlanningQuestion)
            self.assertEqual(question.reply,wire['reply'])
            self.assertEqual(fields,['duration_days'])
            self.assertEqual(set(facts),{'city'})
            self.assertEqual(facts['city']['value']['query'],city)
            self.assertNotIn('field_sources',facts)
            self.assertEqual(wire['unknown_fields'],['start_date','party_size','start_date','party_size'])

    def test_host_completes_question_without_tool_needs_or_trip_effects(self):
        for text,city,locale in (('规划北京行程','北京','zh'),('Plan a trip to Beijing.','Beijing','en')):
            wire=response(text,city,locale);runner=execution.NationalExecution()
            published,events,lookups,_=runner.run_intake(runner.envelope(text),flow_output=wire,locale=locale)
            self.assertEqual((published,lookups),([],[]))
            self.assertFalse(any(kind=='registered'for kind,_ in events))
            self.assertEqual(''.join(value for kind,value in events if kind=='text_delta'),wire['reply'])
            self.assertEqual(events[-1][0],'completed')

    def test_any_executable_value_or_constraint_keeps_the_original_strict_parser(self):
        original=response();text='规划北京行程'
        for change in (
            dict(duration_days=3),dict(start_date='2026-12-01'),dict(party_size=2),
            dict(fixed_items=[{'item_id':'untrusted'}]),dict(extra_fields={'budget_total':'1000'}),
            dict(extra_unknown_fields=['arrival.time']),dict(unresolved=['unknown']),
            dict(long_term_requests=['save something']),
        ):
            with self.subTest(change=change),self.assertRaises(InvalidInput):parsed(dict(original,**change),text)

    def test_nonfresh_holds_foreign_sources_and_other_questions_do_not_enter_control_channel(self):
        text='规划北京行程';original=response()
        for change in (
            dict(question_fields=['party_size']),dict(question_fields=['duration_days','duration_days']),
            dict(publication_hold=dict(source_index=0,quote='规划')),
            dict(current_source_index=False),dict(planning_request_index=False),dict(planning_request_index=None),
            dict(city=dict(original['city'],source_index=1)),dict(city=dict(original['city'],query='上海')),
        ):
            with self.subTest(change=change),self.assertRaises(InvalidInput):parsed(dict(original,**change),text)
        with self.assertRaises(InvalidInput):parsed(original,text,previous=dict(facts={}))
        for text in ('请把“规划北京行程”翻译成英文','规划北京行程，先聊聊不要保存','Plan a trip to Beijing only if I approve.'):
            wire=response(text,'北京'if '北京'in text else'Beijing')
            with self.subTest(text=text),self.assertRaises(InvalidInput):parsed(wire,text)

    def test_unknown_root_fields_and_duplicate_json_keys_are_not_accepted(self):
        wire=response();text='规划北京行程'
        with self.assertRaises(InvalidInput):parsed(dict(wire,permission=True),text)
        duplicate=json.dumps(wire)[:-1]+',"intent":"plan"}'
        with self.assertRaises(InvalidInput):parse_flow(duplicate,(PlanningTurn(text,date(2026,11,13)),),(),'original',None,schema=OptionalIntake)

    def test_only_literal_city_query_is_retained_not_proposed_geography(self):
        wire=response();wire['city'].update(normalized_name='Guessed name',province='Guessed province')
        _,_,facts=parsed(wire,'规划北京行程')
        self.assertIsNone(facts['city']['value']['province'])
        self.assertIsNone(facts['city']['value']['normalized_name'])

    def test_followup_uses_original_city_and_full_strict_execution_facts(self):
        first='规划北京行程';_,_,facts=parsed(response(),first)
        reply='下周二、四天、一人'
        wire=flow(reply,city=None,days=4,start='2026-11-17',party=1,index=1,questions=())
        wire.update(version='LIO-planning-intake.8',planning_request_index=0)
        result,_,_=parse_flow(json.dumps(wire),(PlanningTurn(first,date(2026,11,13)),PlanningTurn(reply,date(2026,11,13))),
            (dict(message_id='question-original'),),'answer-original',dict(facts=facts),schema=OptionalIntake)
        self.assertNotIsInstance(result,ReadOnlyPlanningQuestion)
        self.assertEqual((result.city['query'],result.duration_days,result.start_date['value']),('北京',4,'2026-11-17'))
        self.assertEqual(result.extraction['fields']['party_size'],dict(state='known',value=1))
        wire['field_sources'].append(dict(field='party_size',source_index=1,quote=''))
        with self.assertRaises(InvalidInput):
            parse_flow(json.dumps(wire),(PlanningTurn(first,date(2026,11,13)),PlanningTurn(reply,date(2026,11,13))),
                (dict(message_id='question-original'),),'answer-original',dict(facts=facts),schema=OptionalIntake)


if __name__=='__main__':unittest.main()
