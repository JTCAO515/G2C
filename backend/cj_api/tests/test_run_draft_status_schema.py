import json
import unittest
from pydantic import ValidationError
from cj_api.generated import RunDraftStatusResponse


class DraftStatusSchemaTests(unittest.TestCase):
    def setUp(self):
        self.value = dict(request_id='00000000-0000-4000-8000-000000000001',version='RUN-draft-status.1',
            conversation_id='chat',generation='gen',message_id='message',run_id='run',
            message_sequence=1,run_status='completed',event_highwater=4,draft_outcome='validation_failed')

    def test_outcomes_do_not_replace_answer_status(self):
        for outcome in ('not_requested','not_recorded','published','validation_failed','provider_failed','provider_unknown'):
            value = dict(self.value,draft_outcome=outcome)
            decoded = RunDraftStatusResponse.model_validate_json(json.dumps(value),strict=True)
            self.assertEqual(decoded.run_status.value,'completed')

    def test_invalid_or_extra_wire_fields_rejected(self):
        for changes in ({'version':'RUN-draft-status.2'},{'draft_outcome':'success'},
                        {'run_status':'draft_failed'},{'message_sequence':0},{'event_highwater':-1},
                        {'scope':'other'},{'event_highwater':True}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                RunDraftStatusResponse.model_validate_json(json.dumps(dict(self.value,**changes)),strict=True)
        for key in self.value:
            value = dict(self.value); del value[key]
            with self.subTest(missing=key), self.assertRaises(ValidationError):
                RunDraftStatusResponse.model_validate_json(json.dumps(value),strict=True)
