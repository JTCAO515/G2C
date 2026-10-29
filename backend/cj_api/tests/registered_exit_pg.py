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

WORKER_CHILD = r'''
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
import run_worker
from cj_api.local_app import LocalDatabase,ISSUER,scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider
conninfo,auth,profile,subject,mid,ready,go,invoked,mode=sys.argv[2:]
class PausedProvider(FakeProvider):
    def stream(self,messages,system=None):
        self.calls+=1
        yield 'controlled first chunk'
        Path(invoked).write_text('started')
        deadline=time.monotonic()+20
        while time.monotonic()<deadline: time.sleep(.01)
        raise AssertionError('parent did not terminate the in-flight worker')
model=PausedProvider() if mode=='pause' else FakeProvider()
database=LocalDatabase(Path(conninfo),run_context=load_run_context(profile))
worker=run_worker._worker_for_scope(database,model,Path(auth),scope_for(ISSUER,subject),checker_for(Path(auth)))
receipt=worker.messages.query(mid).receipt
Path(ready).write_text('ready')
deadline=time.monotonic()+20
while not Path(go).exists():
    assert time.monotonic()<deadline,'parent did not release worker'
    time.sleep(.01)
outcome=worker._one(receipt)
print(json.dumps({'status':outcome.status,'calls':model.calls}),flush=True)
'''


def wait_until(predicate,seconds):
    deadline=time.monotonic()+seconds
    while not predicate():
        assert time.monotonic()<deadline,'controlled worker ordering was not reached'
        time.sleep(.01)


def exercise(auth,conninfo):
    import run_worker
    subjects=['alice','draft','foreign','infra','assoc-ack','reserve-ack','claim-ack','settle-ack','rebuild','late-adapter','late-audit','late-time','unregistered','close-primary','close-complete',
              'unicode-high','unicode-low','unicode-valid','race-left-first','race-right-first','duplicate-process','killed-process',
              'before-assoc','before-reserve','before-claim','before-settle','cancel-before-ack','cancel-after-ack',
              'cancel-before-dispatch','cancel-at-settle']
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
    def send(client,subject,mid,intent='none',*,text='PRIVATE_PROMPT_SENTINEL'):
        cid='chat-'+mid
        chat=harness.expect(client.put('/v1/conversations',params={'conversation_id':cid},headers=headers[subject]))
        if intent=='consider_trip':
            needs=auth.parent/'needs.json';needs.write_text(json.dumps(dict(action_id='needs1',needs_id='needs',expected_version=0,
                source={'kind':'manual','text':'explicit local input'},changes={'party_size':{'state':'known','value':1}})))
            operator(subject,'put-needs','--input-json',str(needs))
            operator(subject,'bind-needs','--conversation-id',cid,'--needs-id','needs')
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,text=text,trip_id=None,
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
    # ASCII JSON escapes can carry unpaired surrogates through MESSAGE acceptance.
    # The actual CLI must terminalize those originals without starving a later scope.
    with TestClient(app) as client:
        send(client,'unicode-high','unicode-high',text='PRIVATE_UNICODE_SENTINEL'+chr(0xd800))
        send(client,'unicode-low','unicode-low',text='PRIVATE_UNICODE_SENTINEL'+chr(0xdc00))
        send(client,'unicode-valid','unicode-valid',text='中文地点与有效字符 🍵')
    completed=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/run_worker.py'),'--conninfo-json',str(conninfo),
        '--auth-dir',str(auth),'--run-context',str(path),'--once'],env=env,capture_output=True,text=True,timeout=30)
    assert completed.returncode==0,(completed.stdout,completed.stderr)
    assert 'local_provider_calls=1' in completed.stdout
    assert 'UnicodeEncodeError' not in completed.stderr and 'PRIVATE_UNICODE_SENTINEL' not in completed.stdout+completed.stderr
    with TestClient(app) as client:
        for subject in ('unicode-high','unicode-low'):
            result=status(client,subject,subject)
            assert result['run_status']=='unknown' and result['budget_exhausted_stage']=='none',result
            ledger,operations=saved(subject)
            assert not ledger.attempts and not operations and Meter.exposure(ledger)==0
        assert status(client,'unicode-valid','unicode-valid')['run_status']=='completed'
    originals={subject:saved(subject) for subject in ('unicode-high','unicode-low','unicode-valid')}
    replay=FakeProvider()
    assert run_worker.run_once(database,replay,auth)==[] and replay.calls==0
    assert originals=={subject:saved(subject) for subject in originals}
    # Before/after commit are different observations. The original four after-ACK
    # cases above remain unchanged; these add faults before each real mutation.
    late_receipt=None
    for phase in ('assoc','reserve','claim','settle'):
        subject='before-'+phase
        with TestClient(app) as client: send(client,subject,subject)
        owner=OperationStore if phase=='assoc' else Meter
        method='create' if phase=='assoc' else phase
        captured=[]
        def before_commit(instance,*args,**kwargs):
            if phase=='settle': captured.append(args[0])
            raise (RunCommitUnknown if phase=='assoc' else UsageCommitUnknown)('injected before commit')
        model=FakeProvider()
        with patch.object(owner,method,before_commit): result=run_worker.run_once(database,model,auth)
        assert result[0].status=='unknown' and model.calls==(1 if phase=='settle' else 0)
        ledger,operations=saved(subject)
        assert len(operations)==(0 if phase=='assoc' else 1)
        assert Meter.exposure(ledger)==(1 if phase=='settle' else 0)
        if phase=='claim': assert next(iter(ledger.attempts.values())).state=='released'
        if phase=='settle': late_receipt=captured[0]
        replay=FakeProvider()
        assert run_worker.run_once(database,replay,auth)==[] and replay.calls==0
        assert saved(subject)==(ledger,operations)
    # The late receipt is the exact object generated by the actual local core
    # after FakeProvider EOF, captured before its failed settlement commit.
    # Historical selection is explicit; no current-period account is provisioned.
    future=json.loads(path.read_text())
    future['current']['meter'].update(period_start=now+3600,period_end=now+7200)
    future['history']=[json.loads(path.read_text())['current']]
    retained_path=auth.parent/'late-receipt-history.json';retained_path.write_text(json.dumps(future))
    retained=load_run_context(retained_path,clock=lambda:now+3601)
    historical=LocalDatabase(conninfo,run_context=retained)
    owner=scope_for(ISSUER,'before-settle');old_profile=retained.history[0]
    account=ledger_scope_for(owner,old_profile.meter)
    late_meter=Meter(PostgresRepository(lambda:historical.connect(owner,usage_profile=old_profile),account),old_profile.meter,time.time)
    stopped,operations=saved('before-settle')
    assert next(iter(stopped.attempts.values())).state=='unknown'
    first=late_meter.settle(late_receipt);second=late_meter.settle(late_receipt)
    assert first==second and first.cancelled and first.state=='settled' and first.receipt==late_receipt
    assert len(saved('before-settle')[0].attempts)==1 and Meter.exposure(saved('before-settle')[0])==late_receipt.actual
    with TestClient(app) as client: assert status(client,'before-settle','before-settle')['run_status']=='unknown'
    assert saved('before-settle')[1]==operations
    with psycopg.connect(**config) as conn:
        assert conn.execute('SELECT 1 FROM cj_usage_ledger_candidate WHERE scope_id=%s',
            (ledger_scope_for(owner,retained.current.meter),)).fetchone() is None
    original=saved('before-settle')
    foreign=scope_for(ISSUER,'foreign')
    from cj_usage.postgres import RepositoryUnavailable
    try: Meter(PostgresRepository(lambda:historical.connect(foreign,usage_profile=old_profile),account),old_profile.meter,time.time).settle(late_receipt)
    except RepositoryUnavailable: pass
    else: raise AssertionError('another user settled the original ledger')
    assert saved('before-settle')==original

    def child(subject,mid,label,mode='normal'):
        folder=auth.parent/('process-'+subject+'-'+label);folder.mkdir()
        named=folder/'conn.json';app_name='cj243-'+subject+'-'+label
        named.write_text(json.dumps({**config,'application_name':app_name}))
        ready,go,invoked=(folder/name for name in ('ready','go','invoked'))
        process=subprocess.Popen([sys.executable,'-B','-c',WORKER_CHILD,str(ROOT),str(named),str(auth),str(path),
            subject,mid,str(ready),str(go),str(invoked),mode],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        return dict(process=process,ready=ready,go=go,invoked=invoked,name=app_name)
    def finished(record):
        stdout,stderr=record['process'].communicate(timeout=20)
        assert record['process'].returncode==0,(stdout,stderr)
        return json.loads(stdout)
    def cleanup(records):
        for record in records:
            if record['process'].poll() is None: record['process'].kill()
            record['process'].communicate(timeout=10)
    def waiting(observer,names,table):
        return {row[0] for row in observer.execute(
            "SELECT DISTINCT application_name FROM pg_stat_activity WHERE application_name=ANY(%s) "
            "AND wait_event_type='Lock' AND query LIKE %s",(names,'%'+table+'%FOR UPDATE%')).fetchall()}
    # Start both interpreters before taking the test-only gate. NO KEY UPDATE
    # admits the source FK's KEY SHARE while blocking the canonical Meter row
    # lock. The other worker waits at the real RUN-scope fence, not at a
    # fabricated parallel Meter entry; the order remains RUN then USAGE.
    for order in (('left','right'),('right','left')):
        subject='race-'+order[0]+'-first'
        mids={label:subject+'-'+label for label in order}
        with TestClient(app) as client:
            for mid in mids.values(): send(client,subject,mid)
        records={}
        try:
            for label in order: records[label]=child(subject,mids[label],label)
            wait_until(lambda:all(r['ready'].exists() for r in records.values()),20)
            account=ledger_scope_for(scope_for(ISSUER,subject),context.current.meter)
            with psycopg.connect(**config) as locker,psycopg.connect(**config,autocommit=True) as observer:
                locker.execute('SELECT 1 FROM cj_usage_ledger_candidate WHERE scope_id=%s FOR NO KEY UPDATE',(account,))
                records[order[0]]['go'].touch()
                wait_until(lambda:records[order[0]]['name'] in waiting(observer,[records[order[0]]['name']],'cj_usage_ledger_candidate'),2)
                records[order[1]]['go'].touch()
                wait_until(lambda:records[order[1]]['name'] in waiting(observer,[records[order[1]]['name']],'cj_run_scope'),2)
                assert records[order[0]]['name'] in waiting(observer,[records[order[0]]['name']],'cj_usage_ledger_candidate')
            outcomes={label:finished(record) for label,record in records.items()}
            assert outcomes[order[0]]=={'status':'completed','calls':1},outcomes
            assert outcomes[order[1]]=={'status':'failed','calls':0},outcomes
        finally: cleanup(records.values())
        ledger,operations=saved(subject)
        assert Meter.exposure(ledger)==1 and len(ledger.attempts)==1 and len(operations)==2
        with TestClient(app) as client:
            assert status(client,subject,mids[order[1]])['budget_exhausted_stage']=='answer'
    subject='duplicate-process';mid=subject
    with TestClient(app) as client: send(client,subject,mid)
    records=[]
    try:
        first=child(subject,mid,'first');records.append(first)
        second=child(subject,mid,'second');records.append(second)
        wait_until(lambda:all(r['ready'].exists() for r in records),20)
        account=ledger_scope_for(scope_for(ISSUER,subject),context.current.meter)
        with psycopg.connect(**config) as locker,psycopg.connect(**config,autocommit=True) as observer:
            locker.execute('SELECT 1 FROM cj_usage_ledger_candidate WHERE scope_id=%s FOR NO KEY UPDATE',(account,))
            first['go'].touch();wait_until(lambda:first['name'] in waiting(observer,[first['name']],'cj_usage_ledger_candidate'),2)
            second['go'].touch();assert finished(second)=={'status':'waiting','calls':0}
        assert finished(first)=={'status':'completed','calls':1}
    finally: cleanup(records)
    ledger,operations=saved(subject)
    assert Meter.exposure(ledger)==1 and len(ledger.attempts)==len(operations)==1

    subject='killed-process'
    with TestClient(app) as client: send(client,subject,subject)
    process=child(subject,subject,'owned','pause')
    try:
        wait_until(lambda:process['ready'].exists(),20)
        process['go'].touch();wait_until(lambda:process['invoked'].exists(),20)
        before,operations=saved(subject)
        assert len(before.attempts)==1 and next(iter(before.attempts.values())).state=='unknown' and Meter.exposure(before)==1
        process['process'].kill();process['process'].communicate(timeout=10)
        assert process['process'].returncode<0
    finally: cleanup([process])
    replay=FakeProvider();result=run_worker.run_once(database,replay,auth)
    assert result[0].status=='unknown' and replay.calls==0
    assert saved(subject)[1]==operations and Meter.exposure(saved(subject)[0])==1

    subject='cancel-before-dispatch'
    with TestClient(app) as client: send(client,subject,subject)
    prepare=RegisteredExit.prepare
    def prepare_then_cancel(exit,runs,binding,*args):
        prepared=prepare(exit,runs,binding,*args)
        runs.cancel(binding)
        return prepared
    model=FakeProvider()
    with patch.object(RegisteredExit,'prepare',prepare_then_cancel): result=run_worker.run_once(database,model,auth)
    ledger,operations=saved(subject)
    assert result[0].status=='cancelled' and model.calls==0 and len(operations)==1 and not ledger.attempts

    # Completion already produced its original local receipt when cancellation
    # wins before the settlement ACK; reconciliation cannot revive this RUN.
    subject='cancel-at-settle'
    with TestClient(app) as client: receipt=send(client,subject,subject)['receipt']
    binding=Binding(scope_for(ISSUER,subject),receipt['conversation_id'],receipt['generation'],
        receipt['message_id'],receipt['run_id'],receipt['sequence'])
    worker=run_worker._worker_for_scope(database,FakeProvider(),auth,binding.scope,checker_for(auth))
    captured=[]
    def cancel_at_settle(meter,receipt):
        captured.append(receipt)
        worker.runs.cancel(binding)
        raise UsageCommitUnknown('controlled completion receipt ACK unknown')
    try:
        with patch.object(Meter,'settle',cancel_at_settle): worker.process()
    except BudgetUnknown: pass
    else: raise AssertionError('completion/cancel settlement uncertainty was hidden')
    assert worker.provider.calls==1 and worker.runs.snapshot(binding).status=='cancelled'
    replay=FakeProvider();result=run_worker.run_once(database,replay,auth)
    assert result[0].status=='cancelled' and replay.calls==0
    stopped=worker.runs.snapshot(binding);before,operations=saved(subject)
    account=ledger_scope_for(binding.scope,context.current.meter)
    meter=Meter(PostgresRepository(lambda:database.connect(binding.scope),account),context.current.meter,time.time)
    original=captured[0]
    assert Meter.exposure(before)==1 and next(iter(before.attempts.values())).state=='unknown'
    assert meter.settle(original)==meter.settle(original)
    assert worker.runs.snapshot(binding)==stopped and saved(subject)[1]==operations
    assert Meter.exposure(saved(subject)[0])==original.actual and len(saved(subject)[0].attempts)==1

    for phase in ('before','after'):
        subject='cancel-'+phase+'-ack'
        with TestClient(app) as client: receipt=send(client,subject,subject)['receipt']
        binding=Binding(scope_for(ISSUER,subject),receipt['conversation_id'],receipt['generation'],
            receipt['message_id'],receipt['run_id'],receipt['sequence'])
        worker=run_worker._worker_for_scope(database,FakeProvider(),auth,binding.scope,checker_for(auth))
        class CancelInFlight(FakeProvider):
            def stream(self,messages,system=None):
                for index,chunk in enumerate(super().stream(messages,system=system)):
                    yield chunk
                    if index==0: worker.runs.cancel(binding)
        model=CancelInFlight();worker.provider=model
        cancel=Meter.cancel
        def cancellation_ack(meter,*args):
            if phase=='after': cancel(meter,*args)
            raise UsageCommitUnknown('controlled cancellation acknowledgement unknown')
        try:
            with patch.object(Meter,'cancel',cancellation_ack): worker.process()
        except BudgetUnknown: pass
        else: raise AssertionError('cancellation ACK uncertainty was hidden')
        assert worker.runs.snapshot(binding).status=='cancelled' and model.calls==1
        before,operations=saved(subject)
        assert Meter.exposure(before)==1 and next(iter(before.attempts.values())).cancelled==(phase=='after')
        replay=FakeProvider();result=run_worker.run_once(database,replay,auth)
        assert result[0].status=='cancelled' and replay.calls==0 and saved(subject)[1]==operations
        assert Meter.exposure(saved(subject)[0])==1
    print('PASS actual registered worker processes compete for the last allowance in both lock orders; duplicate and killed workers never redispatch')
    print('PASS before/after ACK windows, original local late receipt settles idempotently under historical scope, cross-owner refusal and cancelled RUN permanence')
    print('PASS actual worker CLI contains unpaired Unicode input as original unknown with zero calls, continues valid Unicode scope and never replays')
    print('PASS unregistered exit has no association/claim, cleanup retains primary failure and never invents completion')
    print('PASS registered association/reserve/claim/settle ACK loss, immutable rebuild, audit/adapter revocation and deadline final checks')
    print('PASS three-kind registered infrastructure through canonical AUTH/RUN/PG, shared allowance and over-limit zero invocation')
    print('PASS registered @2 actual API/operator/worker, positive calls, answer/draft denial, new original storage and no-config/cross-owner refusal')
    print('UNRUN: real tool/background business producers, real provider/fees/cloud')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
