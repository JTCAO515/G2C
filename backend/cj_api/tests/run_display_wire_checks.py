"""Actual AUTH/MESSAGE/display reader with scoped transaction/recovery doubles; no DB."""
import asyncio,hashlib,json,os
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact
from cj_message.domain import Receipt,Stored
from cj_run.core import Binding,Cursor,Event,State,advance
from cj_run.postgres import Recovery
from cj_api.run_display_composition import RunDisplayWireConfiguration,create_run_display_app,build_run_display_reader
from cj_api.composition import CompositionUnavailable
from test_composition import SyntheticFixture
from test_message_wire import TransactionDouble

class RecoveryDouble:
    def __init__(self,binding):self.scope=binding.scope;self.binding=binding;self.state=State(binding);self.epoch='epoch';self.failure=None
    def recover(self,binding):
        if self.failure:raise self.failure
        if binding!=self.binding:raise ValueError('wrong binding')
        return Recovery(self.state,Cursor(binding,self.epoch,self.state.sequence,0),'query_only')

class DisplayWireChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();self.env=patch.dict(os.environ,{'CJ_ENV':'local'});self.env.start();self.addCleanup(self.env.stop)
        self.repo=TransactionDouble();self.mid='message +/%&e\u0301'
        raw=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='c-original',message_id=self.mid,
            text='PRIVATE_INPUT_SENTINEL',trip_id=None,creation_intent='none'),ensure_ascii=False).encode()
        receipt=Receipt(self.mid,'c-original','generation-original',1,'run1',hashlib.sha256(raw).hexdigest())
        self.repo.rows[self.mid]=Stored(receipt=receipt,raw=raw)
        self.binding=Binding(self.repo.scope,receipt.conversation_id,receipt.generation,receipt.message_id,receipt.run_id,receipt.sequence)
        self.run=RecoveryDouble(self.binding);self.options=RunDisplayWireConfiguration(1024,4096,8192)
        self.args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,
            resolve_message_repository=lambda p:self.repo,resolve_run=lambda p,s:self.run)
        self.client=TestClient(create_run_display_app(configuration=self.options,**self.args));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
    def state(self,status,text='display e\u0301 中文\n'):
        state=State(self.binding)
        if status!='queued':
            for e in [Event(self.binding,1,'s','started'),Event(self.binding,2,'t','text_delta',text)]:state=advance(state,e,lambda _:True)
            if status!='running':state=advance(state,Event(self.binding,3,'end',status),lambda _:True)
        self.run.state=state
    def get(self,client=None):return (client or self.client).get('/v1/run-display',params={'message_id':self.mid},headers=self.headers)
    def test_actual_reader_all_statuses_partial_text_and_trace(self):
        for status in ['queued','running','completed','failed','cancelled','context_invalid','unknown']:
            self.state(status);result=self.get();self.assertEqual(result.status_code,200,result.text)
            body=result.json();snapshot=body['snapshot']
            self.assertEqual(body['request_id'],result.headers['X-Request-ID']);self.assertEqual(result.headers['Cache-Control'],'no-store')
            self.assertEqual(snapshot['status'],status)
            self.assertEqual(snapshot['text_state'],'complete' if status=='completed' else 'partial')
            self.assertEqual(snapshot['text'],self.run.state.text);self.assertEqual(snapshot['message_id'],self.mid)
            self.assertEqual(len(snapshot),9);self.assertNotIn('PRIVATE_INPUT_SENTINEL',result.text)
    def test_final_envelope_size_not_just_raw_snapshot_and_no_truncation(self):
        self.state('running')
        reader,_=build_run_display_reader(configuration=self.options,**self.args)
        bare=reader.read(self.token,self.mid)
        with TestClient(create_run_display_app(configuration=RunDisplayWireConfiguration(1024,4096,len(bare)),**self.args)) as client:
            result=self.get(client);self.assertEqual(result.status_code,413);self.assertNotIn('snapshot',result.json())
        with TestClient(create_run_display_app(configuration=RunDisplayWireConfiguration(1024,1,8192),**self.args)) as client:
            self.assertEqual(self.get(client).status_code,413)
    def test_projection_change_and_final_auth_withhold_envelope(self):
        from cj_api import run_display_routes
        original=run_display_routes.encode_response;self.state('running')
        def changed(raw,rid):
            encoded=original(raw,rid);self.run.epoch='changed';return encoded
        with patch.object(run_display_routes,'encode_response',side_effect=changed):
            result=self.get();self.assertEqual(result.status_code,503);self.assertNotIn('snapshot',result.json())
        def denied(raw,rid):
            encoded=original(raw,rid);self.policy.invited=Fact.NO;return encoded
        with patch.object(run_display_routes,'encode_response',side_effect=denied):
            result=self.get();self.assertEqual(result.status_code,503);self.assertNotIn('snapshot',result.json())
    def test_missing_run_cancel_unknown_and_input_do_not_fabricate_snapshot(self):
        for error in [ValueError('unavailable'),asyncio.CancelledError()]:
            self.run.failure=error;result=self.get();self.assertEqual(result.status_code,503);self.assertNotIn('snapshot',result.json())
        self.run.failure=None
        self.assertEqual(self.client.get('/v1/run-display?message_id=x&run_id=caller',headers=self.headers).status_code,400)
        self.assertEqual(self.client.get('/v1/run-display?message_id=x&message_id=y',headers=self.headers).status_code,400)
        self.assertEqual(self.client.get('/v1/run-display?message_id=x').status_code,401)
        for key in ['resolve_message_repository','resolve_run','access_provider']:
            with self.assertRaises(CompositionUnavailable):create_run_display_app(configuration=self.options,**dict(self.args,**{key:None}))
        with self.assertRaises(CompositionUnavailable):RunDisplayWireConfiguration(True,1,1)
