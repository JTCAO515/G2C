"""Formal local factory + operator/worker CLI on private PG; FakeProvider only."""
import json
import os
import subprocess
import sys
import time
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from fastapi.testclient import TestClient
import psycopg
from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
from cj_api.composition import CompositionUnavailable
from cj_api.local_run_context import load_run_context, LocalContextUnavailable
from cj_message.needs_binding import needs_scope_for
from cj_message.domain import Unavailable, CommitUnknown as MessageCommitUnknown
from cj_message.postgres import Transaction as MessageTransaction, Repository as MessageRepository
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
    subjects=['alice','bob','draft','success','missing','stale','midflight','claim-unknown','period','legacy','send-first','activate-first','broken','receipt-ack','activation-ack','missing-marker']
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
        child_env=dict(env)
        flags=[] if context is None else ['--run-context',str(context)]
        if context is None: child_env.pop('CJ_LOCAL_RUN_CONTEXT',None)
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),'--conninfo-json',str(conninfo),
            '--auth-dir',str(auth),*flags,*args],env=child_env,capture_output=True,text=True,timeout=30)
        assert (result.returncode==0)==ok,(script,result.returncode,result.stdout,result.stderr)
        return result
    def operator(subject,*args,context=profile,ok=True):
        return cli('local_run_context.py','--subject',subject,*args,context=context,ok=ok)
    for subject in subjects:
        if subject not in ('missing','legacy','send-first','activate-first','activation-ack'): operator(subject,'init-budget',context=bigger if subject in ('success','stale','midflight') else profile)
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
        selected=dict(env)
        if context is None: selected.pop('CJ_LOCAL_RUN_CONTEXT',None)
        else: selected['CJ_LOCAL_RUN_CONTEXT']=str(context)
        with patch.dict(os.environ,selected,clear=True): return TestClient(app_from_environment())
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
    def unchanged_state():
        with psycopg.connect(**config) as conn:
            return tuple(conn.execute('SELECT * FROM '+table+' ORDER BY 1,2').fetchall() for table in (
                'cj_message_receipt','cj_message_delivery','cj_local_run_requirement','cj_run_record','cj_run_event','cj_run_step_usage','cj_usage_ledger_candidate','cj_trip_proposal'))
    def missing_configuration():
        before=unchanged_state();model=FakeProvider()
        try: run_worker.run_once(LocalDatabase(conninfo),model,auth)
        except Unavailable: pass
        else: raise AssertionError('protected work consumed without configuration')
        assert model.calls==0 and unchanged_state()==before
        cli('run_worker.py','--once',context=None,ok=False)
        assert unchanged_state()==before
        # Exercise CLI preflight with a sentinel instead of loading any real key.
        selected=dict(env);selected.pop('CJ_LOCAL_RUN_CONTEXT',None)
        argv=['run_worker.py','--conninfo-json',str(conninfo),'--auth-dir',str(auth),'--once','--real']
        with patch.dict(os.environ,selected,clear=True),patch.object(sys,'argv',argv),patch.object(run_worker,'provider',side_effect=AssertionError('credential factory reached')):
            try: run_worker.main()
            except Unavailable: pass
            else: raise AssertionError('missing config preflight bypassed')
        assert unchanged_state()==before
    with api() as client:
        harness.expect(client.put('/v1/conversations',params={'conversation_id':'missing'},headers=headers['missing']),503)
        harness.expect(send(client,'alice','first')[0])
    missing_configuration()
    before=unchanged_state()
    with api(None) as client:
        chat=harness.expect(client.get('/v1/message-send-status',params={'conversation_id':'chat-first'},headers=headers['alice']))['head']
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id='chat-first',message_id='downgrade',text='new input',trip_id=None,
            creation_intent='none',expected_generation=chat['generation'],expected_sequence=chat['last_sequence'])).encode()
        harness.expect(client.post('/v1/messages',content=raw,headers={**headers['alice'],'Content-Type':'application/octet-stream'}),503)
        harness.expect(client.put('/v1/conversations',params={'conversation_id':'new-unprotected'},headers=headers['alice']),503)
    assert unchanged_state()==before
    result=cli('run_worker.py','--once'); assert 'local_provider_calls=1' in result.stdout,result.stdout
    with api() as client:
        assert status(client,'alice','first')['run_status']=='completed'
        harness.expect(send(client,'alice','second')[0])
        harness.expect(send(client,'draft','draft','consider_trip')[0])
    missing_configuration()
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
    missing_configuration()
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
    missing_configuration()
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
    print('PASS missing API/worker config refuses plain pre-step, stale NEEDS and original claimed work; CLI preflight reaches no credential factory')
    # First activation cannot silently change pending legacy execution semantics.
    with api(None) as client: harness.expect(send(client,'legacy','legacy')[0])
    operator('legacy','init-budget',ok=False)
    legacy_model=FakeProvider()
    result=run_worker.run_once(LocalDatabase(conninfo),legacy_model,auth)
    assert result[0].status=='completed' and legacy_model.calls==1
    operator('legacy','init-budget')
    with api(None) as client:
        harness.expect(client.put('/v1/conversations',params={'conversation_id':'legacy-after-activation'},headers=headers['legacy']),503)
    def wait_blocked(fragment):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            with psycopg.connect(**config) as conn:
                if conn.execute("SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE %s",('%'+fragment+'%',)).fetchone(): return
            time.sleep(.01)
        raise AssertionError('expected actual PostgreSQL lock wait: '+fragment)
    # Send wins: pause only real INSERT timing while its original scope lock lives.
    entered=Event();release=Event();insert=MessageTransaction.insert
    def held_insert(tx,stored):
        if tx.scope==scope_for(ISSUER,'send-first'):
            entered.set()
            if not release.wait(5): raise AssertionError('send barrier timeout')
        return insert(tx,stored)
    with api(None) as client,ThreadPoolExecutor(max_workers=2) as pool,patch.object(MessageTransaction,'insert',held_insert):
        sending=pool.submit(send,client,'send-first','send-first')
        assert entered.wait(5)
        activating=pool.submit(operator,'send-first','init-budget',ok=False)
        try: wait_blocked('cj_message_scope')
        finally: release.set()
        harness.expect(sending.result()[0]);activating.result()
    with psycopg.connect(**config) as conn:
        assert conn.execute('SELECT 1 FROM cj_local_run_protection WHERE scope=%s',(scope_for(ISSUER,'send-first'),)).fetchone() is None
    legacy_model=FakeProvider();result=run_worker.run_once(LocalDatabase(conninfo),legacy_model,auth)
    assert result[0].status=='completed' and legacy_model.calls==1
    # Activation wins: a test-only trigger delays commit, never changes the result.
    # The production operator CLI and formal legacy API take their real row locks.
    with api(None) as client: harness.expect(client.put('/v1/conversations',params={'conversation_id':'chat-activate-first'},headers=headers['activate-first']))
    with psycopg.connect(**config,autocommit=True) as admin:
        admin.execute("CREATE FUNCTION test_activation_barrier() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock(17016001); RETURN NEW; END $$")
        admin.execute('CREATE TRIGGER test_activation_barrier BEFORE INSERT ON cj_local_run_protection FOR EACH ROW EXECUTE FUNCTION test_activation_barrier()')
        try:
            with psycopg.connect(**config) as lock,api(None) as client,ThreadPoolExecutor(max_workers=2) as pool:
                lock.execute('SELECT pg_advisory_xact_lock(17016001)')
                activating=pool.submit(operator,'activate-first','init-budget')
                wait_blocked('cj_local_run_protection')
                sending=pool.submit(send,client,'activate-first','activate-first')
                try: wait_blocked('cj_message_scope')
                finally: lock.commit()
                activating.result()
                # Existing conversation open is a safe read, actual receive refuses.
                assert sending.result()[0].status_code==503
        finally:
            admin.execute('DROP TRIGGER test_activation_barrier ON cj_local_run_protection')
            admin.execute('DROP FUNCTION test_activation_barrier()')
        assert admin.execute('SELECT 1 FROM cj_message_receipt WHERE scope=%s',(scope_for(ISSUER,'activate-first'),)).fetchone() is None
    assert Meter.exposure(ledger('activate-first'))==0
    print('PASS actual activation/send lock orders, pending legacy refusal and unchanged unactivated worker semantics')
    # Lose only the acknowledgement AFTER real operator activation commits.
    import local_run_context as operator_module
    connect=psycopg.connect
    class ActivationAckLost:
        def __init__(self,*args,**kwargs): self.inner=connect(*args,**kwargs)
        def __enter__(self): return self.inner.__enter__()
        def __exit__(self,*args):
            result=self.inner.__exit__(*args)
            if args[0] is None: raise psycopg.OperationalError('injected activation commit ACK loss')
            return result
    try:
        with patch.object(operator_module.psycopg,'connect',ActivationAckLost):
            operator_module.provision_budget(conninfo,load_run_context(profile),'activation-ack')
    except psycopg.OperationalError: pass
    else: raise AssertionError('activation commit fault not exercised')
    before=unchanged_state()
    assert json.loads(operator('activation-ack','init-budget').stdout)['status']=='existing'
    assert unchanged_state()==before
    # Original receipt, requirement and outbox are durable together before ACK loss.
    transaction=MessageRepository.transaction;fired=[]
    @contextmanager
    def receipt_ack_lost(repository):
        with transaction(repository) as tx: yield tx
        if repository.scope==scope_for(ISSUER,'receipt-ack') and not fired:
            with psycopg.connect(**config) as conn:
                persisted=conn.execute('SELECT 1 FROM cj_local_run_requirement WHERE scope=%s',(repository.scope,)).fetchone()
            if persisted:
                fired.append(True)
                raise MessageCommitUnknown()
    with api() as client:
        with patch.object(MessageRepository,'transaction',receipt_ack_lost):
            response,raw=send(client,'receipt-ack','receipt-ack')
        assert response.status_code==503 and response.json()['error']['outcome']=='unknown',response.text
        assert fired
        replay=harness.expect(client.post('/v1/messages',content=raw,headers={**headers['receipt-ack'],'Content-Type':'application/octet-stream'}))
        with psycopg.connect(**config) as conn:
            for table in ('cj_message_receipt','cj_message_delivery','cj_local_run_requirement'):
                assert conn.execute('SELECT count(*) FROM '+table+' WHERE scope=%s',(scope_for(ISSUER,'receipt-ack'),)).fetchone()[0]==1
    result=cli('run_worker.py','--once')
    assert 'local_provider_calls=1' in result.stdout
    assert 'local_provider_calls=0' in cli('run_worker.py','--once').stdout
    print('PASS durable activation/receipt ACK loss reconciles original marker/outbox/account without reset or duplicate calls')
    with api() as client: harness.expect(send(client,'missing-marker','missing-marker')[0])
    with psycopg.connect(**config) as conn:
        conn.execute('DELETE FROM cj_local_run_requirement WHERE scope=%s',(scope_for(ISSUER,'missing-marker'),))
    before=unchanged_state();model=FakeProvider()
    try: run_worker.run_once(LocalDatabase(conninfo,run_context=load_run_context(profile)),model,auth)
    except Unavailable: pass
    else: raise AssertionError('protected original without requirement dispatched')
    assert model.calls==0 and unchanged_state()==before
    # A provable owner with corrupted accounting is protected, never reset.
    with api() as client: harness.expect(send(client,'broken','broken')[0])
    account=ledger_scope_for(scope_for(ISSUER,'broken'),load_run_context(profile).current.meter)
    with psycopg.connect(**config) as conn:
        conn.execute("UPDATE cj_usage_ledger_candidate SET ledger=jsonb_set(ledger,'{attempts}','[]') WHERE scope_id=%s",(account,))
    missing_configuration();broken_model=FakeProvider()
    try: run_worker.run_once(LocalDatabase(conninfo,run_context=load_run_context(profile)),broken_model,auth)
    except BudgetUnknown: pass
    else: raise AssertionError('corrupt original budget accepted')
    assert broken_model.calls==0
    with psycopg.connect(**config) as conn:
        assert conn.execute("SELECT ledger->'attempts',revision FROM cj_usage_ledger_candidate WHERE scope_id=%s",(account,)).fetchone()==([],0)
    print('PASS corrupt original ledger stays protected and codec-refused; zero provider calls/debits')
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
