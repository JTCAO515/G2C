"""#273 MESSAGE2/worker real local composition; data/provider are synthetic only."""
import json
import os
import sys
import time
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import Event
from unittest.mock import patch
from fastapi.testclient import TestClient
import psycopg

from cj_api.local_app import LocalDatabase,app_from_environment,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider
from cj_memory.runtime import RuntimeDenied
from cj_agent.draft import proposal_id_for,trip_scope_for
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode as decode_ledger
from cj_usage.core import Meter
from cj_message.travel import ABI
from cj_message.travel import Selection
from cj_message.travel_reference import MessageContextLease
from cj_message.postgres import Repository as MessageRepository
from cj_message.auth_boundary import Boundary
from cj_needs.revision_lease import LeaseUnavailable
from cj_api.composition import CompositionUnavailable
from cj_run.core import Binding,Denied
from cj_api.generated import MessageReceiveV2Response,MessageSendStatusV2Response,RunDisplayV2Response,RunDraftStatusV3Response,RunTravelCancellationResponse
import local_history_pg as harness

sys.path.insert(0,str(harness.ROOT/'scripts'))
import dev_auth
import local_run_context as operator

RESTART_CHILD=r'''
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
import run_worker
from cj_api.local_app import LocalDatabase,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider
conninfo,auth,profile,mid,signal=sys.argv[2:]
class Paused(FakeProvider):
    def stream(self,messages,system=None):
        self.calls+=1
        yield 'first'
        Path(signal).write_text('invoked')
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:time.sleep(.01)
        raise AssertionError('parent did not stop in-flight child')
model=Paused()
database=LocalDatabase(Path(conninfo),run_context=load_run_context(profile),travel_context=True)
host=run_worker._worker_for_scope(database,model,Path(auth),scope_for(ISSUER,'restart'),checker_for(Path(auth)))
receipt=host.messages.query(mid).receipt
host._one(receipt)
'''


def exercise(auth,conninfo):
    import run_worker
    subjects=['alice','bob','missing-config','draft','later','restart','activation','inactive','memory-existing','memory-later']
    harness.dev_auth.init(auth,subjects)
    config=json.loads(conninfo.read_text())
    now=int(time.time())
    document={'version':'CJ-LOCAL-RUN@2','current':{'meter':dict(unit='provider_call',budget=20,
        period_start=now-60,period_end=now+3600,max_steps=20,max_tools=10,max_output=10000,max_seconds=600),
        'output_limits':{'model':2000,'tool':2000,'memory':2000}},'history':[]}
    path=auth.parent/'travel-run.json';path.write_text(json.dumps(document))
    context=load_run_context(path)
    for subject in subjects:
        operator.provision_budget(conninfo,context,subject)
        if subject not in ('activation','inactive','memory-existing'):
            dev_auth.activate_travel(conninfo,subject,context,ABI)
    headers={s:{'Authorization':'Bearer '+harness.dev_auth.token(auth,s,30)} for s in subjects}
    environment={'CJ_LOCAL_AUTH_DIR':str(auth),'CJ_LOCAL_CONNINFO':str(conninfo),
        'CJ_LOCAL_RUN_CONTEXT':str(path),'CJ_LOCAL_TRAVEL_CONTEXT':'message-travel.1'}
    database=LocalDatabase(conninfo,run_context=context,travel_context=True)
    def worker(subject,model):
        return run_worker._worker_for_scope(database,model,auth,scope_for(ISSUER,subject),checker_for(auth))
    def expect(response,code=200):return harness.expect(response,code)
    def binding(subject,accepted):
        r=accepted['receipt']
        return Binding(scope_for(ISSUER,subject),r['conversation_id'],r['generation'],r['message_id'],r['run_id'],r['sequence'])
    with patch.dict(os.environ,environment):
        with TestClient(app_from_environment()) as client:
            def action(subject,aid,operation='create',selection=None):
                raw=json.dumps(dict(version='TRAVEL-context-action.1',action_id=aid,operation=operation,travel_context=selection)).encode()
                return expect(client.post('/v1/travel-context-actions',content=raw,
                    headers={**headers[subject],'Content-Type':'application/octet-stream'}))['receipt']['travel_context']
            a=action('alice','A');b=action('alice','B')
            def send(subject,cid,mid,selected, *, code=200,intent='none',needs=None,head=None):
                if head is None:
                    head=expect(client.put('/v1/conversations',params={'conversation_id':cid},headers=headers[subject]))
                raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id=cid,message_id=mid,text='合成 Beijing',
                    trip_id=None,creation_intent=intent,expected_generation=head['generation'],expected_sequence=head['last_sequence'],
                    travel_context=None if selected is None else {'id':selected['id'],'expected_version':selected['version']},
                    needs_reference=needs)).encode()
                response=client.post('/v2/messages',content=raw,
                    headers={**headers[subject],'Content-Type':'application/octet-stream'})
                value=expect(response,code)
                if code==200:MessageReceiveV2Response.model_validate_json(response.content,strict=True)
                return value,raw
            first,raw=send('alice','same','a-first',a)
            second,_=send('alice','same','b-second',b)
            third,_=send('alice','same','a-third',a)
            other,_=send('alice','other','a-other',a)
            assert [x['reference']['selection_epoch'] for x in (first,second,third)]==[1,2,3]
            assert other['reference']['context_id']==a['id'] and other['reference']['selection_epoch']==1
            assert expect(client.post('/v2/messages',content=raw,
                headers={**headers['alice'],'Content-Type':'application/octet-stream'}))['receipt']==first['receipt']
            original=expect(client.get('/v2/message-send-status',params={'conversation_id':'same','message_id':'a-first'},headers=headers['alice']))
            assert original['reference']==first['reference'] and original['head']['last_sequence']==3
            expect(client.get('/v1/message-receipts',params={'message_id':'a-first'},headers=headers['alice']),503)
            expect(client.get('/v1/message-send-status',params={'conversation_id':'same','message_id':'a-first'},headers=headers['alice']),503)
            foreign=expect(client.get('/v2/message-send-status',params={'conversation_id':'same','message_id':'a-first'},headers=headers['bob']))
            assert foreign['receipt'] is None and foreign['reference'] is None
            send('bob','wrong-owner','wrong-owner',a,code=503)
            model=FakeProvider();host=worker('alice',model);outcomes=host.process()
            states={o.message_id:o.status for o in outcomes}
            assert states=={'a-first':'context_invalid','b-second':'context_invalid','a-third':'completed','a-other':'completed'},states
            assert model.calls==2
            assert host.runs.snapshot(binding('alice',first)).text==''
            none,_=send('alice','no-travel','none',None)
            assert none['reference']['context_kind']=='none' and none['reference']['context_id'] is None
            assert worker('alice',model).process()[0].status=='completed' and model.calls==3
            # A version change is not a new identity, and it never rebinds original bytes.
            pending,pending_raw=send('alice','advance','pending',a)
            changed=action('alice','advance-A','advance',{'id':a['id'],'expected_version':1})
            assert changed['id']==a['id'] and changed['version']==2
            assert worker('alice',model).process()[0].status=='context_invalid' and model.calls==3
            assert expect(client.post('/v2/messages',content=pending_raw,
                headers={**headers['alice'],'Content-Type':'application/octet-stream'}))['reference']==pending['reference']
            stale,_=send('alice','stale','stale',a,code=409)
            assert stale['error']['code']=='MESSAGE_CONTEXT_CONFLICT'
            # Original read is allowed after context invalidation, but it gives no lease.
            authority=worker('alice',FakeProvider()).message_context
            ref=authority.read_original(binding('alice',pending))
            assert ref.context_version==1 and authority.valid(binding('alice',pending)) is False
            # Frozen ID grammar includes slash; the actual GET must recover this original.
            slash=action('bob','read/original')
            found=expect(client.get('/v1/travel-context-actions/read%2Foriginal',headers=headers['bob']))
            assert found['receipt']['travel_context']==slash
            # Consecutive identical choices keep one epoch; normal later messages
            # must not invalidate the earlier message merely by increasing head.
            normal1,_=send('alice','normal','normal-1',changed)
            normal2,_=send('alice','normal','normal-2',changed)
            assert normal1['reference']['selection_epoch']==normal2['reference']['selection_epoch']==1
            more=worker('alice',model).process()
            assert [o.status for o in more]==['completed','completed'] and model.calls==5
            held=worker('alice',FakeProvider())
            original_binding=binding('alice',normal2)
            with ExitStack() as leases:
                with held.runs.repository.transaction() as tx:
                    tx.get(original_binding)
                    lease=leases.enter_context(held.message_context.hold_for_effect(original_binding))
                    stored=lease.original_message()
                    with patch.object(held.message_context.repository,'connect',side_effect=AssertionError('second message connection')):
                        assert held.runs.valid(original_binding) is True
                        assert held.message_context.active_original(original_binding)==stored
                    assert lease.reference.owner_scope==scope_for(ISSUER,'alice')
                    try:lease.reference=lease.reference
                    except AttributeError:pass
                    else:raise AssertionError('lease reference replaced')
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        try:pool.submit(lease.check,original_binding).result()
                        except LeaseUnavailable:pass
                        else:raise AssertionError('cross-thread lease used')
            try:lease.check(original_binding)
            except LeaseUnavailable:pass
            else:raise AssertionError('expired lease used')
            try:MessageContextLease(held.message_context,None,original_binding,held.message_context.read_original(original_binding),stored)
            except TypeError:pass
            else:raise AssertionError('caller minted a lease')
            # Missing explicit mode is not permission to turn off travel fences.
            no_mode,no_mode_raw=send('missing-config','no-mode','no-mode',None)
            disabled=LocalDatabase(conninfo,run_context=context)
            denied_model=FakeProvider()
            try:run_worker.run_once(disabled,denied_model,auth)
            except CompositionUnavailable:pass
            else:raise AssertionError('missing travel configuration dispatched')
            assert denied_model.calls==0
            with patch.dict(os.environ,{'CJ_LOCAL_TRAVEL_CONTEXT':''}):
                try:app_from_environment()
                except CompositionUnavailable:pass
                else:raise AssertionError('unknown capability accepted')
            # Admission UNKNOWN before started keeps the original queued/unacked
            # state; it never adds the forbidden queued->unknown transition.
            uncertain=worker('missing-config',FakeProvider())
            admit=uncertain.message_context.admit
            def unknown():raise LeaseUnavailable('synthetic admission dependency unknown')
            uncertain.message_context.admit=unknown
            try:uncertain.process()
            except LeaseUnavailable:pass
            else:raise AssertionError('unknown admission was consumed')
            queued=uncertain.runs.snapshot(binding('missing-config',no_mode))
            assert queued.status=='queued' and not queued.events and uncertain.provider.calls==0
            uncertain.message_context.admit=admit
            assert uncertain.process()[0].status=='completed' and uncertain.provider.calls==1
            # A legal owner edit between stream advances occurs after the first
            # step's M/T locks release; final publication must reject its old ref.
            mid=action('alice','mid-context')
            moving,_=send('alice','midflight','midflight',mid)
            class MovingProvider(FakeProvider):
                def stream(self,messages,system=None):
                    self.calls+=1
                    yield 'old'  # below the unchanged 24-character flush threshold
                    action('alice','mid-advance','advance',{'id':mid['id'],'expected_version':1})
                    yield 'SYNTHETIC_PRIVATE_OLD_TRAVEL'
            moving_model=MovingProvider();moving_host=worker('alice',moving_model)
            assert moving_host.process()[0].status=='context_invalid' and moving_model.calls==1
            state=moving_host.runs.snapshot(binding('alice',moving))
            assert state.text=='' and not state.effects
            # Real MESSAGE commit uncertainty keeps receipt/ref/outbox atomic.
            class LostAck:
                def __init__(self,connection):self.connection=connection
                def __getattr__(self,name):return getattr(self.connection,name)
                def commit(self):
                    self.connection.commit()
                    raise OSError('synthetic original MESSAGE acknowledgement lost')
            def lost_repository(connect,scope,**kwargs):
                return MessageRepository(lambda:LostAck(connect()),scope,**kwargs)
            ack_head=expect(client.put('/v1/conversations',params={'conversation_id':'message-ack'},headers=headers['bob']))
            with patch('cj_api.local_app.MessageRepository',side_effect=lost_repository):
                lost,lost_raw=send('bob','message-ack','message-ack',None,code=503,head=ack_head)
                assert lost['error']['code']=='MESSAGE_OUTCOME_UNKNOWN'
            ack=expect(client.get('/v2/message-send-status',params={'conversation_id':'message-ack','message_id':'message-ack'},headers=headers['bob']))
            replay=expect(client.post('/v2/messages',content=lost_raw,
                headers={**headers['bob'],'Content-Type':'application/octet-stream'}))
            assert ack['receipt']==replay['receipt'] and ack['reference']==replay['reference']
            assert worker('bob',FakeProvider()).process()[0].status=='completed'
            # Explicit NEEDS reference wins over a legacy conversation selector.
            def put_needs(needs_id,party):
                file=auth.parent/(needs_id+'.json')
                file.write_text(json.dumps(dict(action_id='create-'+needs_id,needs_id=needs_id,expected_version=0,
                    source={'kind':'manual','text':'合成 user-provided planning'},changes={'party_size':{'state':'known','value':party}})))
                return operator.put_needs(conninfo,auth,'draft',file.read_bytes())
            put_needs('needs',1);put_needs('different',9)
            expect(client.put('/v1/conversations',params={'conversation_id':'draft'},headers=headers['draft']))
            operator.bind_needs(conninfo,'draft','draft','different')
            drafting,_=send('draft','draft','draft',None,intent='consider_trip',needs={'id':'needs','expected_version':1})
            draft_model=FakeProvider();draft_host=worker('draft',draft_model)
            assert draft_host.process()[0].status=='completed' and draft_model.calls==2
            with psycopg.connect(**config) as admin:
                selected=admin.execute('SELECT needs_id,needs_version FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s',
                    (scope_for(ISSUER,'draft'),'draft')).fetchone()
                assert selected==('needs',1)
                assert admin.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]==0
            send('alice','foreign-needs','foreign-needs',None,code=503,intent='consider_trip',needs={'id':'needs','expected_version':1})
            send('draft','stale-needs','stale-needs',None,code=503,intent='consider_trip',needs={'id':'needs','expected_version':2})
            # Both actual lock orders, with a canonical boundary writer and M1
            # PG connections. No callback writes into its own held business row.
            lock_context=action('alice','lock-context')
            locking,_=send('alice','locks','lock-1',lock_context)
            lock_host=worker('alice',FakeProvider());lock_binding=binding('alice',locking)
            lock_host.runs.accept(lock_binding)
            token=headers['alice']['Authorization'].split(' ',1)[1]
            def action_bytes(aid,version):
                return json.dumps(dict(version='TRAVEL-context-action.1',action_id=aid,operation='advance',
                    travel_context={'id':lock_context['id'],'expected_version':version})).encode()
            def wait_blocked(pid):
                deadline=time.monotonic()+4
                with psycopg.connect(**config,autocommit=True) as admin:
                    while admin.execute('SELECT cardinality(pg_blocking_pids(%s))',(pid,)).fetchone()[0]==0:
                        assert time.monotonic()<deadline,'expected real PG row-lock wait'
                        time.sleep(.01)
            writer_ready=Event();writer_pid=[]
            def resolve_writer(principal):
                owner=scope_for(principal.issuer,principal.subject)
                def connect():
                    conn=database.connect(owner);writer_pid.append(conn.info.backend_pid);writer_ready.set()
                    return conn
                return MessageRepository(connect,owner)
            writer_boundary=Boundary(checker_for(auth),resolve_writer,lambda:None,resolve_travel_repository=resolve_writer)
            with ThreadPoolExecutor(max_workers=1) as pool:
                with ExitStack() as leases:
                    with lock_host.runs.repository.transaction() as tx:
                        tx.get(lock_binding)
                        permit=leases.enter_context(lock_host.message_context.hold_for_effect(lock_binding))
                        pending_write=pool.submit(writer_boundary.travel_action,token,action_bytes('lock-write-1',1))
                        assert writer_ready.wait(3)
                        wait_blocked(writer_pid[0])
                        assert permit.check(lock_binding) is True and not pending_write.done()
                    # The final context lease remains alive after RUN commit.
                    assert permit.check(lock_binding) is True and not pending_write.done()
                written=json.loads(pending_write.result(timeout=10))['travel_context']
                assert written['version']==2
            locking2,_=send('alice','locks','lock-2',written)
            binding2=binding('alice',locking2);lock_host.runs.accept(binding2)
            commit_ready=Event();release_commit=Event();reader_ready=Event();reader_pid=[]
            class PausedCommit:
                def __init__(self,connection):self.connection=connection
                def __getattr__(self,name):return getattr(self.connection,name)
                def commit(self):
                    commit_ready.set()
                    assert release_commit.wait(4),'parent did not release writer'
                    self.connection.commit()
            def resolve_paused(principal):
                owner=scope_for(principal.issuer,principal.subject)
                return MessageRepository(lambda:PausedCommit(database.connect(owner)),owner)
            paused_boundary=Boundary(checker_for(auth),resolve_paused,lambda:None,resolve_travel_repository=resolve_paused)
            original_connect=lock_host.message_context.repository.connect
            def reader_connect():
                conn=original_connect();reader_pid.append(conn.info.backend_pid);reader_ready.set();return conn
            lock_host.message_context.repository.connect=reader_connect
            def read_effect():
                try:
                    with lock_host.runs.repository.transaction() as tx:
                        tx.get(binding2)
                        with lock_host.message_context.hold_for_effect(binding2):
                            raise AssertionError('old-version lease granted after writer')
                except Denied:return 'denied'
            with ThreadPoolExecutor(max_workers=2) as pool:
                write=pool.submit(paused_boundary.travel_action,token,action_bytes('lock-write-2',2))
                assert commit_ready.wait(3)
                read=pool.submit(read_effect)
                assert reader_ready.wait(3)
                wait_blocked(reader_pid[0])
                release_commit.set()
                assert json.loads(write.result(timeout=10))['travel_context']['version']==3
                assert read.result(timeout=10)=='denied'
            rejected=worker('alice',FakeProvider())
            assert [o.status for o in rejected.process()]==['context_invalid','context_invalid']
            assert rejected.provider.calls==0
            # Actual publisher source preparation advances only an injected test
            # clock; final check is SQL-free and runs again before the proposal.
            import cj_agent.draft as draft_module
            from cj_api.local_worker_context import LocalBudgetRouter
            clocked,_=send('draft','deadline','deadline',None,intent='consider_trip',needs={'id':'needs','expected_version':1})
            offset=[0]
            publication_locks=[]
            resolve_original=LocalBudgetRouter._resolve_original
            document_parser=draft_module.document_from_model
            def clocked_exit(router,bind,state):
                result=resolve_original(router,bind,state)
                result.clock=lambda:time.time()+offset[0]
                return result
            def late_source(*args,**kwargs):
                value=document_parser(*args,**kwargs)
                lock=psycopg.connect(**config)
                lock.execute('SELECT scope_id FROM cj_usage_ledger_candidate WHERE scope_id=%s FOR UPDATE',
                    (ledger_scope_for(scope_for(ISSUER,'draft'),context.current.meter),))
                publication_locks.append(lock)
                offset[0]=601
                return value
            deadline_model=FakeProvider();deadline_host=worker('draft',deadline_model)
            try:
                with patch.object(LocalBudgetRouter,'_resolve_original',clocked_exit),patch.object(draft_module,'document_from_model',late_source):
                    assert deadline_host.process()[0].status=='completed'
            finally:
                for lock in publication_locks:
                    lock.rollback();lock.close()
            timed=deadline_host.runs.snapshot(binding('draft',clocked))
            assert timed.text and timed.budget_exhausted_stage=='draft' and timed.draft_outcome=='budget_exhausted'
            assert not timed.effects and deadline_model.calls==2
            with psycopg.connect(**config) as admin:
                assert admin.execute('SELECT count(*) FROM cj_trip_proposal WHERE scope=%s AND proposal_id=%s',
                    (trip_scope_for(scope_for(ISSUER,'draft')),proposal_id_for(clocked['receipt']['run_id']))).fetchone()[0]==0
            # Clock regressions remain UNKNOWN rather than being treated as a
            # fresh deadline. All counters/receipt algorithms remain unchanged.
            regressing,_=send('draft','regression','regression',None,intent='consider_trip',needs={'id':'needs','expected_version':1})
            offset[0]=0
            def backward_source(*args,**kwargs):
                value=document_parser(*args,**kwargs);offset[0]=-1000;return value
            backward_model=FakeProvider();backward_host=worker('draft',backward_model)
            with patch.object(LocalBudgetRouter,'_resolve_original',clocked_exit),patch.object(draft_module,'document_from_model',backward_source):
                assert backward_host.process()[0].status=='unknown'
            assert backward_model.calls==2
            assert not backward_host.runs.snapshot(binding('draft',regressing)).effects
            # A pre-commit failure has no partial receipt/ref/outbox. The manual
            # test reconfirms closure before explicitly resubmitting the same bytes;
            # null alone never authorizes a product retry.
            rollback_head=expect(client.put('/v1/conversations',params={'conversation_id':'rollback'},headers=headers['bob']))
            class BeforeCommit(LostAck):
                def commit(self):raise OSError('synthetic commit acknowledgement unavailable before mutation')
            def before_repository(connect,scope,**kwargs):
                return MessageRepository(lambda:BeforeCommit(connect()),scope,**kwargs)
            with patch('cj_api.local_app.MessageRepository',side_effect=before_repository):
                refused,refused_raw=send('bob','rollback','rollback',None,code=503,head=rollback_head)
                assert refused['error']['code']=='MESSAGE_OUTCOME_UNKNOWN'
            absent=expect(client.get('/v2/message-send-status',params={'conversation_id':'rollback','message_id':'rollback'},headers=headers['bob']))
            assert absent['receipt'] is None and absent['reference'] is None and absent['head']['last_sequence']==0
            with psycopg.connect(**config) as admin:
                for table in ('cj_message_receipt','cj_message_travel_reference','cj_message_delivery'):
                    assert admin.execute('SELECT count(*) FROM '+table+' WHERE scope=%s AND message_id=%s',
                        (scope_for(ISSUER,'bob'),'rollback')).fetchone()[0]==0
            expect(client.post('/v2/messages',content=refused_raw,
                headers={**headers['bob'],'Content-Type':'application/octet-stream'}))
            assert worker('bob',FakeProvider()).process()[0].status=='completed'
            # Execute the actual pre-travel formal CLI, not a parser-only proxy.
            # It would load text from send.2 if it could see the original delivery;
            # the persistent RLS compatibility gate must prevent that read/ACK.
            old_pending,_=send('later','old-consumer','old-consumer',None)
            oldroot=auth.parent/'old-consumer';oldroot.mkdir()
            archive=auth.parent/'old-consumer.tar'
            with archive.open('wb') as output:
                subprocess.run(['git','archive','e652453edb399158bbe9bc6e0115fb130888ae5b','backend','scripts','contracts'],
                    cwd=harness.ROOT,stdout=output,check=True)
            with tarfile.open(archive) as source:source.extractall(oldroot,filter='data')
            oldenv=dict(os.environ,PYTHONPATH=os.pathsep.join([str(oldroot/'backend'),
                *(str(p) for p in (oldroot/'backend').iterdir() if p.is_dir())]))
            old=subprocess.run([sys.executable,'-B',str(oldroot/'scripts/run_worker.py'),
                '--conninfo-json',str(conninfo),'--auth-dir',str(auth),'--run-context',str(path),'--once'],
                cwd=oldroot,env=oldenv,capture_output=True,text=True,timeout=30)
            assert old.returncode==0,(old.returncode,old.stderr)
            assert 'local_provider_calls=0' in old.stdout
            with psycopg.connect(**config) as admin:
                assert admin.execute('SELECT acknowledged FROM cj_message_delivery WHERE scope=%s AND message_id=%s',
                    (scope_for(ISSUER,'later'),'old-consumer')).fetchone()==(False,)
                assert admin.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s',
                    (scope_for(ISSUER,'later'),old_pending['receipt']['run_id'])).fetchone()[0]==0
            current_model=FakeProvider()
            assert worker('later',current_model).process()[0].status=='completed' and current_model.calls==1
            # Real SIGKILL while the original invocation is in-flight; a new
            # worker reconciles that run as UNKNOWN without a second call.
            restarting,_=send('restart','restart','restart',None)
            invoked=auth.parent/'restart-invoked'
            child=subprocess.Popen([sys.executable,'-B','-c',RESTART_CHILD,str(harness.ROOT),str(conninfo),str(auth),
                str(path),'restart',str(invoked)],env=dict(os.environ),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                deadline=time.monotonic()+15
                while not invoked.exists():
                    if child.poll() is not None:
                        out,error=child.communicate();raise AssertionError((child.returncode,out,error))
                    assert time.monotonic()<deadline,'in-flight child did not start'
                    time.sleep(.01)
                child.kill();child.communicate(timeout=10)
                assert child.returncode==-9
            finally:
                if child.poll() is None:
                    child.kill();child.communicate(timeout=10)
            recovery_model=FakeProvider();recovery=worker('restart',recovery_model)
            assert recovery.process()[0].status=='unknown' and recovery_model.calls==0
            assert recovery.runs.snapshot(binding('restart',restarting)).status=='unknown'
            with psycopg.connect(**config) as admin:
                assert admin.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s',
                    (scope_for(ISSUER,'restart'),restarting['receipt']['run_id'])).fetchone()[0]==1
                account=ledger_scope_for(scope_for(ISSUER,'restart'),context.current.meter)
                ledger=decode_ledger(admin.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
                assert Meter.exposure(ledger)==1
            recovered=expect(client.get('/v2/message-send-status',params={'conversation_id':'restart','message_id':'restart'},headers=headers['restart']))
            assert recovered['receipt']==restarting['receipt'] and recovered['reference']==restarting['reference']
            # New public read versions carry the original ref; a later context
            # version never relabels this historical output or authorizes retry.
            display_response=client.get('/v2/run-display',params={'message_id':'a-third'},headers=headers['alice'])
            display=expect(display_response)
            RunDisplayV2Response.model_validate_json(display_response.content,strict=True)
            assert display['snapshot']['status']=='completed' and display['snapshot']['text']
            assert display['reference']==third['reference'] and display['reference']['context_version']==1
            status_response=client.get('/v3/run-draft-status',params={'message_id':'deadline'},headers=headers['draft'])
            status=expect(status_response)
            RunDraftStatusV3Response.model_validate_json(status_response.content,strict=True)
            assert status['budget_exhausted_stage']=='draft' and status['reference']==clocked['reference']
            expect(client.get('/v2/run-display',params={'message_id':'a-third'},headers=headers['bob']),503)
            # Activation checks all original pending deliveries, including an
            # inactive conversation. A successful legacy terminal allows upgrade.
            def legacy(subject):
                head=expect(client.put('/v1/conversations',params={'conversation_id':'legacy'},headers=headers[subject]))
                raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id='legacy',message_id='legacy',text='合成 legacy',
                    trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0)).encode()
                return expect(client.post('/v1/messages',content=raw,
                    headers={**headers[subject],'Content-Type':'application/octet-stream'}))
            for subject in ('activation','inactive'):
                legacy(subject)
                if subject=='inactive':
                    with psycopg.connect(**config) as admin:
                        admin.execute('UPDATE cj_message_chat SET active=false WHERE scope=%s',(scope_for(ISSUER,subject),))
                try:dev_auth.activate_travel(conninfo,subject,context,ABI)
                except psycopg.errors.RaiseException:pass
                else:raise AssertionError('original pending work allowed upgrade')
            legacy_model=FakeProvider();assert worker('activation',legacy_model).process()[0].status=='completed'
            assert legacy_model.calls==1 and dev_auth.activate_travel(conninfo,'activation',context,ABI)=='activated'
            assert dev_auth.activate_travel(conninfo,'activation',context,ABI)=='existing'
            legacy_display=expect(client.get('/v1/run-display',params={'message_id':'legacy'},headers=headers['activation']))
            assert legacy_display['snapshot']['status']=='completed'
            expect(client.get('/v2/run-display',params={'message_id':'legacy'},headers=headers['activation']),503)
            # These are metadata-only negative fixtures, not fake saved Memory
            # facts or proof of #227. Existing Memory requires a real C typed host.
            with psycopg.connect(**config) as admin:
                for subject in ('memory-existing','memory-later'):
                    admin.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s)',(scope_for(ISSUER,subject),))
            try:dev_auth.activate_travel(conninfo,'memory-existing',context,ABI)
            except ValueError:pass
            else:raise AssertionError('conversation-only memory accepted for travel')
            memory_pending,_=send('memory-later','memory-later','memory-later',None)
            memory_model=FakeProvider()
            try:worker('memory-later',memory_model)
            except RuntimeDenied:pass
            else:raise AssertionError('memory silently disabled in upgraded scope')
            assert memory_model.calls==0
            with psycopg.connect(**config) as admin:
                assert admin.execute('SELECT count(*) FROM cj_run_record WHERE scope=%s AND run_id=%s',
                    (scope_for(ISSUER,'memory-later'),memory_pending['receipt']['run_id'])).fetchone()[0]==0
            # C's manual-save seam acquires the same M/T locks and fresh owner;
            # this verifies the real B lease only, with no synthetic Memory save.
            current_authority=worker('alice',FakeProvider()).message_context
            with current_authority.hold_current(Selection.parse({'id':changed['id'],'expected_version':2})) as current:
                assert current.check() is True and current.context.id==changed['id']
            try:current.check()
            except LeaseUnavailable:pass
            else:raise AssertionError('manual current lease escaped its lifetime')
            try:
                with current_authority.hold_current(Selection.parse({'id':slash['id'],'expected_version':1})):
                    raise AssertionError('foreign current context granted')
            except LeaseUnavailable:pass
            # P1 regression: the new producer must have a working public Stop.
            # Cancellation uses historical ownership/origin, never a live context
            # lease, so deactivation and chat closure cannot prevent stopping.
            def cancel(subject,mid,code=200):
                response=client.post('/v2/run-cancellations',json={'version':'RUN-cancel.2','message_id':mid},headers=headers[subject])
                result=expect(response,code)
                if code==200:RunTravelCancellationResponse.model_validate_json(response.content,strict=True)
                return result
            cancel_context=action('alice','cancel-context')
            queued_cancel,_=send('alice','cancel-queued','cancel-queued',cancel_context)
            expect(client.post('/v1/run-cancellations',json={'version':'RUN-cancel.1','message_id':'cancel-queued'},headers=headers['alice']),503)
            action('alice','deactivate-for-stop','deactivate',{'id':cancel_context['id'],'expected_version':1})
            cancel('bob','cancel-queued',503)
            cancelled=cancel('alice','cancel-queued')
            assert cancelled['status']=='cancelled' and cancelled['reference']==queued_cancel['reference']
            repeat=cancel('alice','cancel-queued')
            assert repeat['event_highwater']==cancelled['event_highwater'] and repeat['run_id']==cancelled['run_id']
            stopped=worker('alice',FakeProvider())
            assert stopped.process()[0].status=='cancelled' and stopped.provider.calls==0
            in_flight,_=send('alice','cancel-running','cancel-running',None)
            class CancellingProvider(FakeProvider):
                def stream(self,messages,system=None):
                    self.calls+=1
                    yield 'old'
                    assert cancel('alice','cancel-running')['status']=='cancelled'
                    yield 'SYNTHETIC_LATE_OUTPUT_AFTER_STOP'
            in_flight_model=CancellingProvider();in_flight_host=worker('alice',in_flight_model)
            assert in_flight_host.process()[0].status=='cancelled' and in_flight_model.calls==1
            stopped_state=in_flight_host.runs.snapshot(binding('alice',in_flight))
            assert stopped_state.text=='' and not stopped_state.effects
            # IDs larger than the old 256-byte cancel grammar are valid send.2
            # identities. The new version preserves the full original ID.
            large_id='long-'+('x'*4096)
            large,_=send('alice','large-id',large_id,None)
            assert cancel('alice',large_id)['run_id']==large['receipt']['run_id']
            assert worker('alice',FakeProvider()).process()[0].status=='cancelled'
            closed,_=send('alice','closed-stop','closed-stop',None)
            with psycopg.connect(**config) as admin:
                admin.execute('UPDATE cj_message_chat SET active=false WHERE scope=%s AND conversation_id=%s',
                    (scope_for(ISSUER,'alice'),'closed-stop'))
            assert cancel('alice','closed-stop')['status']=='cancelled'
            with psycopg.connect(**config) as admin:
                assert admin.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s AND run_id IN (%s,%s,%s)',
                    (scope_for(ISSUER,'alice'),queued_cancel['receipt']['run_id'],large['receipt']['run_id'],closed['receipt']['run_id'])).fetchone()[0]==0
        # New app instance reads the original immutable association without dispatch.
        with TestClient(app_from_environment()) as reopened:
            response=reopened.get('/v2/message-send-status',params={'conversation_id':'same','message_id':'a-first'},headers=headers['alice'])
            MessageSendStatusV2Response.model_validate_json(response.content,strict=True)
            recovered=expect(response)
            assert recovered['reference']==first['reference']
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_message_receipt WHERE message_id=%s',('stale',)).fetchone()[0]==0
        assert admin.execute('SELECT count(*) FROM cj_run_metered_operation WHERE run_id IN (%s,%s)',
            (first['receipt']['run_id'],second['receipt']['run_id'])).fetchone()[0]==0
    print('PASS synthetic MESSAGE2/API/worker: immutable origins, same-chat ABA, same-travel cross-chat, none, owner, version, original replay/rebuild, zero pre-dispatch invalid attempts, slash original GET')
    print('PASS actual leases/owner/thread/lifetime, explicit NEEDS, UNKNOWN queued, both PG lock orders, SQL-free deadline/monotonic clock, before/after ACK atomicity, fixed old CLI refusal and SIGKILL recovery with original exposure')
    print('PASS public RUN-cancel.2: queued zero dispatch, in-flight late output refusal, deactivated context/closed chat, cross-owner, full original large ID and idempotent terminal')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
