"""Actual B payload consumer of C's signed item-erasure composition2."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,os,sys,tempfile,time
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

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'scripts'),str(Path(__file__).parent)]
import dev_auth,local_run_context,run_worker
from background_jobs_pg import ExtractFake


def exercise(root,path):
    config=json.loads(path.read_text());auth=root/'auth';dev_auth.init(auth,['erase-a','erase-b']);now=int(time.time())
    quota=root/'quota.json';quota.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=30,period_start=now-60,period_end=now+3600,max_steps=10,max_tools=5,max_output=20000,max_seconds=600),
        output_limits=dict(model=3000,tool=3000,memory=3000)))))
    context=load_run_context(quota)
    for who in ('erase-a','erase-b'):local_run_context.provision_budget(path,context,who)
    dev_auth.activate_travel(path,'erase-a',context,'MESSAGE-TRAVEL-CONSUMER@1')
    database=LocalDatabase(path,run_context=context,travel_context=True)
    tokens={who:dev_auth.token(auth,who,30) for who in ('erase-a','erase-b')}
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
        with psycopg.connect(**config) as audit:
            ledger=audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0]
            assert any(a['state']=='unknown' and a['receipt'] is None for a in ledger['attempts'].values())
            originals=audit.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt WHERE scope=%s ORDER BY message_id',(owner,)).fetchall()
            events=audit.execute('SELECT run_id,sequence,kind,value FROM cj_run_event WHERE scope=%s ORDER BY run_id,sequence',(owner,)).fetchall()
        registry=root/'registry.json';registry.write_bytes(encode(dict(version='b-memory-component',stores=[
            dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
            dict(id='business',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in ORDER if t.startswith('business/')])])) )
        options=Configuration({'memory':b'explicit-synthetic-memory-payload-key'},'memory',3600,ORDER,registry)
        erasure=create_erasure_app_v2(conninfo_path=path,auth_dir=auth,resolve_collection=resolve,cleanup_configuration=options,
            resolve_backend_hooks=hooks,hold_payloads=hold_payloads,run_context=context)
        delete=encode(dict(version='MEMORY-ERASURE@1',action_id='original-delete',item_id=item['item_id'],
            expected_version=item['version'],derived_range='owned_trip_derived_scope'))
        binding=Binding(owner,origin['conversation_id'],origin['generation'],origin['message_id'],origin['run_id'],origin['sequence'])
        with TestClient(erasure) as deleting:
            with database.run_repository(owner).worker_lease(binding) as owned:
                assert owned
                response=deleting.post('/v1/memory-erasures',content=delete,headers=headers['erase-a'])
                assert response.status_code==200,response.text
                value=response.json()['result'];assert value['online_status']=='in_progress' and all(s['state']=='pending' for s in value['steps']),value
            response=deleting.post('/v1/memory-erasures',content=delete,headers=headers['erase-a'])
            assert response.status_code==200,response.text
            value=response.json()['result'];assert value['online_status']=='complete',value
            assert deleting.post('/v1/memory-erasures',content=delete,headers=headers['erase-a']).json()['result']['online_status']=='complete'
            assert deleting.get('/v1/memory-erasure-progress',params={'action_id':'original-delete'},headers=headers['erase-b']).status_code!=200
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
    print('PASS signed C erasure2 + real B hooks/barrier, actual BG2/Meter/Fake and ordinary typed Memory consumers; busy leaves all pending, private B/C copies0, original chat/events/UNKNOWN ledger intact, replay/foreign/no-resend and fresh constructed context validated')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='memory-payload-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
