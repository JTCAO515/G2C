"""Real AUTH/MESSAGE/canonical RUN recover+association with injected DB-API callbacks."""
import asyncio,hashlib,json,os
from datetime import datetime,timezone
from dataclasses import replace
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact
from cj_message.domain import Receipt,Stored
from cj_run.core import Binding,State,Event,advance
from cj_run.postgres import Repository,RecoveryReadUnavailable
from cj_run.usage_binding import UsageBinding
from cj_run.diagnostics import read_diagnostic
from cj_api.original_usage_composition import OriginalUsageWireConfiguration,create_original_usage_app
from cj_api.composition import CompositionUnavailable
from test_composition import SyntheticFixture
from test_message_wire import TransactionDouble

class Database:
    def __init__(self,state):self.state=state;self.epoch='epoch';self.log=[];self.hooks={};self.missing=False
    def call(self,name):
        self.log.append(name)
        if name in self.hooks:self.hooks[name]()
    def connect(self):
        self.call('connect');db=self
        class Conn:
            autocommit=False
            def cursor(self):return Cursor()
            def commit(self):db.call('commit')
            def rollback(self):db.call('rollback')
            def close(self):db.call('connection_close')
        class Cursor:
            query=''
            def execute(self,sql,args=()):self.query=sql;db.log.append(sql)
            def fetchone(self):
                if 'cj_run_scope' in self.query:return(db.epoch,True)
                if db.missing:return None
                s=db.state;b=s.binding;u=s.usage
                return(b.conversation_id,b.generation,b.message_id,b.message_sequence,s.status,s.sequence,True,u.command_bytes if u else None,u.input_bytes if u else None)
            def fetchall(self):return[(e.sequence,e.event_id,e.kind,e.value) for e in db.state.events]
            def close(self):db.call('cursor_close')
        return Conn()

class AssociationChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();self.env=patch.dict(os.environ,{'CJ_ENV':'local'});self.env.start();self.addCleanup(self.env.stop)
        self.repo=TransactionDouble();self.mid='m +/%&e\u0301'
        raw=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='c-original',message_id=self.mid,text='PRIVATE_MESSAGE_SENTINEL',trip_id=None,creation_intent='none'),ensure_ascii=False).encode()
        r=Receipt(self.mid,'c-original','generation-original',1,'run1',hashlib.sha256(raw).hexdigest());self.repo.rows[self.mid]=Stored(raw,r)
        self.binding=Binding(self.repo.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        outbound=b'PRIVATE_OUTBOUND_SENTINEL';command=json.dumps(dict(attempt_id='original-attempt',operation_id='original-operation',run_id='run1',kind='model',input_digest=hashlib.sha256(outbound).hexdigest(),reserve=8,output_limit=9)).encode()
        self.db=Database(State(self.binding,usage=UsageBinding(command,outbound)))
        self.run=Repository(self.db.connect,self.repo.scope,expires_at=datetime(2099,1,1,tzinfo=timezone.utc),statement_timeout_ms=1000,lock_timeout_ms=1000)
        self.args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,resolve_message_repository=lambda p:self.repo,resolve_run=lambda p,s:self.run)
        self.options=OriginalUsageWireConfiguration(1024,8192)
        self.client=TestClient(create_original_usage_app(configuration=self.options,**self.args));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
    def get(self):return self.client.get('/v1/message-usage-association',params={'message_id':self.mid},headers=self.headers)
    def test_actual_original_fields_only_and_no_business_sql(self):
        result=self.get();self.assertEqual(result.status_code,200,result.text);body=result.json();value=body['association']
        self.assertEqual(value,dict(conversation_id='c-original',generation='generation-original',message_id=self.mid,message_sequence=1,run_id='run1',attempt_id='original-attempt',operation_id='original-operation'))
        self.assertEqual(body['request_id'],result.headers['X-Request-ID']);self.assertEqual(result.headers['Cache-Control'],'no-store')
        self.assertNotIn('PRIVATE_',result.text)
        self.assertTrue(all(not sql.startswith(('INSERT','UPDATE','DELETE')) for sql in self.db.log))
        self.assertEqual(self.db.log.count('connection_close'),2)
        self.db.state=advance(self.db.state,Event(self.binding,1,'started','started'),lambda _:True)
        self.db.state=advance(self.db.state,Event(self.binding,2,'unknown','unknown'),lambda _:True)
        again=self.get();self.assertEqual(again.status_code,200);self.assertEqual(again.json()['association'],value)
        self.assertTrue(all(not sql.startswith(('INSERT','UPDATE','DELETE')) for sql in self.db.log))
    def test_missing_legacy_and_strict_close_unavailable(self):
        self.db.state=replace(self.db.state,usage=None);self.assertEqual(self.get().status_code,503)
        self.setUp()
        self.db.hooks['connection_close']=lambda:(_ for _ in ()).throw(OSError('PRIVATE_CLOSE'))
        result=self.get();self.assertEqual(result.status_code,503);self.assertNotIn('association',result.json());self.assertNotIn('PRIVATE_',result.text)
    def test_outer_final_auth_callback_binding_swap_withholds(self):
        original=self.policy.evaluate;after=[0]
        def evaluate(p):
            value=original(p)
            if self.db.log.count('connection_close')==2:
                after[0]+=1
                if after[0]==4:self.run.scope='replacement'
            return value
        with patch.object(self.policy,'evaluate',side_effect=evaluate):result=self.get()
        self.assertEqual(after[0],4);self.assertEqual(result.status_code,503);self.assertNotIn('association',result.json())
    def test_project_epoch_and_unknown_cancel_no_null_fallback(self):
        from cj_api import original_usage_routes
        encoder=original_usage_routes.encode_response
        def change(*args):
            encoded=encoder(*args);self.db.epoch='changed';return encoded
        with patch.object(original_usage_routes,'encode_response',side_effect=change):self.assertEqual(self.get().status_code,503)
        for error in [OSError('fixture ACK unknown'),asyncio.CancelledError()]:
            self.db.hooks['commit']=lambda error=error:(_ for _ in ()).throw(error)
            result=self.get();self.assertEqual(result.status_code,503);self.assertNotIn('association',result.json())
    def test_input_config_and_final_bytes_bound(self):
        self.assertEqual(self.client.get('/v1/message-usage-association?message_id=x&attempt_id=caller',headers=self.headers).status_code,400)
        self.assertEqual(self.client.get('/v1/message-usage-association?message_id=x').status_code,401)
        with TestClient(create_original_usage_app(configuration=OriginalUsageWireConfiguration(1024,1),**self.args)) as c:
            self.assertEqual(c.get('/v1/message-usage-association',params={'message_id':self.mid},headers=self.headers).status_code,413)
        with self.assertRaises(CompositionUnavailable):create_original_usage_app(configuration=self.options,**dict(self.args,resolve_run=None))
    def test_legacy_public_recover_diagnostic_and_display_compatible(self):
        # The default recover still returns after ordinary cleanup errors; only
        # require_clean_close=True opts in to strict withholding.
        self.db.hooks['connection_close']=lambda:(_ for _ in ()).throw(OSError('fixture-close'))
        self.assertEqual(self.run.recover(self.binding).state.binding,self.binding)
        self.assertEqual(read_diagnostic(self.run,self.binding).status,'queued')
        from cj_run.display_snapshot import DisplaySnapshotReader,DisplaySnapshotConfiguration
        from cj_api.original_usage_composition import _attach_original_usage
        from cj_api.composition import build_message_boundary
        message=build_message_boundary(**dict(self.kwargs,resolve_repository=lambda p:self.repo,new_run_id=lambda:'not-called'))
        display=DisplaySnapshotReader(message,lambda p,s:self.run,configuration=DisplaySnapshotConfiguration(1000,8192))
        self.assertEqual(json.loads(display.read(self.token,self.mid))['status'],'queued')
