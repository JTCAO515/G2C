"""Current-source binding without model-copying or duplicating traveler text."""
from datetime import date
import json
from types import SimpleNamespace
import unittest
from jsonschema import Draft202012Validator,ValidationError

from cj_agent.lio_intake_current_schema import response_format,response_format_sha256
from cj_api.lio_national_intake import parse
from cj_needs.domain import InvalidInput


def envelope():
    return dict(version='LIO-planning-intake.2',intent='plan',reply='请补充日期和人数。',needs_tools=False,
        city=None,duration_days=None,extraction=dict(version='NEEDS-extraction.1',fields={},unresolved=[],long_term_requests=[]),
        field_sources={},current_source_index=1)


class CurrentSourceSchema(unittest.TestCase):
    def turns(self,latest):
        return tuple(SimpleNamespace(text=t,question_day=date(2026,11,11)) for t in ('去桂林玩两天',latest))

    def test_chinese_and_english_continuations_bind_current_original(self):
        for text in ('继续','Please continue.'):
            with self.subTest(text=text):
                value=envelope();schema=response_format(1)['json_schema']['schema']
                Draft202012Validator(schema).validate(value)
                intake=parse(json.dumps(value),self.turns(text),version='LIO-planning-intake.2')
                self.assertEqual(intake.current_request,text)
                # A continuation is not transformed into an earlier plan grant.
                from cj_api.local_lio_national import NationalLioPlanning
                self.assertEqual(NationalLioPlanning._authority(intake,dict(status='discussion',authority='none')),'none')

    def test_wrong_prior_negative_bool_and_out_of_range_indices_rejected(self):
        for index in (0,-1,2,True,False,'1',None):
            with self.subTest(index=index):
                value=dict(envelope(),current_source_index=index)
                with self.assertRaises(ValidationError):Draft202012Validator(response_format(1)['json_schema']['schema']).validate(value)
                with self.assertRaises(InvalidInput):parse(json.dumps(value),self.turns('继续'),version='LIO-planning-intake.2')

    def test_versions_are_explicit_and_old_bad_copy_is_not_repaired(self):
        value=envelope();value.pop('current_source_index');value.update(version='LIO-planning-intake.1',current_request='去桂林玩两天')
        for version in ('LIO-planning-intake.1','LIO-planning-intake.2'):
            with self.subTest(version=version),self.assertRaises(InvalidInput):parse(json.dumps(value),self.turns('继续'),version=version)
        with self.assertRaises(InvalidInput):parse(json.dumps(envelope()),self.turns('继续'))
        with self.assertRaises(InvalidInput):parse(json.dumps(dict(envelope(),current_request='继续')),self.turns('继续'),version='LIO-planning-intake.2')

    def test_schema_instances_and_hashes_bind_only_the_selected_coordinate(self):
        first=response_format(0);second=response_format(1)
        self.assertNotEqual(response_format_sha256(0),response_format_sha256(1))
        first['json_schema']['schema']['$defs']['text']['maxLength']=1
        self.assertEqual(second['json_schema']['schema']['$defs']['text']['maxLength'],4096)
        self.assertEqual(response_format(0)['json_schema']['schema']['$defs']['text']['maxLength'],4096)
        self.assertNotIn('current_request',second['json_schema']['schema']['properties'])

    def test_new_coordinate_never_validates_an_unstated_fact(self):
        value=envelope()
        value['extraction']['fields']={'pace':{'state':'known','value':'relaxed'}}
        value['field_sources']={'pace':[{'source_index':0,'quote':'I prefer relaxed travel'}]}
        Draft202012Validator(response_format(1)['json_schema']['schema']).validate(value)
        with self.assertRaises(InvalidInput):parse(json.dumps(value),self.turns('继续'),version='LIO-planning-intake.2')
