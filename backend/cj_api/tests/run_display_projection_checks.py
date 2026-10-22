"""Pure generated-model/BASE codec checks; no auth, repository, DB or network proof."""
import json
import unittest
from cj_api.run_display_projection import encode_response

class ProjectionChecks(unittest.TestCase):
    def payload(self,status='running',text='e\u0301 中文\n'):
        return dict(conversation_id='c',generation='g',message_id='m',run_id='r',message_sequence=1,
                    status=status,event_highwater=2,text=text,text_state='complete' if status=='completed' else 'partial')
    def test_all_statuses_exact_text_and_base_trace(self):
        rid='00000000-0000-4000-8000-000000000001'
        for status in ['queued','running','completed','failed','cancelled','context_invalid','unknown']:
            original=self.payload(status,'' if status=='queued' else 'e\u0301 中文\n')
            encoded=encode_response(json.dumps(original,ensure_ascii=False).encode(),rid)
            self.assertEqual(json.loads(encoded),dict(request_id=rid,snapshot=original))
    def test_private_extra_future_enum_false_completion_and_missing_rejected(self):
        rid='00000000-0000-4000-8000-000000000001'
        cases=[dict(self.payload(),scope='caller'),dict(self.payload(),usage={}),dict(self.payload(),status='future'),
               dict(self.payload('failed'),text_state='complete'),dict(self.payload('completed'),text_state='partial')]
        missing=self.payload();del missing['text'];cases.append(missing)
        for value in cases:
            with self.assertRaises(ValueError):encode_response(json.dumps(value).encode(),rid)
