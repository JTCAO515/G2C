"""Canonical AUTH/cleanup journal and DB-API doubles; no database or hooks."""
import json, os, threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact
from cj_auth.jwt_adapter import PyJWTVerifier
from cj_cleanup import core
from cj_cleanup.postgres import Repository, state_bytes
from cj_api.cleanup_progress_composition import CleanupProgressConfiguration, create_cleanup_progress_app
from cj_api.composition import CompositionUnavailable
from test_composition import SyntheticFixture

class Cursor:
    def __init__(self, owner): self.owner=owner; self.args=None
    def execute(self, sql, args=None): self.owner.sql.append(sql); self.args=args
    def fetchone(self):
        if self.owner.barrier: self.owner.barrier.wait(timeout=5)
        op=self.owner.op
        if self.args != (core.encode(asdict(op.scope)),): return None
        return op.operation_id,op.revision,self.owner.memory.journal(),state_bytes(op)
class Conn:
    autocommit=False
    closed=False
    info=SimpleNamespace(transaction_status=0)
    def __init__(self,owner): self.owner=owner
    def cursor(self): return Cursor(self.owner)
    def commit(self):
        if self.owner.commit_error: raise OSError('PRIVATE_COMMIT')
    def rollback(self): pass
    def close(self):
        if self.owner.close_hook: self.owner.close_hook()
        if self.owner.close_error: raise OSError('PRIVATE_CLOSE')

class CleanupProgressChecks(SyntheticFixture):
    def setUp(self):
        super().setUp(); env=patch.dict(os.environ,{'CJ_ENV':'local'});env.start();self.addCleanup(env.stop)
        self.sql=[];self.resolved=[];self.barrier=None;self.close_hook=None;self.close_error=False;self.commit_error=False
        self.scope=core.Scope.from_principal('local',PyJWTVerifier(self.config,self.keys).verify(self.token).principal)
        self.make()
        self.options=CleanupProgressConfiguration(128,65536)
        def resolve(principal, environment, guard):
            self.resolved.append((principal.subject,environment))
            repo=Repository(lambda:Conn(self),core.Scope.from_principal(environment,principal),guard)
            self.last_repo=repo
            return repo
        self.args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,resolve=resolve)
        self.client=TestClient(create_cleanup_progress_app(configuration=self.options,**self.args));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
    def make(self, state='pending', available=True, gaps=()):
        manifest=core.Manifest('fixture-v1',core.digest(b'fixture registry'),(core.Entry('metadata',core.digest(b'store'),available),),gaps)
        self.memory=core.Repository()
        caps=tuple(core.BARRIERS)+('store:metadata',) if available else ()
        self.op=self.memory.create(core.request(self.scope,'original/operation',core.digest(b'PRIVATE_CONFIRMATION'),manifest,caps))
        if state!='pending':
            self.op=self.memory.intent(self.scope,self.op.operation_id,self.op.revision,'auth_revocation','PRIVATE_CALL')
            if state!='in_progress':
                s=self.op.steps[0]
                raw=core.encode(dict(protocol=core.VERSION,scope_digest=core.digest(core.encode(asdict(self.scope))),operation_id=self.op.operation_id,target=s.target,version=s.version,invocation=s.invocation,outcome=state))
                self.op=self.memory.receipt(self.scope,self.op.operation_id,self.op.revision,s.target,raw)
    def get(self,client=None,**query):
        return (client or self.client).get('/v1/account-cleanup-progress',params=query or {'operation_id':self.op.operation_id},headers=self.headers)
    def test_whitelist_original_revision_states_and_select_only(self):
        for state,expected in [('pending','awaiting_revocation'),('in_progress','awaiting_revocation'),('unknown','unknown'),('failed','failed'),('confirmed','in_progress')]:
            self.make(state);before=self.memory.journal();result=self.get();self.assertEqual(result.status_code,200,result.text)
            data=result.json();value=data['progress'];self.assertEqual(set(data),{'request_id','progress'})
            self.assertEqual(set(value),{'operation_id','revision','status','steps','reasons'})
            self.assertEqual(value['status'],expected);self.assertEqual(value['revision'],self.op.revision)
            self.assertEqual(value['steps'][0]['state'],state)
            self.assertTrue(all(set(s)=={'target','state','reason'} for s in value['steps']))
            self.assertEqual(before,self.memory.journal());self.assertNotIn('PRIVATE_',result.text)
            self.assertNotIn('synthetic-user',result.text);self.assertEqual(data['request_id'],result.headers['X-Request-ID'])
            self.assertEqual(result.headers['Cache-Control'],'no-store')
        self.assertTrue(all(sql.startswith(('SELECT ','SET ')) and 'FOR UPDATE' not in sql for sql in self.sql))
        self.assertEqual(self.resolved[0],('synthetic-user','local'))
    def test_unavailable_hooks_gaps_and_bounded_whole_envelope(self):
        self.make(available=False,gaps=('PRIVATE_OFFLINE_BACKUP_GAP',));r=self.get();self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['progress']['status'],'blocked');self.assertIn('hook_unavailable',r.json()['progress']['reasons']);self.assertNotIn('PRIVATE_',r.text)
        for options in [CleanupProgressConfiguration(1,65536),CleanupProgressConfiguration(128,1)]:
            with TestClient(create_cleanup_progress_app(configuration=options,**self.args)) as client:
                self.assertEqual(self.get(client).status_code,503)
        for n in [0,129,True]:
            with self.assertRaises(CompositionUnavailable):CleanupProgressConfiguration(n,65536)
    def test_current_account_only_and_original_operation_only(self):
        for fact,status in [(Fact.NO,403),(Fact.UNKNOWN,503)]:
            self.policy.invited=fact;before=len(self.resolved);r=self.get();self.assertEqual(r.status_code,status);self.assertNotIn('progress',r.json());self.assertEqual(len(self.resolved),before)
        self.policy.invited=Fact.YES
        self.assertEqual(self.get(operation_id='not-original').status_code,503)
        self.op=replace(self.op,scope=replace(self.scope,subject='other'))
        self.assertEqual(self.get().status_code,503)
        self.assertEqual(self.client.get('/v1/account-cleanup-progress?operation_id=x').status_code,401)
        for extra in ['owner','environment','capabilities','scope','recover']:
            self.assertEqual(self.get(operation_id='x',**{extra:'caller'}).status_code,400)
        self.assertEqual(self.client.post('/v1/account-cleanup-progress',headers=self.headers).status_code,405)
    def test_close_failure_and_revocation_withhold_all_progress(self):
        for attr in ['close_error','commit_error']:
            setattr(self,attr,True);r=self.get();self.assertEqual(r.status_code,503);self.assertNotIn('progress',r.json());self.assertNotIn('PRIVATE_',r.text);setattr(self,attr,False)
        self.close_hook=lambda:setattr(self.policy,'invited',Fact.NO)
        r=self.get();self.assertNotEqual(r.status_code,200);self.assertNotIn('progress',r.json())
    def test_resolver_wrong_scope_rejected(self):
        def resolve(principal,environment,guard):
            return Repository(lambda:Conn(self),replace(self.scope,subject='other'),guard)
        with TestClient(create_cleanup_progress_app(configuration=self.options,**dict(self.args,resolve=resolve))) as c:
            self.assertEqual(self.get(c).status_code,503)
    def test_concurrent_http_gets_have_independent_native_read_contexts(self):
        self.barrier=threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.get(),range(2)))
        self.assertEqual([r.status_code for r in results],[200,200]);self.assertNotEqual(results[0].json()['request_id'],results[1].json()['request_id'])

    def test_complete_is_only_original_frozen_operation(self):
        for target in [s.target for s in self.op.steps]:
            self.op=self.memory.intent(self.scope,self.op.operation_id,self.op.revision,target,'call-'+str(self.op.revision))
            step=next(s for s in self.op.steps if s.target==target)
            receipt=core.encode(dict(protocol=core.VERSION,scope_digest=core.digest(core.encode(asdict(self.scope))),operation_id=self.op.operation_id,target=target,version=step.version,invocation=step.invocation,outcome='confirmed'))
            self.op=self.memory.receipt(self.scope,self.op.operation_id,self.op.revision,target,receipt)
        result=self.get();self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['progress']['status'],'complete')
        self.assertEqual(result.json()['progress']['reasons'],[])

    def test_composed_read_uses_message_checker(self):
        from cj_api.composition import create_composed_app
        from cj_api import cleanup_progress_composition as comp
        from cj_auth.read_context import ProtectedReadBoundary
        original=comp._cleanup_progress_from_checker;seen=[];boundary_init=ProtectedReadBoundary.__init__
        def attach(checker,*args,**kwargs):
            seen.append(checker);return original(checker,*args,**kwargs)
        def initialize(boundary,checker,*args,**kwargs):
            self.assertIs(checker,seen[0]);return boundary_init(boundary,checker,*args,**kwargs)
        with patch.object(comp,'_cleanup_progress_from_checker',side_effect=attach):
            app=create_composed_app(**self.kwargs,max_body_bytes=1024,cleanup_progress_configuration=self.options,resolve_cleanup_progress=self.args['resolve'])
        with patch.object(ProtectedReadBoundary,'__init__',new=initialize),TestClient(app) as c:
            self.assertEqual(self.get(c).status_code,200)
