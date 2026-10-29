"""Formal local factory + operator/worker CLI on private PG; FakeProvider only."""
import json
import os
import subprocess
import sys
import time
from unittest.mock import patch
from fastapi.testclient import TestClient
import psycopg
from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
from cj_api.composition import CompositionUnavailable
from cj_api.local_run_context import load_run_context, LocalContextUnavailable
from cj_message.needs_binding import needs_scope_for
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode
from cj_usage.core import Meter
from cj_agent.provider import FakeProvider
from cj_usage.postgres import CommitUnknown
from cj_usage.local_provider_exit import BudgetUnknown
import local_history_pg as harness
sys.path.insert(0,str(harness.ROOT/'scripts'))

ROOT = harness.ROOT


def exercise(auth, conninfo):
    import run_worker
    subjects=['alice','bob','draft','success','missing','stale','midflight','claim-unknown','period']
    harness.dev_auth.init(auth,subjects)
    headers={s:{'Authorization':'Bearer '+harness.dev_auth.token(auth,s,30)} for s in subjects}
    now=int(time.time())
    def document(budget):
        return {'version':'CJ-LOCAL-RUN@1','current':{'meter':dict(unit='provider_call',budget=budget,
            period_start=now-60,period_end=now+3600,max_steps=4,max_tools=1,max_output=10000,max_seconds=600),
            'output_limits':{'answer':1000,'draft':1000}},'history':[]}
    profile=auth.parent/'context.json'; profile.write_text(json.dumps(document(1)))
    bigger=auth.parent/'bigger.json'; bigger.write_text(json.dumps(document(3)))
    config=json.loads(conninfo.read_text())
    env=dict(os.environ,CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(profile))
    def cli(script,*args,context=profile,ok=True):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),'--conninfo-json',str(conninfo),
            '--auth-dir',str(auth),'--run-context',str(context),*args],env=env,capture_output=True,text=True,timeout=30)
        assert (result.returncode==0)==ok,(script,result.returncode,result.stdout,result.stderr)
        return result
    def operator(subject,*args,context=profile,ok=True):
        return cli('local_run_context.py','--subject',subject,*args,context=context,ok=ok)
    for subject in subjects:
        if subject!='missing': operator(subject,'init-budget',context=bigger if subject in ('success','stale','midflight') else profile)
    assert json.loads(operator('alice','init-budget').stdout)['status']=='existing'
    operator('alice','init-budget',context=bigger,ok=False)
    cli('run_worker.py','--once','--real',ok=False)
    def needs(subject,version=0):
        path=auth.parent/'needs-input.json'
        path.write_text(json.dumps(dict(action_id=f'edit-{version}',needs_id='needs',expected_version=version,
            source={'kind':'manual','text':'explicit local operator input'},changes={'party_size':{'state':'known','value':version+1}})))
        return operator(subject,'put-needs','--input-json',str(path),context=bigger if subject in ('success','stale','midflight') else profile)
    def ledger(subject,context=profile):
        meter=load_run_context(context).current.meter
        account=ledger_scope_for(scope_for(ISSUER,subject),meter)
        with psycopg.connect(**config) as conn:
            return decode(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
    def api(context=profile):
        with patch.dict(os.environ,{**env,'CJ_LOCAL_RUN_CONTEXT':str(context)}): return TestClient(app_from_environment())
    def send(client,subject,mid,intent='none',select=True):
        cid='chat-'+mid
        chat=harness.expect(client.put('/v1/conversations',params={'conversation_id':cid},headers=headers[subject]))
        if intent=='consider_trip' and select:
            needs(subject)
            operator(subject,'bind-needs','--conversation-id',cid,'--needs-id','needs',context=bigger if subject in ('success','stale','midflight') else profile)
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,text='Beijing',trip_id=None,
            creation_intent=intent,expected_generation=chat['generation'],expected_sequence=0)).encode()
        response=client.post('/v1/messages',content=raw,headers={**headers[subject],'Content-Type':'application/octet-stream'})
        return response,raw
    def status(client,subject,mid,code=200,version=2):
        return harness.expect(client.get(f'/v{version}/run-draft-status',params={'message_id':mid},headers=headers[subject]),code)
    with api() as client:
        harness.expect(client.put('/v1/conversations',params={'conversation_id':'missing'},headers=headers['missing']),503)
        harness.expect(send(client,'alice','first')[0])
    result=cli('run_worker.py','--once'); assert 'local_provider_calls=1' in result.stdout,result.stdout
    with api() as client:
        assert status(client,'alice','first')['run_status']=='completed'
        harness.expect(send(client,'alice','second')[0])
        harness.expect(send(client,'draft','draft','consider_trip')[0])
    result=cli('run_worker.py','--once'); assert 'local_provider_calls=1' in result.stdout,result.stdout
    with api() as client:
        answer=status(client,'alice','second'); draft=status(client,'draft','draft')
        assert answer['run_status']=='failed' and answer['budget_exhausted_stage']=='answer',answer
        assert draft['run_status']=='completed' and draft['draft_outcome']=='budget_exhausted' and draft['budget_exhausted_stage']=='draft',draft
        status(client,'draft','draft',503,version=1)
        status(client,'bob','second',503)
        denied,raw=send(client,'bob','unbound','consider_trip',select=False)
        assert denied.status_code==503,denied.text
    assert Meter.exposure(ledger('alice'))==Meter.exposure(ledger('draft'))==1
    result=cli('run_worker.py','--once'); assert 'local_provider_calls=0' in result.stdout,result.stdout
    print('PASS formal API/CLI answer and draft quota refusal, original replay, cross-account and missing binding/account')
    with api(bigger) as client:
        harness.expect(send(client,'success','success','consider_trip')[0])
        harness.expect(send(client,'stale','stale','consider_trip')[0])
    needs('stale',1)
    result=cli('run_worker.py','--once',context=bigger)
    assert 'local_provider_calls=2' in result.stdout,result.stdout
    with api(bigger) as client:
        success=status(client,'success','success'); stale=status(client,'stale','stale')
        assert success['run_status']=='completed' and success['draft_outcome']=='published',success
        assert stale['run_status']=='context_invalid',stale
    assert Meter.exposure(ledger('success',bigger))==2
    assert Meter.exposure(ledger('stale',bigger))==0
    print('PASS operator NEEDS input/selection, atomic binding, successful two-step draft and pre-dispatch revision fence')
    # Actual host function with local FakeProvider fault timing; no test repository/scopes.
    with api(bigger) as client:
        harness.expect(send(client,'midflight','midflight','consider_trip')[0])
    class ReviseDuringDraft(FakeProvider):
        def stream(self,messages,system=None):
            if system is not None: needs('midflight',1)
            yield from super().stream(messages,system=system)
    model=ReviseDuringDraft()
    results=run_worker.run_once(LocalDatabase(conninfo,run_context=load_run_context(bigger)),model,auth)
    assert len(results)==1 and results[0].status=='context_invalid' and model.calls==2,results
    with api(bigger) as client:
        assert status(client,'midflight','midflight')['run_status']=='context_invalid'
    with psycopg.connect(**config) as conn:
        assert conn.execute("SELECT count(*) FROM cj_run_event WHERE run_id=%s AND kind='effect_committed'",(results[0].run_id,)).fetchone()[0]==0
    # Inject only lost ACK after the real claim commits, then restart actual CLI.
    with api() as client: harness.expect(send(client,'claim-unknown','claim-unknown')[0])
    claim=Meter.claim
    def lost_ack(meter,*args):
        claim(meter,*args)
        raise CommitUnknown('injected durable claim ACK loss')
    model=FakeProvider()
    with patch.object(Meter,'claim',lost_ack):
        result=run_worker.run_once(LocalDatabase(conninfo,run_context=load_run_context(profile)),model,auth)
    assert result[0].status=='unknown' and model.calls==0
    original=ledger('claim-unknown')
    assert Meter.exposure(original)==1
    restart=cli('run_worker.py','--once')
    assert 'local_provider_calls=0' in restart.stdout
    assert ledger('claim-unknown')==original
    print('PASS formal host mid-draft revision blocks publication; durable claim ACK loss stays unknown, CLI restart has zero calls')
    # Abrupt worker interruption after durable claim leaves the original pending.
    with api() as client: harness.expect(send(client,'period','period')[0])
    class Interrupted(BaseException): pass
    def interrupted_claim(meter,*args):
        claim(meter,*args)
        raise Interrupted()
    model=FakeProvider()
    try:
        with patch.object(Meter,'claim',interrupted_claim):
            run_worker.run_once(LocalDatabase(conninfo,run_context=load_run_context(profile)),model,auth)
    except Interrupted: pass
    else: raise AssertionError('interruption not exercised')
    assert model.calls==0
    prior=ledger('period')
    future=document(1)
    future['current']['meter'].update(period_start=now+3600,period_end=now+7200)
    missing_history=auth.parent/'missing-history.json';missing_history.write_text(json.dumps(future))
    missing_context=load_run_context(missing_history,clock=lambda:now+3601)
    try: run_worker.run_once(LocalDatabase(conninfo,run_context=missing_context),FakeProvider(),auth)
    except BudgetUnknown: pass
    else: raise AssertionError('missing original period substituted current quota')
    assert ledger('period')==prior
    future['history']=[document(1)['current']]
    future_path=auth.parent/'future.json';future_path.write_text(json.dumps(future))
    # Advance only config admission clock; recovery must never call a provider or reserve.
    retained=load_run_context(future_path,clock=lambda:now+3601)
    model=FakeProvider()
    recovered=run_worker.run_once(LocalDatabase(conninfo,run_context=retained),model,auth)
    assert recovered[0].status=='unknown' and model.calls==0
    after=ledger('period')
    assert set(after.attempts)==set(prior.attempts) and Meter.exposure(after)==1
    new_account=ledger_scope_for(scope_for(ISSUER,'period'),retained.current.meter)
    with psycopg.connect(**config) as conn:
        assert conn.execute('SELECT 1 FROM cj_usage_ledger_candidate WHERE scope_id=%s',(new_account,)).fetchone() is None
    print('PASS interrupted original run recovered with retained period; no current-period account or redispatch (config clock advanced)')
    # Inspect real formal connection scope lifetime; same physical connection survives rollback/commit.
    db=LocalDatabase(conninfo,run_context=load_run_context(profile)); scope=scope_for(ISSUER,'alice')
    names=('message','trip','needs','usage')
    for finish in ('commit','rollback'):
        conn=db.connect(scope)
        with conn.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED');conn.bind_scope(cursor)
            cursor.execute("SELECT current_setting('cj.needs_scope'),current_setting('cj.usage_scope'),current_user")
            assert cursor.fetchone()==(needs_scope_for(scope),ledger_scope_for(scope,db.run_context.current.meter),'cj_m1_runtime')
        getattr(conn,finish)()
        for name in names: assert conn.execute("SELECT current_setting(%s,true)",('cj.'+name+'_scope',)).fetchone()[0] in (None,'')
        conn.rollback();conn.close()
    for name in ('needs','usage'):
        dirty=psycopg.connect(**db.conninfo,autocommit=True)
        dirty.execute('SELECT set_config(%s,%s,false)',('cj.'+name+'_scope','retained-foreign'))
        try:
            with patch('cj_api.local_app.psycopg.connect',return_value=dirty): db.connect(scope)
        except CompositionUnavailable: pass
        else: raise AssertionError('retained authority overwritten at checkout')
        assert dirty.closed
    for bad in ({},dict(document(1),history=[document(1)['current']])):
        invalid=auth.parent/'invalid.json';invalid.write_text(json.dumps(bad))
        try: load_run_context(invalid)
        except LocalContextUnavailable: pass
        else: raise AssertionError('bad explicit context accepted')
    with psycopg.connect(**config) as conn:
        assert conn.execute("SELECT count(*) FROM cj_message_receipt WHERE message_id='unbound'").fetchone()[0]==0
    print('PASS four LOCAL scopes cleared on commit/rollback, invalid profiles refused, no failed-send residue')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
