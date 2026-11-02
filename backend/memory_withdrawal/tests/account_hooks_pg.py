"""Actual signed local retirement -> C owner account hooks -> physical row audit."""
from datetime import datetime,timedelta,timezone
import base64,json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,scope_for,ISSUER
from cj_api.local_cleanup import Configuration,Runtime
from cj_cleanup.core import encode,digest,Denied
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.store import require_intent
from cj_cleanup.hooks_v1_1 import Selection
from cj_memory.typed_api import create_local_typed_app
from cj_memory.typed_local import TypedConfiguration
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_withdrawal.account_cleanup import account_hooks,MemoryAuthorityAccountHook,MemoryManagementAccountHook,TripAuthorityAccountHook
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import Proposal,packed
from cj_trip.postgres import Repository as TripRepository
from cj_agent.draft import trip_scope_for

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import migrate,pg_suites
import dev_auth


def seed_memory(root,path):
    auth=root/'auth';actors=('graph-alice','graph-bob');dev_auth.init(auth,actors)
    tokens={who:dev_auth.token(auth,who,30) for who in actors}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    extraction=CollectionPolicy(frozenset({'self'}),frozenset({'pace'}),5,4096,lambda entry:True,lambda entry,rows:False)
    policy=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term'}),frozenset(),deadline,
        lambda command,raw:True,lambda command,raw:True)
    app=create_collection_app(conninfo_path=path,auth_dir=auth,
        resolve_collection=lambda principal:(extraction,policy,lambda entry:(None,None)))
    host=app.state.memory_history;c=host.service;token=tokens['graph-alice']
    def ok(response):
        assert response.status_code==200,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        def post(url,value):return ok(client.post(url,content=encode(value),headers=headers['graph-alice']))
        head=ok(client.put('/v1/conversations',params={'conversation_id':'source'},headers=headers['graph-alice']))
        text='Maybe I prefer a slow pace'
        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='source',message_id='origin',text=text,trip_id=None,
            creation_intent='none',expected_generation=head['generation'],expected_sequence=0))
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='source',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        source=dict(conversation_id='source',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='job',attempt_id='attempt',source=source))
        c.transition(token,'job','attempt','inflight')
        c.record_output(token,'job','attempt',encode(dict(version='MEMORY-EXTRACT@1',entries=[dict(subject='self',slot='pace',
            kind='inference',text=text,extent='long_term',occurred_at='date unknown',evidence=[dict(message_id='origin',quote=text)])])))
        c.publish_output(token,'job','attempt')
        listed=ok(client.get('/v3/memory-candidates',params={'job_id':'job','attempt_id':'attempt'},headers=headers['graph-alice']))['result']
        iid=listed['candidates'][0]['candidate_id']
        post('/v3/memory-candidate-actions',dict(version='MEMORY-CANDIDATE@1',action_id='confirm',job_id='job',attempt_id='attempt',
            candidate_id=iid,expected_candidate_version=1,expected_memory_epoch=listed['memory_epoch'],operation='confirm',
            kind='preference',text='I prefer a slow pace',extent='long_term',context=None,occurred_at='date unknown'))
    profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    typed=TypedConfiguration.from_bytes(encode(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=deadline.isoformat(),profiles={who:profile for who in actors}),travel_contexts={who:[] for who in actors})))
    with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=typed)) as client:
        ok(client.post('/v2/memory-management-actions',content=encode(dict(version='MEMORY-management.2',action_id='edit',operation='edit',
            item_id=iid,expected_version=2,expected_source_version=1,context=None,text='I prefer a very slow pace')),headers=headers['graph-alice']))
    return dict(auth=auth,tokens=tokens,headers=headers,database=host.database)


def bootstrap_race(root,path,configuration):
    from threading import Event,Thread
    from cj_api.local_app import LocalDatabase
    auth=root/'race-auth';dev_auth.init(auth,['scope-race'])
    token=dev_auth.token(auth,'scope-race',30);owner=scope_for(ISSUER,'scope-race')
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    typed=TypedConfiguration.from_bytes(encode(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={'scope-race':profile}),travel_contexts={'scope-race':[]})))
    memory=create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=typed)
    gateway=create_local_app(conninfo_path=path,auth_dir=auth,cleanup_configuration=configuration)
    def ok(response):
        assert response.status_code==200,(response.status_code,response.text)
        return response.json()
    with TestClient(gateway) as client:
        device=ok(client.post('/v1/cleanup-devices',content=encode(dict(version='CLEANUP-DEVICE@1',action_id='device',device_id='race-device',state_ref=digest(b'race-state'))),headers=headers))
        prepared=ok(client.post('/v1/account-cleanup-operations',content=encode(dict(version='CLEANUP-API@1',action_id='prepare',binding_id=device['binding_id'])),headers=headers))
    inserted,release,finished=Event(),Event(),Event();answers={};errors=[]
    original=LocalDatabase.connect
    class Connection:
        def __init__(self,connection):self.connection,self.inserted=connection,False
        def __enter__(self):self.connection.__enter__();return self
        def __exit__(self,*args):
            if self.inserted and args[0] is None:
                inserted.set()
                if not release.wait(5):raise AssertionError('scope creator release missing')
            return self.connection.__exit__(*args)
        def execute(self,sql,*args,**kwargs):
            value=self.connection.execute(sql,*args,**kwargs)
            if sql.startswith('INSERT INTO cj_memory_scope'):self.inserted=True
            return value
    def connect(database,scope,*args,**kwargs):
        connection=original(database,scope,*args,**kwargs)
        return Connection(connection) if scope==owner else connection
    def read():
        try:
            with TestClient(memory) as client:answers['read']=client.get('/v2/memories',params={'limit':'1'},headers=headers).status_code
        except Exception as error:errors.append(error)
    def erase():
        try:
            with TestClient(gateway) as client:
                answers['erase']=ok(client.post('/v1/account-cleanup-operations/'+prepared['operation_id']+'/confirmation',content=encode(
                    dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT')),headers=headers))
        except Exception as error:errors.append(error)
        finally:finished.set()
    with patch.object(LocalDatabase,'connect',connect):
        creator=Thread(target=read);creator.start()
        assert inserted.wait(5),'actual first scope INSERT did not pause before COMMIT'
        cleanup=Thread(target=erase);cleanup.start()
        finished.wait(.3);release.set();creator.join(10);cleanup.join(10)
        assert not creator.is_alive() and not cleanup.is_alive() and not errors,errors
    assert answers['read'] in (403,503),answers
    assert answers['erase']['online_status']=='complete',answers
    with psycopg.connect(**json.loads(path.read_text())) as conn:
        retained=conn.execute('SELECT count(*) FROM cj_memory_scope WHERE scope=%s',(owner,)).fetchone()[0]
    assert retained==0,('late first scope COMMIT survived confirmed erasure',retained,answers['erase']['online_status'])
    print('PASS actual in-flight first scope creator cannot leave a late raw owner record after confirmed physical cleanup')


def exercise(root,path):
    seeded=seed_memory(root,path);auth=seeded['auth'];tokens=seeded['tokens'];headers=seeded['headers'];db=seeded['database']
    actors=('graph-alice','graph-bob');deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    typed=TypedConfiguration.from_bytes(encode(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=deadline.isoformat(),profiles={who:profile for who in actors}),travel_contexts={who:[] for who in actors})))
    def expect(response):
        assert response.status_code==200,(response.status_code,response.text)
        return response.json()
    with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=typed)) as client:
        expect(client.post('/v2/memories',content=encode(dict(version='MEMORY-manual.2',operation_id='bob-save',item_id='bob-item',
            subject='self',slot='pace',kind='preference',text='Bob retained canonical value',extent='long_term',context=None,
            occurred_at='date unknown')),headers=headers['graph-bob']))
    signer=ConfirmationSigner(b'synthetic-C-account-trip-confirmation-only')
    identity=create_local_app(conninfo_path=path,auth_dir=auth,confirmation_signer=signer)
    with TestClient(identity) as client:
        for who in actors:
            expect(client.put('/v1/conversations',params={'conversation_id':'account-trip'},headers=headers[who]))
            owner=scope_for(ISSUER,who);trip_scope=trip_scope_for(owner)
            repository=TripRepository(lambda:db.connect(owner),trip_scope,signer)
            proposal=Proposal('account-proposal','account-trip',0,'local-account-fixture',int(time.time())+3600,
                packed(dict(title='Synthetic account Trip',items=[dict(id='synthetic-stop',text='Synthetic stop',
                    verification='pending',evidence=[])])))
            repository.publish(proposal)
            detail=repository.proposal_detail('account-proposal')
            prepared=expect(client.post('/v1/trip-confirmations',content=encode(dict(action_id='account-accept',kind='accept',
                proposal_id='account-proposal',candidate_hash=detail.candidate_hash)),headers={**headers[who],'Content-Type':'application/json'}))
            expect(client.post('/v1/trip-actions',content=base64.b64decode(prepared['action_utf8_base64']),headers=headers[who]))
    targets=('memory-derived','business/memory-management-actions','business/memory-authoritative','business/trip-authoritative',
             'business/feedback-private-actions')
    registry=root/'c-registry.json';registry.write_bytes(encode(dict(version='c-account-component',stores=[
        dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),
        dict(id='business',objects=[dict(id=target.split('/')[1],cleanup_protocol='CLEANUP@1.1') for target in targets[1:]])])))
    configuration=Configuration({'local':b'synthetic-c-owner-cleanup-key-only'},'local',3600,targets,registry,clock=time.time,extra_hooks=account_hooks)
    app=create_local_app(conninfo_path=path,auth_dir=auth,cleanup_configuration=configuration)
    with TestClient(app) as client:
        def post(url,value):return expect(client.post(url,content=encode(value),headers=headers['graph-alice']))
        post('/v1/feedback',dict(action_id='feedback',problem='synthetic scope data',expectation='',references=[]))
        device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='device',device_id='account-device',state_ref=digest(b'local-state')))
        prepared=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='prepare',binding_id=device['binding_id']))
        original_execute=MemoryAuthorityAccountHook.execute;rls_probe=[]
        def execute_with_foreign_lock_probe(hook,request):
            # Test the new UPDATE/locking policy under a genuine original
            # in-progress intent, not only the hook's Python binding check.
            with hook.store.transaction(request.operation_id) as cursor:
                require_intent(cursor,request)
                foreign=scope_for(ISSUER,'graph-bob')
                if hook.scope_table=='cj_trip_scope':foreign=trip_scope_for(foreign)
                cursor.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(foreign,))
                cursor.execute(f'SELECT scope FROM {hook.scope_table} WHERE scope=%s FOR UPDATE',(foreign,))
                assert cursor.fetchone() is None,'new cleanup lock policy admitted another owner'
                rls_probe.append(hook.target)
            return original_execute(hook,request)
        with patch.object(MemoryAuthorityAccountHook,'execute',execute_with_foreign_lock_probe),patch.object(TripAuthorityAccountHook,'execute',execute_with_foreign_lock_probe):
            result=post('/v1/account-cleanup-operations/'+prepared['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',
                registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
        assert rls_probe==['business/memory-authoritative','business/trip-authoritative']
        assert result['business_access']=='revoked' and result['online_status']=='complete',result
        # This component inventory deliberately excludes other B/device/external
        # stores and proves no global all-device/backup completion.
    admin=json.loads(path.read_text());alice=scope_for(ISSUER,'graph-alice');bob=scope_for(ISSUER,'graph-bob')
    with psycopg.connect(**admin) as conn:
        for table in MemoryAuthorityAccountHook.content_tables+MemoryManagementAccountHook.content_tables:
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE scope=%s',(alice,)).fetchone()==(0,),table
        for table in TripAuthorityAccountHook.content_tables:
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE scope=%s',(trip_scope_for(alice),)).fetchone()==(0,),table
        assert conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(bob,)).fetchone()==(1,)
        assert conn.execute('SELECT count(*) FROM cj_trip_record WHERE scope=%s',(trip_scope_for(bob),)).fetchone()==(1,)
        assert conn.execute("SELECT has_table_privilege('cj_m1_runtime','cj_memory_item','DELETE')").fetchone()==(False,)
        assert conn.execute("SELECT has_table_privilege('cj_m1_runtime','cj_trip_record','DELETE')").fetchone()==(False,)
        assert conn.execute("SELECT has_column_privilege('cj_local_cleanup','cj_trip_scope','scope','UPDATE')").fetchone()==(True,)
        assert conn.execute("SELECT has_table_privilege('cj_local_cleanup','cj_trip_scope','UPDATE')").fetchone()==(False,)
        assert conn.execute("SELECT prosecdef FROM pg_proc WHERE proname='cj_c_scope_bootstrap_fence'").fetchone()==(False,)
    runtime=Runtime(db,configuration,scope_for)
    from cj_api.local_worker_context import checker_for
    principal=checker_for(auth).check(tokens['graph-alice']).principal
    original=runtime.original(runtime.subject(principal),prepared['operation_id'])
    coordinator=Coordinator(original.store,runtime.registry,original.hooks)
    request=coordinator.request(prepared['operation_id'],'business/memory-authoritative',alice,Selection('account'))
    assert original.hooks[request.target].reconcile(request).outcome=='confirmed'
    assert original.hooks[request.target].execute(request).outcome=='confirmed'
    from dataclasses import replace
    try:original.hooks[request.target].execute(replace(request,domain_scope=bob))
    except Denied:pass
    else:raise AssertionError('foreign C domain erased')
    try:
        with psycopg.connect(**admin,autocommit=True) as conn:migrate.down(conn,migrate.load(),40)
    except psycopg.errors.RaiseException:pass
    else:raise AssertionError('M41 down accepted retained other-owner data')
    print('PASS actual signed confirmation/retirement and C account hooks erase authoritative Memory/action/Trip records and original bytes, source/queue cleared by existing derived hook; Bob preserved, replay/reconcile and foreign denial, runtime no DELETE, populated down refused; item erasure/global devices UNRUN')
    bootstrap_race(root,path,configuration)


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='c-account-hooks-') as folder:
        with pg_suites.cluster('c_account_hooks',port=55796,role='cj_c_account_hooks',root=Path(folder)/'pg',socket=Path(folder)/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();migrate.up(conn,chain,41);migrate.down(conn,chain,40);migrate.up(conn,chain,41)
            root=Path(folder);path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600)
            exercise(root,path)
