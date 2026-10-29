"""Contract-first v2 checks; no route/consumer activation is claimed here."""
import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, RefResolver

ROOT=Path(__file__).resolve().parents[3]


class DraftStatusV2ContractTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((ROOT/'contracts/api/openapi.json').read_text())
        self.schema=self.spec['components']['schemas']['RunDraftStatusV2Response']
        self.validator=Draft202012Validator(self.schema,resolver=RefResolver.from_schema(self.spec))
        self.value=dict(request_id='00000000-0000-4000-8000-000000000001',version='RUN-draft-status.2',
            conversation_id='chat',generation='g',message_id='m',run_id='r',message_sequence=1,
            run_status='completed',event_highwater=4,draft_outcome='budget_exhausted',budget_exhausted_stage='draft')

    def test_explicit_stage_and_status_are_independent(self):
        self.validator.validate(self.value)
        self.validator.validate(dict(self.value,run_status='failed',draft_outcome='not_recorded',budget_exhausted_stage='answer'))
        self.validator.validate(dict(self.value,run_status='cancelled'))
        self.validator.validate(dict(self.value,draft_outcome='not_recorded',budget_exhausted_stage=None))

    def test_unknown_version_stage_and_extra_fields_fail(self):
        for patch in ({'version':'RUN-draft-status.1'},{'budget_exhausted_stage':'tool'},
                      {'draft_outcome':'success'},{'scope':'owner'},{'event_highwater':-1}):
            with self.subTest(patch=patch):
                self.assertTrue(list(self.validator.iter_errors(dict(self.value,**patch))))
        for field in self.schema['required']:
            value=copy.deepcopy(self.value);del value[field]
            with self.subTest(missing=field):self.assertTrue(list(self.validator.iter_errors(value)))

    def test_v1_shape_and_enum_not_expanded(self):
        v1=self.spec['components']['schemas']['RunDraftStatusResponse']
        self.assertEqual(v1['properties']['version']['enum'],['RUN-draft-status.1'])
        self.assertNotIn('budget_exhausted',v1['properties']['draft_outcome']['enum'])
        self.assertNotIn('budget_exhausted_stage',v1['properties'])
        self.assertEqual(self.spec['paths']['/v1/run-draft-status']['get']['operationId'],'getRunDraftStatus')
        self.assertEqual(self.spec['paths']['/v2/run-draft-status']['get']['operationId'],'getRunDraftStatusV2')
        self.assertNotIn('/v1/run-budget-status',self.spec['paths'])
