"""Actual B payload consumer of C's signed item-erasure composition2."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,os,sys,tempfile,time,threading
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER,load_history_configuration
from cj_api.local_run_context import load_run_context
from cj_api.local_cleanup import Configuration
from cj_api.local_background import LocalBackgroundHost,GuardedCollectionAdapterV3
from cj_agent.provider import FakeProvider,ProviderFailed
from cj_memory.manual import ManualPolicy
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_withdrawal.erasure_app import create_erasure_app_v2
from cj_memory_withdrawal.erasure_service import ORDER
from cj_message.source import SourceQuery
from cj_run.background import BackgroundJobsV2
from cj_run.background_store import JobRequest
from cj_run.core import Binding
from cj_run.step_usage import ledger_scope_for
from cj_cleanup.core import encode,digest
from cj_cleanup.memory_payloads import hooks,hold_payloads
from cj_run.payload_evidence import owner_digest

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'scripts'),str(Path(__file__).parent)]
import dev_auth,local_run_context,run_worker
from background_jobs_pg import ExtractFake


def exercise(root,path):
    config=json.loads(path.read_text());auth=root/'auth';dev_auth.init(auth,['erase-a','erase-b','erase-formal']);now=int(time.time())
    quota=root/'quota.json';quota.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=30,period_start=now-60,period_end=now+3600,max_steps=10,max_tools=5,max_output=20000,max_seconds=600),
        output_limits=dict(model=3000,tool=3000,memory=3000)))))
    context=load_run_context(quota)
    for who in ('erase-a','erase-b','erase-formal'):local_run_context.provision_budget(path,context,who)
    dev_auth.activate_travel(path,'erase-a',context,'MESSAGE-TRAVEL-CONSUMER@1')
    database=LocalDatabase(path,run_context=context,travel_context=True)
    tokens={who:dev_auth.token(auth,who,30) for who in ('erase-a','erase-b','erase-formal')}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    app=create_local_app(conninfo_path=path,auth_dir=auth,run_context=context,travel_context=True,
                         history_configuration=load_history_configuration(auth))
    with TestClient(app) as client:
        def send(cid,text):
            head=client.put('/v1/conversations',params={'conversation_id':cid},headers=headers['erase-a']).json()
            value=dict(version='MESSAGE-send.2',conversation_id=cid,message_id=cid,text=text,trip_id=None,creation_intent='none',
                expected_generation=head['generation'],expected_sequence=0,travel_context=None,needs_reference=None)
            response=client.post('/v2/messages',content=encode(value),headers=headers['erase-a'])
            assert response.status_code==200,response.text
            return head,response.json()['receipt']
        head,origin=send('origin','I do not eat spicy food')
        normal=FakeProvider();assert [o.status for o in run_worker.run_once(database,normal,auth)]==['completed']
        assert normal.calls==1
        slots=frozenset({'diet.spicy'});policy=CollectionPolicy(frozenset({'self'}),slots,10,4096,lambda e:True,
            lambda entry,rows:any(entry.text==row.text for row in rows))
        deadline=datetime.now(timezone.utc)+timedelta(hours=1)
        memory=ManualPolicy(policy.subjects,slots,frozenset({'long_term'}),frozenset(),deadline,lambda c,r:True,lambda c,r:True)
        resolve=lambda p:(policy,memory,lambda e:(None,None))
        collection_app=create_collection_app(conninfo_path=path,auth_dir=auth,run_context=context,resolve_collection=resolve)
        host=collection_app.state.memory_history;c=host.service;token=tokens['erase-a']
        c.apply_consent(token,encode(dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='origin',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)))
        query=SourceQuery('origin',head['generation'],0,0,1,1,1)
        raw=encode(dict(version='MEMORY-JOBS@1',job_id='actual-job',attempt_id='actual-attempt',source=dict(
            conversation_id='origin',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')))
        c.enqueue(token,raw);c.transition(token,'actual-job','actual-attempt','inflight')
        prepared=c.prepare_model_input_v2(token,'actual-job','actual-attempt',max_payload_bytes=262144)
        jobs=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=GuardedCollectionAdapterV3(c),max_payload_bytes=262144)
        background=jobs.prepare(token,JobRequest('actual-job','actual-attempt',query,None,prepared))
        extractor=ExtractFake();result=run_worker.run_once(database,extractor,auth,background_jobs=LocalBackgroundHost(jobs,auth))
        assert [o.status for o in result]==['completed'] and extractor.calls==1,result
        publication=json.loads(c.query_publication_v2(token,'actual-job','actual-attempt'));item=publication['receipts'][0]
        assert item['status']=='active',item
        profile=dict(subjects=['self'],slots={'diet.spicy':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
            extents=['long_term'],context_ids=[])
        typed=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),
            profiles={who:profile for who in tokens}),travel_contexts={who:[] for who in tokens})
        runtime=TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',collection=typed,
            selections={who:dict(subject='self',slots=['diet.spicy'],max_bytes=32768) for who in tokens})))
        _,consumer=send('consumer','Use my stored preference')
        class Recorded(FakeProvider):
            def stream(self,messages,system=None):
                self.original_messages=json.loads(json.dumps(messages));yield from super().stream(messages,system)
        model=Recorded();result=run_worker.run_once(database,model,auth,memory_configuration=runtime)
        assert [o.status for o in result]==['completed'] and model.calls==1,result
        assert 'I do not eat spicy food' in model.original_messages[0]['content']
        _,uncertain=send('uncertain','An uncertain model attempt')
        class Unknown(FakeProvider):
            def stream(self,messages,system=None):self.calls+=1;raise ProviderFailed('synthetic outcome unknown')
        unknown=Unknown();run_worker.run_once(database,unknown,auth,memory_configuration=runtime);assert unknown.calls==1
        owner=scope_for(ISSUER,'erase-a');account=ledger_scope_for(owner,context.current.meter)
        _,late=send('late','An original in-flight consumer')
        entered,release=threading.Event(),threading.Event();outcomes=[];errors=[]
        class Blocking(Recorded):
            def stream(self,messages,system=None):
                self.calls+=1;self.original_messages=messages
                yield 'held'
                entered.set()
                if not release.wait(30):raise AssertionError('provider test release timed out')
                yield 'LATE INVALID MEMORY RESULT'
        blocked=Blocking()
        def worker():
            try:outcomes.extend(run_worker.run_once(database,blocked,auth,memory_configuration=runtime))
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=worker);thread.start()
        assert entered.wait(20),errors
        registry=root/'registry.json';registry.write_bytes(encode(dict(version='b-memory-component',stores=[
            dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
            dict(id='business',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in ORDER if t.startswith('business/')])])) )
        options=Configuration({'memory':b'explicit-synthetic-memory-payload-key'},'memory',3600,ORDER,registry)
        acknowledgements=dict(execute=0,reconcile=0,lost=False)
        class LostAck:
            def __init__(self,hook):self.hook=hook
            def execute(self,request):
                acknowledgements['execute']+=1
                result=self.hook.execute(request)
                if not acknowledgements['lost']:
                    acknowledgements['lost']=True
                    raise OSError('synthetic committed result acknowledgement lost')
                return result
            def reconcile(self,request):
                acknowledgements['reconcile']+=1
                return self.hook.reconcile(request)
        def actual_hooks(store,scope,reader):
            actual=hooks(store,scope,reader);actual['business/message']=LostAck(actual['business/message'])
            return actual
        def application():return create_erasure_app_v2(conninfo_path=path,auth_dir=auth,resolve_collection=resolve,cleanup_configuration=options,
            resolve_backend_hooks=actual_hooks,hold_payloads=hold_payloads,run_context=context)
        erasure=application()
        delete=encode(dict(version='MEMORY-ERASURE@1',action_id='original-delete',item_id=item['item_id'],
            expected_version=item['version'],derived_range='owned_trip_derived_scope'))
        binding=Binding(owner,origin['conversation_id'],origin['generation'],origin['message_id'],origin['run_id'],origin['sequence'])
        try:
          with TestClient(erasure) as deleting:
            with database.run_repository(owner).worker_lease(binding) as owned:
                assert owned
                response=deleting.post('/v1/memory-erasures',content=delete,headers=headers['erase-a'])
                assert response.status_code==200,response.text
                value=response.json()['result'];assert value['online_status']=='in_progress' and all(s['state']=='pending' for s in value['steps']),value
            release.set();thread.join(20);assert not thread.is_alive() and not errors,errors
            assert blocked.calls==1 and all(o.status!='completed' for o in outcomes),outcomes
            with psycopg.connect(**config) as audit:
                ledger=audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0]
                assert any(a['state']=='unknown' and a['receipt'] is None for a in ledger['attempts'].values())
                originals=audit.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt WHERE scope=%s ORDER BY message_id',(owner,)).fetchall()
                events=audit.execute('SELECT run_id,sequence,kind,value FROM cj_run_event WHERE scope=%s ORDER BY run_id,sequence',(owner,)).fetchall()
                assert not any(rid==late['run_id'] and kind in ('text_delta','completed') for rid,_,kind,_ in events),events
            response=deleting.post('/v1/memory-erasures',content=delete,headers=headers['erase-a'])
            assert response.status_code==503 and response.json()['error']['code']=='ERASURE_OUTCOME_UNKNOWN',response.text
        finally:
            release.set();thread.join(20);assert not thread.is_alive()
        with TestClient(application()) as deleting:
            response=deleting.post('/v1/memory-erasures',content=delete,headers=headers['erase-a'])
            assert response.status_code==200,response.text
            value=response.json()['result'];assert value['online_status']=='complete',value
            assert deleting.post('/v1/memory-erasures',content=delete,headers=headers['erase-a']).json()['result']['online_status']=='complete'
            assert deleting.get('/v1/memory-erasure-progress',params={'action_id':'original-delete'},headers=headers['erase-b']).status_code!=200
            assert acknowledgements['execute']==1 and acknowledgements['reconcile']>=1,acknowledgements
        with psycopg.connect(**config) as audit:
            assert audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0]==ledger
            assert audit.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt WHERE scope=%s ORDER BY message_id',(owner,)).fetchall()==originals
            assert audit.execute('SELECT run_id,sequence,kind,value FROM cj_run_event WHERE scope=%s ORDER BY run_id,sequence',(owner,)).fetchall()==events
            assert audit.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s AND input_bytes IS NOT NULL',(owner,)).fetchone()==(0,)
            assert audit.execute('SELECT input_bytes FROM cj_run_background_job WHERE scope=%s',(owner,)).fetchone()==(None,)
            assert audit.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(owner,)).fetchone()==(0,)
            assert audit.execute('SELECT count(*) FROM cj_memory_erasure_manifest WHERE scope=%s',(owner,)).fetchone()==(0,)
        original=jobs.query_original(token,'actual-job','actual-attempt')
        assert original['input_state']=='erased' and original['meter_attempt_id']==background['meter_attempt_id']
        after=FakeProvider();assert run_worker.run_once(database,after,auth,memory_configuration=runtime,background_jobs=LocalBackgroundHost(jobs,auth))==[] and after.calls==0
        history=client.get('/v2/message-history',params={'conversation_id':'origin','limit':20},headers=headers['erase-a'])
        assert history.status_code==200 and history.json()['messages'][0]['text']=='I do not eat spicy food',history.text
        send('fresh','A new explicit instruction')
        fresh=Recorded();result=run_worker.run_once(database,fresh,auth,memory_configuration=runtime)
        assert [o.status for o in result]==['completed'] and fresh.calls==1
        assert json.loads(fresh.original_messages[0]['content'].split('\n',1)[1])['items']==[]
        with database.connect(scope_for(ISSUER,'erase-b')) as foreign:
            assert foreign.execute('SELECT count(*) FROM cj_run_payload_erasure').fetchone()==(0,)
        for sql in ('DELETE FROM cj_run_payload_erasure','TRUNCATE cj_run_payload_erasure',
                    "INSERT INTO cj_run_payload_erasure(owner_digest,kind,object_digest,outcome) VALUES(%s,'run',%s,'stopped')"):
            try:
                with database.connect(owner) as runtime_conn:runtime_conn.execute(sql,(owner_digest(owner),'0'*64) if '%s' in sql else None)
            except psycopg.errors.InsufficientPrivilege:pass
            else:raise AssertionError('runtime gained payload erasure write/delete authority')
        with psycopg.connect(**config) as audit:
            from migrate import load
            migration=next(m for m in load() if m['version']==45)
            try:
                with audit.transaction():audit.execute((ROOT/migration['down']).read_text())
            except psycopg.errors.RaiseException as error:assert 'erasure evidence retained' in str(error)
            else:raise AssertionError('populated erasure migration reverted')
    formal_history(root,path,auth,context,headers,typed,resolve,options)
    print('PASS signed C erasure2 + real B hooks/barrier, actual BG2/Meter/Fake and ordinary typed Memory consumers; busy leaves all pending, late provider cannot publish, committed ACK loss/rebuild reconciles without redispatch; private B/C copies0, original chat/events/UNKNOWN ledger intact, replay/foreign/minimal runtime privileges/populated down/fresh context validated')


def formal_history(root,path,auth,context,headers,typed,resolve,options):
    from trip_message_pg import document
    from cj_trip.domain import packed
    from cj_agent.draft import trip_scope_for
    from cj_memory.typed_local import TypedConfiguration
    from cj_memory.typed_api import create_local_typed_app
    import message_trip_profile
    who='erase-formal';scope=scope_for(ISSUER,who);config=json.loads(path.read_text())
    dev_auth.activate_travel(path,who,context,'MESSAGE-TRAVEL-CONSUMER@1')
    message_trip_profile.activate(path,who,context,'MESSAGE-TRIP-CONSUMER@1')
    database=LocalDatabase(path,run_context=context,travel_context=True,trip_context=True)
    database.provision(scope)
    source=packed(document())
    with psycopg.connect(**config) as audit:
        audit.execute('INSERT INTO cj_trip_record(scope,trip_id,version,content) VALUES(%s,%s,1,%s)',(trip_scope_for(scope),'kept-trip',source))
    app=create_local_app(conninfo_path=path,auth_dir=auth,run_context=context,travel_context=True,trip_context=True,
                         history_configuration=load_history_configuration(auth))
    with TestClient(app) as client:
        head=client.put('/v1/conversations',params={'conversation_id':'formal'},headers=headers[who]).json()
        original=encode(dict(version='MESSAGE-send.3',conversation_id='formal',message_id='formal',text='Explain the stored Trip',
            trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0,travel_context=None,needs_reference=None,
            trip_context=dict(id='kept-trip',expected_version=1,day=dict(date='2026-10-31',timezone='Asia/Shanghai'),item_id='item-a')))
        response=client.post('/v3/messages',content=original,headers=headers[who]);assert response.status_code==200,response.text
        receipt=response.json()['receipt']
        assert [o.status for o in run_worker.run_once(database,FakeProvider(),auth)]==['completed']
        before=client.get('/v5/message-history',params={'conversation_id':'formal','limit':10},headers=headers[who])
        assert before.status_code==200 and before.json()['messages'][0]['source_state']=='retained',before.text
        display=client.get('/v6/run-display',params={'message_id':'formal'},headers=headers[who])
        assert display.status_code==200 and display.json()['source_state']=='retained',display.text
        original_snapshot=display.json()['snapshot'];assert original_snapshot['run_id']==receipt['run_id'] and original_snapshot['text']
        with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=TypedConfiguration.from_bytes(encode(typed)))) as manager:
            manual=encode(dict(version='MEMORY-manual.2',operation_id='formal-memory',item_id='formal-memory',subject='self',slot='diet.spicy',
                kind='preference',text='A selected preference',extent='long_term',context=None,occurred_at='date unknown'))
            saved=manager.post('/v2/memories',content=manual,headers=headers[who]);assert saved.status_code==200,saved.text
        erasure=create_erasure_app_v2(conninfo_path=path,auth_dir=auth,resolve_collection=resolve,cleanup_configuration=options,
            resolve_backend_hooks=hooks,hold_payloads=hold_payloads,run_context=context)
        with TestClient(erasure) as deleting:
            result=deleting.post('/v1/memory-erasures',content=encode(dict(version='MEMORY-ERASURE@1',action_id='formal-delete',
                item_id='formal-memory',expected_version=1,derived_range='owned_trip_derived_scope')),headers=headers[who])
            assert result.status_code==200 and result.json()['result']['online_status']=='complete',result.text
        after=client.get('/v5/message-history',params={'conversation_id':'formal','limit':10},headers=headers[who])
        assert after.status_code==200 and after.json()['version']=='MESSAGE-history.5',after.text
        item=after.json()['messages'][0]
        assert item['source_state']=='erased' and item['reference'] is None and item['text']=='Explain the stored Trip',item
        import base64
        assert base64.b64decode(item['original_utf8_base64'])==original
        display=client.get('/v6/run-display',params={'message_id':'formal'},headers=headers[who])
        assert display.status_code==200 and display.json()['version']=='RUN-display.6',display.text
        assert display.json()['source_state']=='erased' and display.json()['reference'] is None and display.json()['snapshot']==original_snapshot,display.text
        assert client.get('/v6/run-display',params={'message_id':'formal'},headers=headers['erase-b']).status_code!=200
        assert client.get('/v3/run-display',params={'message_id':'formal'},headers=headers[who]).status_code==503
        assert client.get('/v2/message-history',params={'conversation_id':'formal','limit':10},headers=headers[who]).status_code==503
        assert client.get('/v5/message-history',params={'conversation_id':'formal','limit':10},headers=headers['erase-b']).status_code!=200
        with psycopg.connect(**config) as audit:
            assert bytes(audit.execute('SELECT content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',(trip_scope_for(scope),'kept-trip')).fetchone()[0])==source
            assert audit.execute('SELECT source_content,content_sha256 FROM cj_message_trip_reference WHERE scope=%s',(scope,)).fetchone()==(None,None)
            proof=audit.execute("DELETE FROM cj_run_payload_erasure WHERE owner_digest=%s AND kind='reference' RETURNING *",(owner_digest(scope),)).fetchone()
            assert proof is not None
        try:
            assert client.get('/v5/message-history',params={'conversation_id':'formal','limit':10},headers=headers[who]).status_code==503
            assert client.get('/v6/run-display',params={'message_id':'formal'},headers=headers[who]).status_code==503
        finally:
            with psycopg.connect(**config) as audit:
                audit.execute('INSERT INTO cj_run_payload_erasure VALUES(%s,%s,%s,%s,%s,%s)',proof)
        assert client.get('/v5/message-history',params={'conversation_id':'formal','limit':10},headers=headers[who]).status_code==200
    print('PASS owned Trip-derived B input/source cache erased; raw original formal chat and accepted Trip retained; history5 explicit erased state, old history unchanged/closed, foreign/missing original proof denied')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='memory-payload-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
