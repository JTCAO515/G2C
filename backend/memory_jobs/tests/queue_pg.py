"""Signed local API + restricted PG C consent/queue, no model or production data."""
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import ISSUER, scope_for
from cj_memory.postgres import Repository
from cj_memory.domain import Service as MemoryService
from cj_memory.manual import ManualPolicy
from cj_message.auth_boundary import AccessBlocked
from cj_auth.interfaces import AdmissionStatus
from cj_message.domain import Unavailable as MessageUnavailable
from cj_memory_jobs.codec import Conflict, Unavailable
from cj_memory_jobs.local_app import build_history_host, create_local_history_app
from cj_memory_jobs.service import OperationWithheld, Service

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth


def compose(conninfo, auth):
    host=build_history_host(conninfo,auth)
    return host.database,host.boundary,host.service.resolve_repository,host.service


def check_cleanup_scope(conninfo,database,boundary,tokens,a,b):
    """Domain-only registry fixture; this is not whole-account #27 acceptance."""
    from cj_cleanup.core import Scope, encode, digest
    from cj_cleanup.coordinator import Coordinator
    from cj_cleanup.hooks_v1_1 import Selection
    from cj_cleanup.registry import freeze
    from cj_cleanup.store import Store
    from cj_memory_jobs.cleanup import CleanupHook, CONTENT_TABLES, TARGET
    config=json.loads(conninfo.read_bytes())
    def owner_store(token):
        principal=boundary.checker.check(token).principal
        subject=digest(encode(asdict(Scope.from_principal('local',principal))))
        def guard(stage):
            current=boundary.checker.check(token)
            if current.status is not AdmissionStatus.ALLOWED or current.principal!=principal:
                raise AssertionError('fixture cleanup identity unavailable')
        return Store(lambda:psycopg.connect(**dict(config,user='cj_local_cleanup')),subject,guard)
    store=owner_store(tokens['alice'])
    entry=dict(id=TARGET,objects=list(CONTENT_TABLES)+['cj_memory_history_fence'],cleanup_protocol='CLEANUP@1.1')
    raw=encode(dict(version='memory-history-test.1',stores=[entry]))
    manifest=freeze(raw,(TARGET,),versions=('CLEANUP@1.1',))
    coordinator=Coordinator(store,lambda:manifest,{TARGET:CleanupHook(store,a)})
    plan={TARGET:dict(domain_scope=a,selection={'kind':'account'})}
    coordinator.create('history-scope-proof',digest(encode(plan)),'account',plan)
    request=coordinator.request('history-scope-proof',TARGET,a,Selection('account'))
    with store.transaction(request.operation_id,writing=False) as cur:
        cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(a,))
        cur.execute('DELETE FROM cj_memory_history_job WHERE scope=%s',(a,))
        assert cur.rowcount==0  # Confirmation alone cannot replace durable dispatch intent.
    assert store.intent(request) is True
    with store.transaction(request.operation_id,writing=False) as cur:
        cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(b,))
        for table in CONTENT_TABLES:
            cur.execute(f'SELECT count(*) FROM {table} WHERE scope=%s',(b,))
            assert cur.fetchone()==(0,)
            cur.execute(f'DELETE FROM {table} WHERE scope=%s',(b,))
            assert cur.rowcount==0
        cur.execute("SELECT set_config('cj.cleanup_scope',%s,true)",(a,))
        cur.execute('SELECT count(*) FROM cj_memory_history_job WHERE scope=%s',(a,))
        assert cur.fetchone()[0]>0
    with database.connect(b) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone()==(1,)
    print('PASS actual cleanup role: confirmation without intent cannot delete; forged other-owner scope is denied by frozen-plan RLS')

    # A Memory selection must never silently become an account-wide deletion.
    item=Selection('memory',item_id='manual-item',item_version=1,scope_epoch=2)
    item_plan={TARGET:dict(domain_scope=a,selection=item.to_dict())}
    coordinator.create('unsupported-item',digest(encode(item_plan)),'memory',item_plan)
    item_request=coordinator.request('unsupported-item',TARGET,a,item)
    assert coordinator.advance(item_request)['status']=='failed'
    with database.connect(a) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone()==(5,)

    # Only the actual deletion transaction loses ACK; coordinator intent is durable first.
    lost={'armed':True}
    class LostCleanupAck:
        def __init__(self,connection):self.connection=connection
        @property
        def autocommit(self):return self.connection.autocommit
        @property
        def info(self):return self.connection.info
        def cursor(self):return self.connection.cursor()
        def rollback(self):return self.connection.rollback()
        def close(self):return self.connection.close()
        def commit(self):
            self.connection.commit()
            if lost['armed']:
                lost['armed']=False
                raise OSError('synthetic lost physical-cleanup ACK')
    uncertain=Store(lambda:LostCleanupAck(psycopg.connect(**dict(config,user='cj_local_cleanup'))),
                    store.subject_digest,store.guard)
    class CountingHook(CleanupHook):
        calls=0
        def execute(self,request):
            self.calls+=1
            return super().execute(request)
    hook=CountingHook(uncertain,a)
    deleting=Coordinator(store,lambda:manifest,{TARGET:hook})
    deleting.create('history-account',digest(encode(plan)),'account',plan)
    erase=deleting.request('history-account',TARGET,a,Selection('account'))
    assert deleting.advance(erase)['status']=='unknown'
    assert hook.calls==1
    assert deleting.advance(erase)['status']=='unknown' and hook.calls==1
    with database.connect(a) as conn:
        for table in CONTENT_TABLES:
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()==(0,)
        assert conn.execute('SELECT erased FROM cj_memory_history_fence').fetchone()==(True,)
        # This target did not erase authoritative Memory or another domain's records.
        assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(1,)
    assert deleting.reconcile(erase)['status']=='complete' and hook.calls==1
    with database.connect(b) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone()==(1,)
    try:
        with database.connect(a) as conn:
            conn.execute('INSERT INTO cj_memory_history_cursor VALUES(%s,%s,0)',(a,'f'*64))
    except psycopg.errors.InsufficientPrivilege:pass
    else:raise AssertionError('runtime rebuilt erased history')
    print('PASS physical C-domain cleanup + actual COMMIT ACK loss, original result reconciliation and zero redispatch; other owner/formal Memory unchanged')

    for owner in ('bob','empty'):
        token=tokens[owner]
        principal=boundary.checker.check(token).principal
        own_scope=scope_for(principal.issuer,principal.subject)
        own=owner_store(token)
        clean=Coordinator(own,lambda:manifest,{TARGET:CleanupHook(own,own_scope)})
        own_plan={TARGET:dict(domain_scope=own_scope,selection={'kind':'account'})}
        operation='self-history-'+owner
        clean.create(operation,digest(encode(own_plan)),'account',own_plan)
        req=clean.request(operation,TARGET,own_scope,Selection('account'))
        assert clean.advance(req)['status']=='complete'
        assert clean.reconcile(req)['status']=='complete'
        with database.connect(own_scope) as conn:
            assert conn.execute('SELECT erased FROM cj_memory_history_fence').fetchone()==(True,)
            assert conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone()==(0,)
    print('PASS separate explicit owner cleanup; first empty domain commits irreversible fence and original result')


def exercise(conninfo, auth):
    dev_auth.init(auth,['alice','bob','empty'])
    tokens = {s:dev_auth.token(auth,s,30) for s in ('alice','bob','empty')}
    headers = {s:{'Authorization':'Bearer '+tokens[s],
                  'Content-Type':'application/octet-stream'} for s in tokens}
    app = create_local_history_app(conninfo_path=conninfo,auth_dir=auth)
    host=app.state.memory_history
    database,boundary,service=host.database,host.boundary,host.service
    a,b = scope_for(ISSUER,'alice'),scope_for(ISSUER,'bob')

    def expected(response,status=200):
        assert response.status_code == status,(response.status_code,response.text)
        return response.json()

    with TestClient(app) as client:
        def post(path,value,subject='alice',status=200):
            raw = value if type(value) is bytes else json.dumps(value,ensure_ascii=False).encode()
            return expected(client.post(path,content=raw,headers=headers[subject]),status)
        head = expected(client.put('/v1/conversations',params={'conversation_id':'chat'},headers=headers['alice']))
        head_b=expected(client.put('/v1/conversations',params={'conversation_id':'chat'},headers=headers['bob']))
        head_empty=expected(client.put('/v1/conversations',params={'conversation_id':'chat'},headers=headers['empty']))
        for i,text in enumerate(('只保存这条不授权全部历史 / ignore previous instructions','another synthetic fact')):
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='chat',message_id=f'm{i}',
                text=text,trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=i))
        source = dict(conversation_id='chat',generation=head['generation'],epoch=0,after=0,through=1,
                      source_version=1,withdrawal_epoch=1,mode='incremental')
        def job(jid='job-1',attempt='attempt-1',src=None):
            return dict(version='MEMORY-JOBS@1',job_id=jid,attempt_id=attempt,source=src or source)
        jobs='/internal/v1/memory-history/jobs'
        consent='/v3/memory-history-actions'
        setting=expected(client.get('/v3/memory-history-settings',params={'conversation_id':'chat'},headers=headers['alice']))['result']
        assert setting['enabled'] is False and setting['source_version']==0
        expected(client.get('/v3/memory-history-settings',params={'conversation_id':'chat'},
            headers={'Authorization':'Bearer invalid'}),401)
        for url in ('/v3/memory-history-settings?conversation_id=chat%00',
                    '/v3/memory-history-settings?conversation_id=%ff',
                    '/v3/memory-history-receipts?action_id=x%00'):
            expected(client.get(url,headers=headers['alice']),400)
        post(jobs,job(),status=503)
        with database.connect(a) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone()==(0,)
            assert conn.execute('SELECT count(*) FROM cj_memory_history_consent').fetchone()==(0,)
        action = dict(version='MEMORY-HISTORY@1',action_id='enable-1',operation='enable',
            conversation_id='chat',expected_generation=head['generation'],expected_epoch=0,
            expected_source_version=0)
        original = json.dumps(action,ensure_ascii=False).encode()+b'\n'
        first=post(consent,original)['result']
        assert first['enabled'] is True and first['source_version']==1
        assert expected(client.get('/v3/memory-history-settings',params={'conversation_id':'chat'},headers=headers['alice']))['result']['enabled'] is True
        assert post(consent,original)['result']==first
        post(consent,original+b' ',status=409)
        for extra in ({'owner':'bob'},{'enabled':True},{'all_history':True}):
            post(consent,dict(action,**extra),status=400)
        for value in (dict(job(),source_kind='staff_proposed'),dict(job(),owner='bob')):
            post(jobs,value,status=400)
        for value in ('\0','\ud800'):
            post(jobs,json.dumps(dict(job(),job_id=value)).encode(),status=400)
        class MessageLostAck:
            def __init__(self,connection):self.connection=connection
            @property
            def autocommit(self):return self.connection.autocommit
            def cursor(self):return self.connection.cursor()
            def bind_scope(self,cursor):return self.connection.bind_scope(cursor)
            def rollback(self):return self.connection.rollback()
            def close(self):return self.connection.close()
            def commit(self):
                self.connection.commit()
                raise OSError('synthetic lost outer MESSAGE ACK')
        message_ack_app=create_local_history_app(conninfo_path=conninfo,auth_dir=auth)
        message_ack_host=message_ack_app.state.memory_history
        def uncertain_message(principal):
            scope=scope_for(principal.issuer,principal.subject)
            repo=message_ack_host.database.message_repository(scope)
            connect=repo.connect
            repo.connect=lambda:MessageLostAck(connect())
            return repo
        message_ack_host.boundary.resolve_repository=uncertain_message
        message_ack_service=message_ack_host.service
        with TestClient(message_ack_app) as message_ack_client:
            read=expected(message_ack_client.get('/v3/memory-history-settings',
                params={'conversation_id':'chat'},headers=headers['alice']),503)
            assert read['error']['outcome']=='unknown' and read['error']['recovery']=='retry_safe_read'
            uncertain=expected(message_ack_client.post(jobs,content=json.dumps(job(),ensure_ascii=False).encode(),
                headers=headers['alice']),503)
            assert uncertain['error']['outcome']=='unknown' and uncertain['error']['recovery']=='reconcile_original'
            head_unknown=expected(message_ack_client.post(consent,
                content=json.dumps(dict(action,action_id='head-unknown',operation='disable',expected_source_version=1)).encode(),
                headers=headers['alice']),503)
            assert head_unknown['error']['outcome']=='unknown' and head_unknown['error']['recovery']=='reconcile_original'
        state=post(jobs,job())['result']
        assert state['state']=='pending'
        assert post(jobs,job())['result']==state
        post(jobs,job('new-job','new-attempt'),status=409)
        first_start=json.loads(service.transition(tokens['alice'],'job-1','attempt-1','inflight'))
        assert first_start['state']=='inflight'
        try:service.transition(tokens['alice'],'job-1','attempt-1','inflight')
        except Conflict:pass
        else:raise AssertionError('original attempt dispatched twice')
        try:message_ack_service.transition(tokens['alice'],'job-1','attempt-1','completed',candidate=b'{"candidate":"synthetic"}')
        except OperationWithheld as error:
            assert (error.operation_id,error.attempt_id,error.recovery)==('job-1','attempt-1','reconcile_original')
        else:raise AssertionError('outer MESSAGE ACK loss became successful completion')
        completed=json.loads(service.query_original(tokens['alice'],'job-1','attempt-1'))
        assert completed['state']=='completed' and completed['processed_through']==1
        assert service.transition(tokens['alice'],'job-1','attempt-1','completed',candidate=b'{"candidate":"synthetic"}')==json.dumps(completed,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
        print('PASS actual outer MESSAGE COMMIT ACK loss after inner C commit: enqueue/completion preserve original task; read uncertainty stays retry_safe_read')
        next_source=dict(source,after=1,through=2)
        post(jobs,job('job-2','attempt-2',next_source))
        service.transition(tokens['alice'],'job-2','attempt-2','inflight')
        service.transition(tokens['alice'],'job-2','attempt-2','unknown')
        disabled=post(consent,dict(action,action_id='disable-2',operation='disable',expected_source_version=1))['result']
        assert disabled['enabled'] is False and disabled['source_version']==2
        post(jobs,job('blocked','blocked',next_source),status=503)
        for target in ('inflight','completed'):
            try:service.transition(tokens['alice'],'job-2','attempt-2',target,candidate=b'late' if target=='completed' else None)
            except (Unavailable,MessageUnavailable):pass
            else:raise AssertionError('disabled source renewed work')
        saved=expected(client.get(jobs,params={'job_id':'job-2','attempt_id':'attempt-2'},headers=headers['alice']))['result']
        assert saved['state']=='unknown'
        assert compose(conninfo,auth)[3].query_original(tokens['alice'],'job-2','attempt-2')==json.dumps(saved,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
        reopened=subprocess.check_output([sys.executable,'-B',str(Path(__file__).resolve()),
            '--query',str(conninfo),str(auth),'job-2','attempt-2'],text=True)
        assert json.loads(reopened)['state']=='unknown'
        for jid in ('job-1','absent'):
            expected(client.get(jobs,params={'job_id':jid,'attempt_id':'attempt-1'},headers=headers['bob']),503)
        reenabled=post(consent,dict(action,action_id='enable-3',expected_source_version=2))['result']
        assert reenabled['source_version']==3 and reenabled['withdrawal_epoch']==1
        post(jobs,job('stale','stale',next_source),status=503)
        fresh=dict(source,source_version=3,through=2)
        post(jobs,job('job-3','attempt-3',fresh))
        service.transition(tokens['alice'],'job-3','attempt-3','inflight')
        print('PASS signed API/PG: default off, exact original consent/job bytes, source dedupe, cursor, restart read, disable/re-enable, stale attempt and two-account rejection')

        # Actual C commit occurs, its ACK is lost, and only original readback recovers.
        class Cursor:
            def __init__(self,original,connection):self.original,self.connection=original,connection
            def execute(self,sql,params=None):
                if sql.startswith('UPDATE cj_memory_history_job SET state=') and params[0]=='completed':
                    self.connection.lose=True
                self.original.execute(sql,params)
                if self.connection.on_sql is not None:self.connection.on_sql(sql,params)
                return self
            def fetchone(self):return self.original.fetchone()
            def fetchall(self):return self.original.fetchall()
            def close(self):return self.original.close()
        class LostAck:
            def __init__(self,original,*,on_sql=None,on_commit=None):
                self.original,self.lose=original,False
                self.on_sql,self.on_commit=on_sql,on_commit
            @property
            def autocommit(self):return self.original.autocommit
            def cursor(self):return Cursor(self.original.cursor(),self)
            def bind_scope(self,cursor):return self.original.bind_scope(cursor)
            def rollback(self):return self.original.rollback()
            def close(self):return self.original.close()
            def commit(self):
                self.original.commit()
                if self.on_commit is not None:self.on_commit()
                if self.lose:raise OSError('synthetic lost commit ACK')
        def uncertain_repository(principal,scope):
            return Repository(lambda:LostAck(database.connect(scope)),scope,
                transaction_binder=lambda connection,cursor:connection.bind_scope(cursor))
        uncertain=Service(boundary,uncertain_repository)
        try:uncertain.transition(tokens['alice'],'job-3','attempt-3','completed',candidate='资料 / data'.encode())
        except OperationWithheld as error:
            assert (error.operation_id,error.attempt_id,error.recovery)==('job-3','attempt-3','reconcile_original')
        else:raise AssertionError('lost ACK reported success')
        assert json.loads(service.query_original(tokens['alice'],'job-3','attempt-3'))['state']=='completed'
        try:service.transition(tokens['alice'],'job-3','attempt-3','inflight')
        except Conflict:pass
        else:raise AssertionError('unknown ACK allowed automatic resend')
        print('PASS actual commit ACK loss: original row/cursor durable, original readback, no second start')

        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='chat',message_id='m'*300,
            text='new synthetic source',trip_id=None,creation_intent='none',
            expected_generation=head['generation'],expected_sequence=2))
        source4=dict(fresh,after=2,through=3)
        invited=auth/'invited.json';invitations=invited.read_bytes()
        def changed_connection(*,after_sql=None,after_commit=None):
            def resolve(principal,scope):
                return Repository(lambda:LostAck(database.connect(scope),on_sql=after_sql,on_commit=after_commit),
                    scope,transaction_binder=lambda connection,cursor:connection.bind_scope(cursor))
            return Service(boundary,resolve)
        for access in (AdmissionStatus.DENIED,AdmissionStatus.UNKNOWN):
            def revoke(sql,params):
                if sql.startswith('INSERT INTO cj_memory_history_job'):
                    invited.write_bytes(b'["bob"]' if access is AdmissionStatus.DENIED else b'{')
            refusing=changed_connection(after_sql=revoke)
            try:
                try:refusing.enqueue(tokens['alice'],json.dumps(job('refused','refused',source4)).encode())
                except AccessBlocked as error:assert error.status is access
                else:raise AssertionError('stale admission committed a job')
            finally:invited.write_bytes(invitations)
            with database.connect(a) as conn:
                assert conn.execute('SELECT count(*) FROM cj_memory_history_job WHERE job_id=%s',('refused',)).fetchone()==(0,)
            try:
                invited.write_bytes(b'["bob"]' if access is AdmissionStatus.DENIED else b'{')
                response=expected(client.get('/v3/memory-history-settings',params={'conversation_id':'chat'},
                    headers=headers['alice']),403 if access is AdmissionStatus.DENIED else 503)
                assert response['error']['code']==('ACCESS_DENIED' if access is AdmissionStatus.DENIED else 'ACCESS_UNKNOWN')
            finally:invited.write_bytes(invitations)
        after_commit=changed_connection(after_commit=lambda:invited.write_bytes(b'["bob"]'))
        try:
            try:after_commit.enqueue(tokens['alice'],json.dumps(job('job-4','attempt-4',source4)).encode())
            except OperationWithheld as error:
                assert (error.operation_id,error.attempt_id)==('job-4','attempt-4')
            else:raise AssertionError('postcommit denial returned a success')
        finally:invited.write_bytes(invitations)
        assert json.loads(service.query_original(tokens['alice'],'job-4','attempt-4'))['state']=='pending'
        service.transition(tokens['alice'],'job-4','attempt-4','inflight')
        print('PASS fresh signed admission: precommit DENIED/UNKNOWN rollback; postcommit denial retains original task/reconcile only')

        ending=dict(version='MESSAGE-SOURCE@1',conversation_id='chat',generation=head['generation'],
                    epoch=0,through=3,conversation_type='travel')
        post('/internal/v1/conversation-end',ending)
        post(jobs,job('end-job','end-attempt',dict(fresh,through=3,mode='conversation_end')))
        assert json.loads(service.query_original(tokens['alice'],'end-job','end-attempt'))['state']=='pending'
        decision=boundary.checker.check(tokens['alice'])
        memory_repository=service.resolve_repository(decision.principal,a)
        memory=MemoryService(memory_repository,manual_policy=ManualPolicy(
            frozenset({'self'}),frozenset({'test.basis'}),frozenset({'long_term'}),frozenset(),
            datetime.now(timezone.utc)+timedelta(hours=1),
            lambda command,raw:command.text=='reviewed synthetic fact',lambda command,raw:True))
        manual=json.dumps(dict(operation_id='manual-1',item_id='manual-item',subject='self',slot='test.basis',
            kind='fact',text='reviewed synthetic fact',extent='long_term',context_id=None,occurred_at='synthetic')).encode()
        def memory_guard(stage):
            current=boundary.checker.check(tokens['alice'])
            if current.status is not AdmissionStatus.ALLOWED:raise AccessBlocked(current,stage)
            return current.principal,a
        result=memory.with_operation(memory_guard,
            lambda operation:json.dumps({'status':operation.save_manual(manual).status}).encode())
        assert json.loads(result)['status']=='active'
        for jid,attempt,target in (('end-job','end-attempt','inflight'),('job-4','attempt-4','completed')):
            try:service.transition(tokens['alice'],jid,attempt,target,candidate=b'late' if target=='completed' else None)
            except Conflict:pass
            else:raise AssertionError('old Memory basis permitted extraction/publication')
        service.transition(tokens['alice'],'job-4','attempt-4','unknown')
        with database.connect(a) as conn:
            assert conn.execute('SELECT candidate FROM cj_memory_history_job WHERE job_id=%s',('job-4',)).fetchone()==(None,)
        print('PASS actual canonical manual save invalidates old queued/in-flight Memory basis, with no late candidate/cursor publication')
        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='chat',message_id='m0',
            text='bob synthetic source',trip_id=None,creation_intent='none',expected_generation=head_b['generation'],expected_sequence=0),subject='bob')
        post(consent,dict(action,expected_generation=head_b['generation']),subject='bob')
        bob_source=dict(source,generation=head_b['generation'])
        assert post(jobs,job(src=bob_source),subject='bob')['result']['state']=='pending'
        assert json.loads(service.query_original(tokens['alice'],'job-1','attempt-1'))['state']=='completed'
        assert json.loads(service.query_original(tokens['bob'],'job-1','attempt-1'))['state']=='pending'
        post(jobs,job('foreign','foreign',source),subject='bob',status=503)
        for table in ('cj_memory_history_consent','cj_memory_history_action',
                      'cj_memory_history_job','cj_memory_history_cursor'):
            with database.connect(b) as conn:
                assert conn.execute(f'SELECT count(*) FROM {table} WHERE scope=%s',(a,)).fetchone()==(0,)
            for statement in (f'DELETE FROM {table}',f'TRUNCATE {table}'):
                try:
                    with database.connect(a) as conn:conn.execute(statement)
                except psycopg.errors.InsufficientPrivilege:pass
                else:raise AssertionError('runtime acquired cleanup authority')
        try:
            with database.connect(b) as conn:
                from hashlib import sha256
                conn.execute('INSERT INTO cj_memory_history_fence(scope_digest) VALUES(%s)',(sha256(a.encode()).hexdigest(),))
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('cross-owner INSERT permitted')
        with database.connect(a) as conn:
            assert conn.execute('SELECT current_user').fetchone()==('cj_m1_runtime',)
            assert conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone()==(5,)
        print('PASS actual end signal/no Trip, FORCE RLS isolation and runtime DELETE/TRUNCATE negatives')
        check_cleanup_scope(conninfo,database,boundary,tokens,a,b)
        for call in (
            lambda:service.transition(tokens['alice'],'job-4','attempt-4','completed',candidate=b'late'),
            lambda:service.apply_consent(tokens['alice'],json.dumps(dict(action,action_id='after-erase',expected_source_version=0)).encode()),
        ):
            try:call()
            except Unavailable:pass
            else:raise AssertionError('erased history revived from old task or enable request')
        with database.connect(a) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone()==(0,)
        post(consent,dict(action,action_id='empty-after-erase',expected_generation=head_empty['generation']),
             subject='empty',status=503)
        empty_scope=scope_for(ISSUER,'empty')
        with database.connect(empty_scope) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_scope').fetchone()==(0,)


if __name__=='__main__':
    if sys.argv[1:2]==['--query']:
        _,conninfo,auth,job,attempt=sys.argv[1:]
        token=dev_auth.token(Path(auth),'alice',30)
        print(compose(Path(conninfo),Path(auth))[3].query_original(token,job,attempt).decode())
        raise SystemExit(0)
    import migrate
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='g2c-history-auth-') as temp:
        conninfo=Path(os.environ['CJ_E2E_CONNINFO'])
        config=json.loads(conninfo.read_bytes())
        down=ROOT/'backend/migrations/down/0034_memory_history.down.sql'
        with psycopg.connect(**config,autocommit=True) as conn:
            migrations=migrate.load()
            migrate.down(conn,migrations,33)
            migrate.up(conn,migrations,migrations[-1]['version'])
        print('PASS registered M34 and dependent append migrations empty down/up over the real migration chain')
        exercise(conninfo,Path(temp)/'auth')
        try:
            with psycopg.connect(**config,autocommit=True) as conn:
                conn.execute(down.read_text())
        except psycopg.errors.RaiseException:
            with psycopg.connect(**config) as conn:
                assert conn.execute('SELECT count(*) FROM cj_memory_history_fence WHERE erased').fetchone()==(3,)
                assert conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone()==(0,)
        else:raise AssertionError('nonempty rollback erased history')
        print('PASS nonempty down refusal preserves erasure fences after content deletion')
