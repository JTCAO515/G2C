"""Registered @2 formal model host on real private runtime PG; no real fees."""
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
import psycopg
from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
from cj_api.local_run_context import load_run_context
from cj_api.composition import CompositionUnavailable
from cj_agent.provider import FakeProvider, ProviderFailed
from cj_usage.codec import decode
from cj_usage.core import Meter
from cj_usage.postgres import PostgresRepository, CommitUnknown as UsageCommitUnknown
from cj_run.postgres import CommitUnknown as RunCommitUnknown
from cj_run.operation_usage import OperationStore
from cj_run.step_usage import OriginalStepOnly
from cj_run.core import Binding
from cj_usage.registered_exit import _model_input
from cj_usage import metered_exit
from cj_api import local_worker_context
from cj_usage.registered_exit import RegisteredExit, Registration, InvocationInput
from cj_api.local_worker_context import checker_for
from cj_run.step_usage import ledger_scope_for
import local_history_pg as harness

ROOT=harness.ROOT
sys.path.insert(0,str(ROOT/'scripts'))


def exercise(auth,conninfo):
    import run_worker
    subjects=['alice','draft','foreign','infra','assoc-ack','reserve-ack','claim-ack','settle-ack','rebuild','late-adapter','late-audit','late-time','unregistered','close-primary','close-complete']
    harness.dev_auth.init(auth,subjects)
    tokens={s:harness.dev_auth.token(auth,s,30) for s in subjects}
    headers={s:{'Authorization':'Bearer '+v} for s,v in tokens.items()}
    now=int(time.time());path=auth.parent/'registered.json'
    path.write_text(json.dumps({'version':'CJ-LOCAL-RUN@2','current':{'meter':dict(unit='provider_call',budget=1,
        period_start=now-10,period_end=now+3600,max_steps=4,max_tools=1,max_output=10000,max_seconds=600),
        'output_limits':{'model':1000,'tool':1000,'memory':1000}},'history':[]}))
    env=dict(os.environ,CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(path))
    def operator(subject,*args,context_path=path):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(conninfo),
            '--auth-dir',str(auth),'--run-context',str(context_path),'--subject',subject,*args],env=env,capture_output=True,text=True,timeout=30)
        assert result.returncode==0,(result.stdout,result.stderr)
        return json.loads(result.stdout)
    for subject in subjects:
        if subject!='infra': operator(subject,'init-budget')
    with patch.dict(os.environ,env): app=app_from_environment()
    config=json.loads(conninfo.read_text());context=load_run_context(path)
    database=LocalDatabase(conninfo,run_context=context)
    def send(client,subject,mid,intent='none'):
        cid='chat-'+mid
        chat=harness.expect(client.put('/v1/conversations',params={'conversation_id':cid},headers=headers[subject]))
        if intent=='consider_trip':
            needs=auth.parent/'needs.json';needs.write_text(json.dumps(dict(action_id='needs1',needs_id='needs',expected_version=0,
                source={'kind':'manual','text':'explicit local input'},changes={'party_size':{'state':'known','value':1}})))
            operator(subject,'put-needs','--input-json',str(needs))
            operator(subject,'bind-needs','--conversation-id',cid,'--needs-id','needs')
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,text='PRIVATE_PROMPT_SENTINEL',trip_id=None,
            creation_intent=intent,expected_generation=chat['generation'],expected_sequence=0)).encode()
        return harness.expect(client.post('/v1/messages',content=raw,headers={**headers[subject],'Content-Type':'application/octet-stream'}))
    def status(client,subject,mid,code=200):
        return harness.expect(client.get('/v2/run-draft-status',params={'message_id':mid},headers=headers[subject]),code)
    with TestClient(app) as client:
        send(client,'alice','one');send(client,'draft','draft','consider_trip')
        no_config=FakeProvider()
        try: run_worker.run_once(LocalDatabase(conninfo),no_config,auth)
        except CompositionUnavailable: pass
        else: raise AssertionError('unconfigured formal worker executed')
        assert no_config.calls==0
        completed=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/run_worker.py'),'--conninfo-json',str(conninfo),
            '--auth-dir',str(auth),'--run-context',str(path),'--once'],env=env,capture_output=True,text=True,timeout=30)
        assert completed.returncode==0,(completed.stdout,completed.stderr)
        assert 'local_provider_calls=2' in completed.stdout and 'message=' not in completed.stdout
        audit=[json.loads(line) for line in completed.stderr.splitlines() if line.startswith('{')]
        assert len(audit)==3 and all(set(row)=={'run_id','attempt_id','kind','stage','unit','confirmed_units','monetary_cost'} for row in audit)
        assert all(row['confirmed_units'] is None and row['monetary_cost']=='UNKNOWN' for row in audit)
        assert 'PRIVATE_PROMPT_SENTINEL' not in completed.stdout+completed.stderr
        assert all(token not in completed.stdout+completed.stderr for token in tokens.values())
        assert status(client,'alice','one')['run_status']=='completed'
        result=status(client,'draft','draft')
        assert result['run_status']=='completed' and result['budget_exhausted_stage']=='draft',result
        send(client,'alice','two')
        model=FakeProvider();run_worker.run_once(database,model,auth)
        assert model.calls==0 and status(client,'alice','two')['budget_exhausted_stage']=='answer'
        status(client,'foreign','one',503)
    with psycopg.connect(**config) as conn:
        assert conn.execute('SELECT count(*) FROM cj_run_step_usage').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM cj_run_metered_operation').fetchone()[0]==4
        assert conn.execute('SELECT count(*) FROM cj_message_metered_requirement').fetchone()[0]==3
        assert conn.execute('SELECT count(*) FROM cj_local_run_requirement').fetchone()[0]==0
        for subject in ('alice','draft'):
            account=ledger_scope_for(scope_for(ISSUER,subject),context.current.meter)
            ledger=decode(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
            assert Meter.exposure(ledger)==1 and len(ledger.attempts)==1
    model=FakeProvider();assert run_worker.run_once(database,model,auth)==[] and model.calls==0
    # Three-kind infrastructure uses actual production AUTH/worker fencing and PG.
    # Only the outbound transport is controlled; these are not business producers.
    broad=json.loads(path.read_text());broad['current']['meter']['budget']=3
    broad_path=auth.parent/'infra.json';broad_path.write_text(json.dumps(broad))
    operator('infra','init-budget',context_path=broad_path)
    broad_context=load_run_context(broad_path);infra_db=LocalDatabase(conninfo,run_context=broad_context)
    with patch.dict(os.environ,{**env,'CJ_LOCAL_RUN_CONTEXT':str(broad_path)}): infra_app=app_from_environment()
    scope=scope_for(ISSUER,'infra');cfg=broad_context.current.meter;account=ledger_scope_for(scope,cfg)
    calls=[]
    def input_for(kind):
        def prepare(argument):
            raw=json.dumps(argument,separators=(',',':')).encode()
            def materialize():
                def invoke():
                    calls.append(kind)
                    yield 'controlled '+kind+' result'
                return invoke
            return InvocationInput(raw,materialize)
        return prepare
    registry={kind:Registration(kind,input_for(kind)) for kind in ('model','tool','memory')}
    class InfrastructureCaller(RegisteredExit):
        def __init__(self,kind):
            def resolve(binding,requested):
                assert binding.scope==scope and requested==account
                return Meter(PostgresRepository(lambda:infra_db.connect(scope),account),cfg,time.time)
            super().__init__(cfg,resolve,clock=time.time,output_limits=broad_context.current.output_limits,
                             environment='local',registrations=registry)
            self.kind=kind
        def prepare(self,runs,binding,step_key,messages,system,provider):
            return self.prepare_operation(runs,binding,'infra.'+self.kind,self.kind,
                                          {'input':'controlled infrastructure input'},stage=step_key)
    with TestClient(infra_app) as client:
        for kind in ('model','tool','memory'):
            send(client,'infra','infra-'+kind)
            worker=run_worker._worker_for_scope(infra_db,FakeProvider(),auth,scope,checker_for(auth))
            worker.budget_exit=InfrastructureCaller(kind)
            assert worker.process()[0].status=='completed'
        send(client,'infra','infra-denied')
        worker=run_worker._worker_for_scope(infra_db,FakeProvider(),auth,scope,checker_for(auth))
        worker.budget_exit=InfrastructureCaller('memory')
        assert worker.process()[0].status=='failed'
        assert status(client,'infra','infra-denied')['budget_exhausted_stage']=='answer'
    assert calls==['model','tool','memory']
    with psycopg.connect(**config) as conn:
        stored=decode(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
        assert Meter.exposure(stored)==3 and len(stored.attempts)==3
        assert {a.command.kind for a in stored.attempts.values()}=={'model','tool','memory'}
        assert all(a.state=='settled' and a.receipt.actual==1 for a in stored.attempts.values())
        assert conn.execute('SELECT count(*) FROM cj_run_metered_binding WHERE scope=%s',(scope,)).fetchone()[0]==4
    def saved(subject):
        owner=scope_for(ISSUER,subject);account_id=ledger_scope_for(owner,context.current.meter)
        with psycopg.connect(**config) as conn:
            ledger=decode(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account_id,)).fetchone()[0])
            operations=conn.execute('SELECT operation_key,attempt_id,operation_id,command_bytes,input_bytes FROM cj_run_metered_operation WHERE scope=%s ORDER BY operation_key',(owner,)).fetchall()
        return ledger,operations
    for phase in ('assoc','reserve','claim','settle'):
        subject=phase+'-ack'
        with TestClient(app) as client: send(client,subject,subject)
        owner=OperationStore if phase=='assoc' else Meter
        method='create' if phase=='assoc' else phase
        actual=getattr(owner,method);lost=[]
        def after_commit(instance,*args,**kwargs):
            result=actual(instance,*args,**kwargs)
            if not lost:
                lost.append(True)
                raise (RunCommitUnknown if phase=='assoc' else UsageCommitUnknown)('injected committed ACK loss')
            return result
        model=FakeProvider()
        with patch.object(owner,method,after_commit): outcome=run_worker.run_once(database,model,auth)
        assert lost and outcome[0].status=='unknown' and model.calls==(1 if phase=='settle' else 0)
        before,rows=saved(subject)
        assert len(rows)==1 and Meter.exposure(before)==(1 if phase in ('claim','settle') else 0)
        replay=FakeProvider();assert run_worker.run_once(database,replay,auth)==[] and replay.calls==0
        assert saved(subject)==(before,rows)
    # Process-style interruption after durable association: no new grant from rebuild.
    with TestClient(app) as client: received=send(client,'rebuild','rebuild')['receipt']
    class Interrupted(BaseException): pass
    create=OperationStore.create
    def interrupted(instance,*args,**kwargs):
        create(instance,*args,**kwargs)
        raise Interrupted()
    model=FakeProvider()
    try:
        with patch.object(OperationStore,'create',interrupted): run_worker.run_once(database,model,auth)
    except Interrupted: pass
    else: raise AssertionError('interruption not exercised')
    assert model.calls==0
    binding=Binding(scope_for(ISSUER,'rebuild'),received['conversation_id'],received['generation'],
                    received['message_id'],received['run_id'],received['sequence'])
    worker=run_worker._worker_for_scope(database,FakeProvider(),auth,binding.scope,checker_for(auth))
    snapshot=OperationStore(worker.runs,context.current.meter).read_original(binding,'model.answer')
    before,rows=saved('rebuild')
    try: OperationStore(worker.runs,context.current.meter).create(binding,'model.answer','model.answer','model',snapshot.original.input_bytes,1000)
    except OriginalStepOnly: pass
    else: raise AssertionError('read-only original rearmed execution')
    assert saved('rebuild')==(before,rows)
    future=json.loads(path.read_text())
    future['current']['meter'].update(period_start=now+3600,period_end=now+7200)
    future_path=auth.parent/'future.json';future_path.write_text(json.dumps(future))
    from cj_usage.local_provider_exit import BudgetUnknown
    missing=LocalDatabase(conninfo,run_context=load_run_context(future_path,clock=lambda:now+3601))
    try: run_worker.run_once(missing,FakeProvider(),auth)
    except BudgetUnknown: pass
    else: raise AssertionError('missing original registered period became current')
    assert saved('rebuild')==(before,rows)
    future['history']=[json.loads(path.read_text())['current']]
    future_path.write_text(json.dumps(future))
    historical=LocalDatabase(conninfo,run_context=load_run_context(future_path,clock=lambda:now+3601))
    recovered=FakeProvider();result=run_worker.run_once(historical,recovered,auth)
    assert result[0].status=='unknown' and recovered.calls==0 and saved('rebuild')[1]==rows
    # Persistent rows are a boundary: inconsistent columns/bytes never become a
    # trusted original. Restore only the deliberately corrupted test data.
    with psycopg.connect(**config) as conn:
        conn.execute("UPDATE cj_run_metered_operation SET kind='tool' WHERE scope=%s",(binding.scope,))
    try:
        try: OperationStore(worker.runs,context.current.meter).read_original(binding,'model.answer')
        except OriginalStepOnly: pass
        else: raise AssertionError('mismatched persisted kind accepted')
    finally:
        with psycopg.connect(**config) as conn:
            conn.execute("UPDATE cj_run_metered_operation SET kind='model' WHERE scope=%s",(binding.scope,))
    with psycopg.connect(**config) as conn:
        conn.execute("UPDATE cj_run_metered_operation SET input_bytes=%s WHERE scope=%s",(b'tampered',binding.scope))
    try:
        try: OperationStore(worker.runs,context.current.meter).read_original(binding,'model.answer')
        except ValueError: pass
        else: raise AssertionError('mismatched persisted input accepted')
    finally:
        with psycopg.connect(**config) as conn:
            conn.execute('UPDATE cj_run_metered_operation SET input_bytes=%s WHERE scope=%s',(snapshot.original.input_bytes,binding.scope))
    assert saved('rebuild')[1]==rows
    invitation=auth/'invited.json';original_invitation=invitation.read_bytes()
    for phase in ('adapter','audit','time'):
        subject='late-'+phase
        with TestClient(app) as client: send(client,subject,subject)
        clock=[time.time()]
        def materializing(argument):
            value=_model_input(argument)
            def materialize():
                invoke=value.materialize()
                if phase=='time': clock[0]+=601
                else: invitation.write_text('[]')
                return invoke
            return InvocationInput(value.original_bytes,materialize)
        audit_emit=metered_exit.audit_prepared
        def auditing(*args):
            audit_emit(*args)
            invitation.write_text('[]')
        model=FakeProvider()
        try:
            if phase=='audit':
                with patch.object(metered_exit,'audit_prepared',auditing): result=run_worker.run_once(database,model,auth)
            else:
                with patch.object(local_worker_context,'MODEL_REGISTRY',{'model.answer':Registration('model',materializing)}), \
                     patch.object(local_worker_context,'time',SimpleNamespace(time=lambda:clock[0])):
                    result=run_worker.run_once(database,model,auth)
        finally: invitation.write_bytes(original_invitation)
        assert model.calls==0 and result[0].status==('failed' if phase=='time' else 'context_invalid')
        assert Meter.exposure(saved(subject)[0])==(0 if phase=='audit' else 1)
    with TestClient(app) as client: send(client,'unregistered','unregistered')
    model=FakeProvider()
    with patch.object(local_worker_context,'MODEL_REGISTRY',{}): result=run_worker.run_once(database,model,auth)
    assert result[0].status=='unknown' and model.calls==0
    assert not saved('unregistered')[1] and not saved('unregistered')[0].attempts
    for primary_failure in (True,False):
        subject='close-primary' if primary_failure else 'close-complete'
        with TestClient(app) as client: send(client,subject,subject)
        primary=ProviderFailed('controlled provider failure');invocations=[]
        class Stream:
            def __iter__(self): return self
            def __next__(self):
                invocations.append(True)
                if primary_failure: raise primary
                raise StopIteration
            def close(self): raise OSError('PRIVATE_CLOSE_SENTINEL')
        def close_input(argument):
            original=_model_input(argument)
            def materialize():
                stream=Stream()
                return lambda:stream
            return InvocationInput(original.original_bytes,materialize)
        with patch.object(local_worker_context,'MODEL_REGISTRY',{'model.answer':Registration('model',close_input)}):
            result=run_worker.run_once(database,FakeProvider(),auth)
        assert len(invocations)==1 and result[0].status==('failed' if primary_failure else 'unknown')
        ledger,_=saved(subject)
        assert Meter.exposure(ledger)==1
        attempt=next(iter(ledger.attempts.values()))
        assert attempt.state==('unknown' if primary_failure else 'settled')
        if primary_failure: assert primary.__notes__==['provider stream cleanup failed; original failure retained']
    print('PASS unregistered exit has no association/claim, cleanup retains primary failure and never invents completion')
    print('PASS registered association/reserve/claim/settle ACK loss, immutable rebuild, audit/adapter revocation and deadline final checks')
    print('PASS three-kind registered infrastructure through canonical AUTH/RUN/PG, shared allowance and over-limit zero invocation')
    print('PASS registered @2 actual API/operator/worker, positive calls, answer/draft denial, new original storage and no-config/cross-owner refusal')
    print('UNRUN: real tool/background business producers, real provider/fees/cloud')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
