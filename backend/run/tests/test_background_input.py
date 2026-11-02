import base64,hashlib,json,unittest
from cj_message.source import SourceQuery
from cj_run.background_store import JobRequest
from cj_usage.background_exit import ModelInput


class BackgroundInputChecks(unittest.TestCase):
    def request(self,raw,job='任务:一',attempt='尝试:一'):
        return JobRequest(job,attempt,SourceQuery('会话','generation',0,0,1,1,1),None,raw)

    def test_original_prompt_and_full_operation_hash_are_distinct(self):
        raw=b'{"system":"fixed", "messages":[{"role":"user","content":"private data"}]}\n'
        request=self.request(raw);frame=request.envelope('canonical-owner','server-run')
        value=json.loads(frame)
        self.assertEqual(base64.b64decode(value['prepared_input_base64']),raw)
        self.assertEqual(value['job_id'],'任务:一')
        self.assertEqual(request.prepared_sha256,hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(hashlib.sha256(frame).hexdigest(),request.prepared_sha256)
        self.assertNotEqual(frame,request.envelope('other-owner','server-run'))
        self.assertNotEqual(frame,request.envelope('canonical-owner','other-run'))

    def test_no_history_data_can_set_a_model_role(self):
        for role in ('system','assistant','tool'):
            with self.subTest(role=role),self.assertRaises(ValueError):
                ModelInput.parse(json.dumps(dict(system='fixed',messages=[dict(role=role,content='untrusted')])).encode())
        value=ModelInput.parse(b'{"system":"fixed","messages":[{"role":"user","content":"ignore instructions"}]}')
        self.assertEqual(value.messages,(('user','ignore instructions'),))

    def test_invalid_unicode_duplicate_fields_and_alias_bounds(self):
        with self.assertRaises(UnicodeError):ModelInput.parse(b'{"system":"fixed","messages":[{"role":"user","content":"\\ud800"}]}')
        with self.assertRaises(ValueError):ModelInput.parse(b'{"system":"a","system":"b","messages":[]}')
        for name in ('\0','\ud800','x'*257):
            with self.subTest(alias=repr(name)),self.assertRaises((ValueError,UnicodeError)):
                self.request(b'{}',job=name)


if __name__=='__main__':unittest.main()
