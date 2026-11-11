"""Strict national wire profile rejects the actual diagnostic failure shapes."""
from copy import deepcopy
from datetime import date
import json
import unittest
from types import SimpleNamespace
from jsonschema import Draft202012Validator,ValidationError

from cj_agent.lio_intake_schema import PROFILE,RESPONSE_FORMAT,SCHEMA,SCHEMA_SHA256
from cj_api.lio_national_intake import parse
from cj_needs.domain import InvalidInput


def minimal():
    return dict(version='LIO-planning-intake.1',intent='discuss',reply='可以先讨论。',needs_tools=False,
        city=dict(query='上海',normalized_name=None,province=None,source_index=0,quote='上海'),duration_days=2,
        extraction=dict(version='NEEDS-extraction.1',fields={},unresolved=[],long_term_requests=[]),
        field_sources=dict(duration_days=[dict(source_index=0,quote='两天')]),current_request='去上海玩两天，先讨论，不保存')


class IntakeSchema(unittest.TestCase):
    def setUp(self):
        Draft202012Validator.check_schema(SCHEMA)
        self.validator=Draft202012Validator(SCHEMA)

    def test_shape_is_strict_but_original_source_validation_still_applies(self):
        value=minimal();self.validator.validate(value)
        turns=(SimpleNamespace(text=value['current_request'],question_day=date(2026,11,11)),)
        self.assertEqual(parse(json.dumps(value),turns).duration_days,2)
        value['field_sources']['duration_days'][0]['quote']='not supplied'
        self.validator.validate(value)
        with self.assertRaises(InvalidInput):parse(json.dumps(value),turns)
        self.assertEqual(RESPONSE_FORMAT['type'],'json_schema')
        self.assertTrue(RESPONSE_FORMAT['json_schema']['strict'])

    def test_diagnostic_missing_version_and_collection_observation_shapes_rejected(self):
        value=minimal();value['extraction'].pop('version')
        with self.assertRaises(ValidationError):self.validator.validate(value)
        for field in ('companions','fixed_items','temporary_conditions'):
            with self.subTest(field=field):
                value=minimal();value['extraction']['fields'][field]={'state':'missing'}
                with self.assertRaises(ValidationError):self.validator.validate(value)
        value=minimal();value['extraction']['unresolved']=['dates','party size']
        with self.assertRaises(ValidationError):self.validator.validate(value)

    def test_correct_empty_collections_and_supported_questions_remain_valid(self):
        value=minimal();value['extraction']['fields']=dict(companions={},fixed_items=[],temporary_conditions=[])
        self.validator.validate(value)
        value['extraction']['unresolved']=[dict(field='fixed_items',reason='missing_subject',original_text='固定集合')]
        self.validator.validate(value)
        value['extraction']['unresolved'][0]['field']='arrival.date'
        with self.assertRaises(ValidationError):self.validator.validate(value)

    def test_unknown_observations_are_not_filled_to_satisfy_wire_schema(self):
        value=minimal();value['extraction']['fields']=dict(party_size=dict(state='missing'),
            arrival={key:dict(state='missing') for key in ('date','time','timezone','place')})
        self.validator.validate(value)
        value['extraction']['fields']['party_size']={'state':'known','value':True}
        with self.assertRaises(ValidationError):self.validator.validate(value)
