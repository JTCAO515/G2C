"""No execution parameters in consultation; city names remain original spans."""
from datetime import date
import json
from types import SimpleNamespace
import unittest
from jsonschema import Draft202012Validator,ValidationError
from cj_agent.lio_intake_modes_schema import response_format
from cj_api.lio_national_intake import parse
from cj_needs.domain import InvalidInput


def dialogue():
    return dict(version='LIO-planning-intake.3',intent='discuss',reply='我们可以先聊聊，不会保存行程。',needs_tools=False,
        city=dict(query='杭州',normalized_name=None,province=None,source_index=0,quote='想去杭州玩两天'),
        current_source_index=0,duration_days=None,extraction=None,field_sources={})


class IntakeModes(unittest.TestCase):
    def turns(self):return (SimpleNamespace(text='想去杭州玩两天，日期和人数还没确定，先聊聊不要保存。',question_day=date(2026,11,11)),)
    def checked(self,value):
        Draft202012Validator(response_format(value['current_source_index'])['json_schema']['schema']).validate(value)
        return parse(json.dumps(value),self.turns(),version='LIO-planning-intake.3')

    def test_original_city_span_allows_context_quote_without_execution_fields(self):
        for intent in ('consult','discuss','cancel'):
            with self.subTest(intent=intent):
                intake=self.checked(dict(dialogue(),intent=intent))
                self.assertIsNone(intake.extraction)
                self.assertEqual(intake.city['query'],'杭州')
                self.assertEqual(intake.current_request,self.turns()[0].text)

    def test_query_cannot_come_from_another_span_turn_or_normalization(self):
        for query,quote,index in [('上海','想去杭州玩两天',0),('杭州市','想去杭州玩两天',0),
                                  ('杭州','想去上海玩两天',0),('杭州','想去杭州玩两天',1),('','想去杭州玩两天',0)]:
            with self.subTest(query=query,quote=quote,index=index):
                value=dialogue();value['city'].update(query=query,quote=quote,source_index=index)
                with self.assertRaises(InvalidInput):parse(json.dumps(value),self.turns(),version='LIO-planning-intake.3')

    def test_nonexecution_rejects_parameters_instead_of_repairing_old_payload(self):
        for change in [dict(extraction=dict(version='NEEDS-extraction.1',fields={},unresolved=[],long_term_requests=[])),
                       dict(duration_days=2),dict(field_sources={'duration_days':[dict(source_index=0,quote='两天')]})]:
            with self.subTest(change=change):
                value=dict(dialogue(),**change)
                with self.assertRaises(ValidationError):Draft202012Validator(response_format(0)['json_schema']['schema']).validate(value)
                with self.assertRaises(InvalidInput):parse(json.dumps(value),self.turns(),version='LIO-planning-intake.3')
        for version in ('LIO-planning-intake.1','LIO-planning-intake.2'):
            with self.subTest(version=version),self.assertRaises(InvalidInput):parse(json.dumps(dialogue()),self.turns(),version=version)

    def test_execution_requires_full_needs_and_cannot_supply_destination_timezone(self):
        value=dict(dialogue(),intent='plan')
        with self.assertRaises(ValidationError):Draft202012Validator(response_format(0)['json_schema']['schema']).validate(value)
        with self.assertRaises(InvalidInput):parse(json.dumps(value),self.turns(),version='LIO-planning-intake.3')
        value['extraction']=dict(version='NEEDS-extraction.1',fields={},unresolved=[],long_term_requests=[])
        self.checked(value)
        value['extraction']['fields']['destination_timezone']=dict(state='known',value='Asia/Shanghai')
        with self.assertRaises(ValidationError):Draft202012Validator(response_format(0)['json_schema']['schema']).validate(value)
        with self.assertRaises(InvalidInput):parse(json.dumps(value),self.turns(),version='LIO-planning-intake.3')

    def test_latest_source_coordinate_and_extra_fields_stay_strict(self):
        for index in (-1,1,True,False,'0',None):
            with self.subTest(index=index),self.assertRaises(InvalidInput):
                parse(json.dumps(dict(dialogue(),current_source_index=index)),self.turns(),version='LIO-planning-intake.3')
        with self.assertRaises(InvalidInput):
            parse(json.dumps(dict(dialogue(),current_request=self.turns()[0].text)),self.turns(),version='LIO-planning-intake.3')
