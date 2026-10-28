"""Actual AUTH read context and USAGE read-only storage with DB callback doubles."""
import json,os,threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact,CJAccessFacts
from cj_auth.read_context import ProtectedReadBoundary,ReadContextViolation
from cj_usage.core import Config,Ledger,Run,Attempt,Command,Receipt
from cj_usage.codec import encode
from cj_usage.postgres import PostgresRepository
from cj_api.usage_status_composition import UsageStatusConfiguration,create_usage_status_app,build_usage_status_dependencies
from cj_api.usage_status_projection import encode_response
from cj_api.composition import CompositionUnavailable
from test_composition import SyntheticFixture

class Cursor:
    def __init__(self,owner):self.owner=owner
    def execute(self,sql,args=None):self.owner.sql.append(sql)
    def fetchone(self):
        if self.owner.barrier:self.owner.barrier.wait(timeout=5)
        return (17,1,json.loads(encode(self.owner.ledger)))
    def close(self):pass
class Conn:
    autocommit=False
    def __init__(self,owner):self.owner=owner
    def cursor(self):return Cursor(self.owner)
    def commit(self):
        if self.owner.commit_error:raise OSError('PRIVATE_ACK_SENTINEL')
    def rollback(self):pass
    def close(self):
        if self.owner.close_hook:self.owner.close_hook()
        if self.owner.close_error:raise OSError('PRIVATE_CLOSE_SENTINEL')

class UsageStatusChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();self.env=patch.dict(os.environ,{'CJ_ENV':'local'});self.env.start();self.addCleanup(self.env.stop)
        self.sql=[];self.barrier=None;self.commit_error=False;self.close_error=False;self.close_hook=None
        self.ledger=self.make('unknown')
        self.options=UsageStatusConfiguration(0,1000,800,65536)
        self.resolutions=[]
        def resolve(p,env,start,end):
            self.resolutions.append((p.subject,env,start,end));return PostgresRepository(lambda:Conn(self),'owner-period-scope')
        self.args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,resolve=resolve)
        self.client=TestClient(create_usage_status_app(configuration=self.options,**self.args));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
    def make(self,state,actual=0):
        amount=10**40;cfg=Config('opaque-unit/not-currency',amount*2,0,1000,10,10,amount*2,1000)
        c=Command('attempt','operation','run','model','a'*64,amount,amount)
        receipt=Receipt('attempt','receipt','opaque-unit/not-currency',actual,0) if state=='settled' else None
        cancelled=state=='released'
        return Ledger(cfg,{'attempt':Attempt(c,state,receipt,cancelled,False)},{'run':Run(10,1,0,cancelled)},10)
    def get(self):return self.client.get('/v1/usage-attempt-status',params={'attempt_id':'attempt'},headers=self.headers)
    def test_unknown_zero_and_large_original_counts_exact_null_not_balance(self):
        for state in ['reserved','unknown','released','settled']:
            self.ledger=self.make(state);result=self.get();self.assertEqual(result.status_code,200,result.text)
            value=result.json()['attempt'];self.assertEqual(value['reserved_units'],str(10**40))
            self.assertEqual(value['confirmed_units'],'0' if state=='settled' else None)
            self.assertEqual(value['confirmed_output'],'0' if state=='settled' else None)
            self.assertEqual(value['receipt_id'],'receipt' if state=='settled' else None)
            self.assertEqual(value['unit'],'opaque-unit/not-currency');self.assertNotIn('input_digest',value);self.assertNotIn('budget',value)
            self.assertEqual(result.json()['request_id'],result.headers['X-Request-ID']);self.assertEqual(result.headers['Cache-Control'],'no-store')
        self.ledger=self.make('settled',actual=10**39)
        self.assertEqual(self.get().json()['attempt']['confirmed_units'],str(10**39))
        self.assertTrue(all(sql.startswith('SET TRANSACTION') or sql.startswith('SELECT ') for sql in self.sql))
        self.assertEqual(self.resolutions[0],('synthetic-user','local',0,1000))
    def test_illegal_numeric_projection_never_defaults_or_coerces(self):
        from dataclasses import asdict
        from cj_usage.read_status import status_of
        source=asdict(status_of(self.ledger.attempts['attempt'],self.ledger.config))
        for bad in [True,-1,1.5,'0',None]:
            body=dict(source,reserved_units=bad)
            with self.assertRaises(ValueError):encode_response(json.dumps(body).encode(),'00000000-0000-4000-8000-000000000001','attempt')
    def test_final_close_and_outer_auth_withhold_and_primary_unknown_priority(self):
        self.close_hook=lambda:setattr(self.policy,'invited',Fact.NO)
        result=self.get();self.assertEqual(result.status_code,403);self.assertNotIn('attempt',result.json())
        self.policy.invited=Fact.YES;self.commit_error=True
        result=self.get();self.assertEqual(result.status_code,503);self.assertEqual(result.json()['error']['category'],'dependency')
        self.assertNotIn('PRIVATE_',result.text)
        self.commit_error=False;self.policy.invited=Fact.YES;self.close_hook=None;self.close_error=True
        self.assertEqual(self.get().status_code,503)
    def test_actual_period_mismatch_unknown_denied_and_no_caller_partition(self):
        for fact,status in [(Fact.UNKNOWN,503),(Fact.NO,403)]:
            self.policy.invited=fact;before=len(self.resolutions);r=self.get();self.assertEqual(r.status_code,status);self.assertEqual(len(self.resolutions),before)
        self.policy.invited=Fact.YES
        with TestClient(create_usage_status_app(configuration=UsageStatusConfiguration(1,1001,800,65536),**self.args)) as c:
            self.assertEqual(c.get('/v1/usage-attempt-status?attempt_id=attempt',headers=self.headers).status_code,503)
        for q in ['attempt_id=attempt&period_start=0','attempt_id=attempt&owner=caller','attempt_id=attempt&unit=USD']:
            self.assertEqual(self.client.get('/v1/usage-attempt-status?'+q,headers=self.headers).status_code,400)
        self.assertEqual(self.client.get('/v1/usage-attempt-status?attempt_id=attempt').status_code,401)
        with self.assertRaises(CompositionUnavailable):create_usage_status_app(configuration=self.options,**dict(self.args,resolve=None))
    def test_two_concurrent_http_reads_have_separate_native_lifetimes(self):
        self.barrier=threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.get(),range(2)))
        self.assertEqual([r.status_code for r in results],[200,200]);self.assertNotEqual(results[0].json()['request_id'],results[1].json()['request_id'])
    def test_same_native_boundary_nested_context_stays_sticky(self):
        checker,_,_,modules=build_usage_status_dependencies(configuration=self.options,**self.args)
        boundary=ProtectedReadBoundary(checker,max_response_bytes=4096);inner=[]
        def outer(ctx):
            try:boundary.with_read_context(self.token,lambda nested:(inner.append(True),b'{}')[1])
            except ReadContextViolation:pass
            return b'PRIVATE_MUST_NOT_ESCAPE'
        with self.assertRaises(ReadContextViolation):boundary.with_read_context(self.token,outer)
        self.assertEqual(inner,[])

    def test_outer_auth_final_check_after_storage_and_domain_guards(self):
        original=self.policy.evaluate;target=[None]
        def evaluate(p):
            result=original(p)
            if target[0] is not None and self.policy.calls==target[0]:
                return CJAccessFacts(p,Fact.YES,Fact.YES,Fact.NO)
            return result
        # From close, the next admission check is the outer AUTH final check.
        self.close_hook=lambda:target.__setitem__(0,self.policy.calls+1)
        with patch.object(self.policy,'evaluate',side_effect=evaluate):result=self.get()
        self.assertEqual(result.status_code,403);self.assertEqual(self.policy.calls,target[0]);self.assertNotIn('attempt',result.json())
