"""Candidate wire only: canonical guarded lifecycle, strict synthetic AUTH, fresh PG."""
import hashlib,json,os,time
from pathlib import Path
from unittest.mock import patch
import jwt
import psycopg
from fastapi.testclient import TestClient
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import Fact
from cj_auth.jwt_adapter import PyJWTVerifier
from cj_memory.domain import Service
from cj_memory.postgres import Repository
from cj_memory_management.guarded import GuardedService
from cj_api.app import create_app
from cj_api.composition import CompositionUnavailable
from cj_api.memory_boundary import MemoryBinding
from cj_api.memory_management_boundary import (MemoryManagementConfiguration,
    _candidate_boundary_from_checker,create_memory_management_app)
from test_composition import SyntheticFixture

CONFIG=json.loads(Path(os.environ['CJ005_MANAGEMENT_PG_CONFIG']).read_text())
def connect():return psycopg.connect(**CONFIG)

class Conn:
    def __init__(self,owner):self.owner=owner;self.c=connect()
    @property
    def autocommit(self):return self.c.autocommit
    def cursor(self):return self.c.cursor()
    def commit(self):
        self.c.commit()
        if self.owner.unknown:raise OSError('PRIVATE_COMMIT_ACK_UNKNOWN')
    def rollback(self):self.c.rollback()
    def close(self):
        self.c.close()
        if self.owner.revoke_close:self.owner.policy.invited=Fact.NO

class ManagementWireChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();env=patch.dict(os.environ,{'CJ_ENV':'local'});env.start();self.addCleanup(env.stop)
        self.scope='A-'+self._testMethodName;self.other='B-'+self._testMethodName
        self.unknown=False;self.revoke_close=False;self.connections=0
        def factory():self.connections+=1;return Conn(self)
        self.service=GuardedService(Repository(factory,self.scope))
        self.other_service=GuardedService(Repository(factory,self.other))
        def resolve(p):return MemoryBinding(self.scope,self.service) if p.subject=='synthetic-user' else MemoryBinding(self.other,self.other_service)
        checker=AdmissionChecker(PyJWTVerifier(self.config,self.keys),self.policy)
        self.boundary=_candidate_boundary_from_checker(environment='local',checker=checker,resolve_binding=resolve)
        self.options=MemoryManagementConfiguration(32768,65536)
        self.client=TestClient(create_app(_memory_management_boundary=self.boundary,_memory_management_configuration=self.options));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/octet-stream'}
        with connect() as c:c.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s),(%s)',(self.scope,self.other))
        self.item='item +e\u0301/中文';self.seed(self.item)
    def seed(self,item):
        raw=json.dumps(dict(operation_id='seed-'+item,item_id=item,subject='self',slot=item,kind='preference',text='synthetic original / 合成原内容',extent='long_term',context_id=None,source_id='source-'+item,source_version=1,occurred_at='date unknown'),ensure_ascii=False).encode()
        with connect() as c:c.execute('INSERT INTO cj_memory_source VALUES (%s,%s,1,%s,true,true,true,true,clock_timestamp()+interval \'1 hour\')',(self.scope,'source-'+item,raw))
        Service(Repository(connect,self.scope)).save(raw)
    def action(self,aid=' action e\u0301/中文 ',operation='pause',version=1,**extra):
        return json.dumps(dict(action_id=aid,operation=operation,item_id=self.item,expected_version=version,expected_source_version=1,**extra),ensure_ascii=False,indent=2).encode()+b'\n'
    def post(self,raw,client=None):return (client or self.client).post('/v1/memory-management-actions',content=raw,headers=self.headers)
    def query(self,aid,headers=None):return self.client.get('/v1/memory-management-receipts',params={'action_id':aid},headers=headers or self.headers)
    def row(self):
        with connect() as c:return c.execute('SELECT version,status FROM cj_memory_item WHERE scope=%s AND item_id=%s',(self.scope,self.item)).fetchone()
    def stored(self,aid):
        with connect() as c:return c.execute('SELECT original_input,version,status FROM cj_memory_management_action WHERE scope=%s AND action_id=%s',(self.scope,aid)).fetchone()
    def test_exact_pause_resume_replay_query_and_same_transaction(self):
        raw=self.action();aid=json.loads(raw)['action_id'];before=self.connections;captured=[];original=self.boundary.invoke
        def invoke(token,kind,arg,project):
            def encoded(value):
                body=project(value);captured.append(body);return body
            return original(token,kind,arg,encoded)
        with patch.object(self.boundary,'invoke',side_effect=invoke):r=self.post(raw)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.connections,before+1);self.assertEqual(r.content,captured[-1])
        receipt=r.json()['receipt'];self.assertEqual(receipt['action_id'],aid);self.assertEqual(receipt['status'],'disabled');self.assertEqual(receipt['version'],2)
        self.assertEqual(receipt['input_sha256'],hashlib.sha256(bytes(self.stored(aid)[0])).hexdigest());self.assertEqual(bytes(self.stored(aid)[0]),raw)
        self.assertEqual(r.json()['request_id'],r.headers['X-Request-ID']);self.assertEqual(r.headers['Cache-Control'],'no-store')
        resume=self.action('resume-original','resume',2);resumed=self.post(resume);self.assertEqual(resumed.status_code,200,resumed.text)
        self.assertEqual(resumed.json()['receipt']['status'],'active');self.assertEqual(self.row(),(3,'active'))
        self.assertEqual(self.query(aid).json()['receipt'],receipt);self.assertEqual(self.post(raw).json()['receipt'],receipt);self.assertEqual(self.row(),(3,'active'))
        self.assertEqual(self.post(raw+b' ').status_code,409)
    def test_required_null_scoped_query_and_public_factory_closed(self):
        raw=self.action();self.assertEqual(self.post(raw).status_code,200);aid=json.loads(raw)['action_id']
        now=int(time.time());other=jwt.encode(dict(iss=self.config.issuer,aud=self.config.audience,sub='other',iat=now-1,nbf=now-1,exp=now+120),self.key,algorithm='RS256',headers={'kid':'test-key'})
        r=self.query(aid,{'Authorization':'Bearer '+other});self.assertEqual(r.status_code,200,r.text);self.assertIsNone(r.json()['receipt'])
        self.assertIsNone(self.query('absent-original').json()['receipt'])
        with self.assertRaises(CompositionUnavailable):create_memory_management_app(configuration=self.options,environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,resolve_binding=lambda p:None)
        with TestClient(create_app()) as c:self.assertEqual(c.post('/v1/memory-management-actions',content=raw,headers=self.headers).status_code,503)
    def test_commit_unknown_and_close_revoke_query_only_original(self):
        raw=self.action();aid=json.loads(raw)['action_id'];self.unknown=True
        r=self.post(raw);self.assertEqual(r.status_code,503,r.text);self.assertEqual(r.json()['error']['recovery'],'reconcile_original');self.assertNotIn('receipt',r.json());self.assertNotIn('PRIVATE_',r.text)
        self.assertEqual(self.row(),(2,'disabled'));self.unknown=False
        found=self.query(aid);self.assertEqual(found.status_code,200,found.text);self.assertEqual(found.json()['receipt']['input_sha256'],hashlib.sha256(raw).hexdigest())
        self.revoke_close=True;r=self.post(self.action('resume-close','resume',2));self.assertEqual(r.status_code,503);self.assertNotIn('receipt',r.json());self.assertEqual(self.row(),(3,'active'))
        self.revoke_close=False;self.policy.invited=Fact.YES;self.assertEqual(self.query('resume-close').json()['receipt']['status'],'active')
    def test_precommit_rollback_then_bounded_projection_original_reconcile(self):
        raw=self.action();aid=json.loads(raw)['action_id'];policy=self.boundary.source_policy
        def revoke(*args):
            if args[-1]=='precommit':self.policy.invited=Fact.NO
            return True
        self.boundary.source_policy=revoke
        r=self.post(raw);self.assertEqual(r.status_code,503,r.text);self.assertEqual(r.json()['error']['recovery'],'reconcile_original');self.assertEqual(self.row(),(1,'active'));self.assertIsNone(self.stored(aid))
        self.boundary.source_policy=policy;self.policy.invited=Fact.YES
        with TestClient(create_app(_memory_management_boundary=self.boundary,_memory_management_configuration=MemoryManagementConfiguration(32768,1))) as c:r=self.post(raw,c)
        self.assertEqual(r.status_code,503,r.text);self.assertEqual(r.json()['error']['recovery'],'reconcile_original');self.assertEqual(self.row(),(2,'disabled'))
        self.assertEqual(self.query(aid).json()['receipt']['version'],2)
    def test_final_binding_change_withholds_committed_receipt(self):
        def change(*args):
            if args[-1]=='return':self.service.repository.scope=self.other
            return True
        self.boundary.source_policy=change;raw=self.action();aid=json.loads(raw)['action_id']
        r=self.post(raw);self.assertEqual(r.status_code,503,r.text);self.assertNotIn('receipt',r.json());self.assertEqual(self.row(),(2,'disabled'))
        self.service.repository.scope=self.scope;self.boundary.source_policy=lambda *_:True
        self.assertEqual(self.query(aid).json()['receipt']['version'],2)
    def test_input_no_edit_new_approval_or_caller_scope_and_access_fail_closed(self):
        before=self.connections
        raws=[self.action(text='new edit'),self.action(owner='caller'),self.action(authorized=True),self.action(operation='edit'),self.action(version=True),self.action(version=2**63),self.action().replace(b'"action_id":',b'"action_id":"duplicate","action_id":',1)]
        for raw in raws:self.assertEqual(self.post(raw).status_code,400)
        self.assertEqual(self.connections,before)
        for fact,status in [(Fact.NO,403),(Fact.UNKNOWN,503)]:
            self.policy.invited=fact;self.assertEqual(self.post(self.action()).status_code,status);self.assertEqual(self.connections,before)
        self.policy.invited=Fact.YES
        self.assertEqual(self.client.get('/v1/memory-management-receipts?action_id=x&owner=caller',headers=self.headers).status_code,400)
        self.assertEqual(self.client.post('/v1/memory-management-actions',content=self.action(),headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'}).status_code,415)
