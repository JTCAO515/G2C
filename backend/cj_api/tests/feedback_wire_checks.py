"""FEEDBACK wire fixtures + actual AUTH rejection/same-checker construction; no DB."""
import hashlib,json,os
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact
from cj_feedback.domain import Receipt,SourceReference,Conflict,ReferenceUnavailable
from cj_feedback.boundary import Boundary,OperationWithheld
from cj_api.feedback_composition import create_feedback_composed_app,FeedbackWireConfiguration,build_feedback_boundary
from cj_api.composition import CompositionUnavailable
from test_composition import SyntheticFixture

class FeedbackWireChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();self.env=patch.dict(os.environ,{'CJ_ENV':'local'});self.env.start();self.addCleanup(self.env.stop)
        self.connected=False
        def connect():self.connected=True;raise AssertionError('No fixture DB')
        self.args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,
            access_provider=self.policy,resolve=lambda p:(connect,'fixture-scope'))
        self.options=FeedbackWireConfiguration(16384,65536)
        self.client=TestClient(create_feedback_composed_app(configuration=self.options,**self.args));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
    def raw(self,refs=None,**values):
        obj={'action_id':'a1','problem':'Synthetic e\u0301 中文 problem','expectation':'','references':refs or []};obj.update(values)
        return json.dumps(obj,ensure_ascii=False,indent=1).encode()
    def post(self,raw):return self.client.post('/v1/feedback',content=raw,headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
    def query(self,aid):return self.client.get('/v1/feedback-action-receipts',params={'action_id':aid},headers=self.headers)
    def fixture(self,ctx):return patch.object(Boundary,'with_operation',side_effect=lambda token,callback:callback(ctx))

    def test_original_receipt_hash_time_source_null_and_no_text_echo(self):
        owner=self;raw=self.raw()
        receipt=Receipt('a1',hashlib.sha256(raw).hexdigest(),'2026-10-22T01:02:03.123456Z')
        class Ctx:
            def submit(self,a):owner.assertEqual(a.original,raw);return receipt
            def query_action(self,aid):return receipt if aid=='a1' else None
        with self.fixture(Ctx()):
            result=self.post(raw);self.assertEqual(result.status_code,200,result.text)
            body=result.json()['receipt'];self.assertEqual(body['input_sha256'],receipt.input_sha256)
            self.assertEqual(body['submitted_at'],receipt.submitted_at);self.assertIsNone(body['source'])
            self.assertEqual(body['message_zh'],'反馈已提交。');self.assertNotIn('problem',body)
            self.assertEqual(self.query('a1').json()['receipt'],body)
            self.assertIsNone(self.query('absent').json()['receipt'])

    def test_minimal_historical_source_whitelist_only(self):
        source=SourceReference('message-é','chat','gen',1,'run','a'*64,'unknown',0)
        class Ctx:
            def submit(self,a):return Receipt(a.action_id,a.digest,'2026-10-22T01:02:03Z',source=source)
        with self.fixture(Ctx()):
            result=self.post(self.raw([{'kind':'message','id':'message-é'}]));self.assertEqual(result.status_code,200)
            value=result.json()['receipt']['source']
            self.assertEqual(set(value),{'message_id','conversation_id','generation','message_sequence','run_id','message_input_sha256','run_status_at_read','event_highwater_at_read'})
            self.assertEqual(value['run_status_at_read'],'unknown')
            for unavailable in ['usage','duration','model_version','rule_version','failure_stage','text','raw','tool_results']:
                self.assertNotIn(unavailable,value)

    def test_input_bytes_authority_unsupported_references_and_limits(self):
        for raw in [self.raw(owner='caller'),self.raw(model_version='caller'),self.raw(problem='中'*2001),self.raw(problem='\x00'),
                    self.raw([{'kind':'run','id':'r'}]),self.raw([{'kind':'trip','id':'t'}]),
                    self.raw([{'kind':'message','id':'m'},{'kind':'message','id':'n'}]),b'\xff',self.raw()+b'NaN',
                    self.raw().replace(b'"a1"',b'"a1", "action_id":"another"')]:
            self.assertEqual(self.post(raw).status_code,400)
        self.assertEqual(self.post(b'x'*16385).status_code,413)
        self.assertEqual(self.client.post('/v1/feedback',content=self.raw(),headers=self.headers).status_code,415)
        self.assertEqual(self.client.get('/v1/feedback-action-receipts?action_id=a1&owner=a',headers=self.headers).status_code,400)
        self.assertFalse(self.connected)

    def test_actual_auth_missing_unknown_denied_and_missing_configuration(self):
        for fact in [Fact.NO,Fact.UNKNOWN]:
            self.policy.invited=fact;result=self.query('a1')
            self.assertEqual(result.status_code,503);self.assertNotIn('receipt',result.json());self.assertFalse(self.connected)
        self.assertEqual(self.client.get('/v1/feedback-action-receipts?action_id=a1').status_code,401)
        for key in ['resolve','access_provider','verification_keys']:
            with self.assertRaises(CompositionUnavailable):create_feedback_composed_app(configuration=self.options,**dict(self.args,**{key:None}))

    def test_sources_missing_or_single_shared_checker_no_fallback(self):
        general,_=build_feedback_boundary(**self.args);self.assertIsNone(general.sources)
        linked,_=build_feedback_boundary(**self.args,resolve_message_repository=lambda p:self.repo,resolve_run=lambda p,s:None)
        self.assertIs(linked.checker,linked.sources.message.checker)
        self.assertIsNone(linked.sources.message.new_run_id)
        with self.assertRaises(CompositionUnavailable):build_feedback_boundary(**self.args,resolve_run=lambda p,s:None)
        from cj_api.composition import build_message_boundary
        from cj_api.feedback_composition import _feedback_with_shared_message
        message=build_message_boundary(**self.kwargs)
        attached,_=_feedback_with_shared_message(message,self.args['resolve'],lambda p,s:None)
        self.assertIs(attached.checker,message.checker);self.assertIs(attached.sources.message,message)

    def test_conflict_source_unknown_and_postcommit_withheld(self):
        for exc,status in [(Conflict(),409),(ReferenceUnavailable(),503),(OperationWithheld(True),503)]:
            with patch.object(Boundary,'with_operation',side_effect=exc):
                result=self.post(self.raw());self.assertEqual(result.status_code,status);self.assertNotIn('receipt',result.json())
                if status==503:self.assertEqual(result.json()['error']['recovery'],'reconcile_original')
