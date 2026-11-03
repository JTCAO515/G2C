"""Manual item erasure must also fence pre-existing unprocessed authorized history."""
import base64,json,sys,time,tempfile,os
import psycopg
from pathlib import Path
from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient

root_repo=Path(__file__).resolve().parents[3];sys.path[:0]=[str(root_repo/'scripts'),str(root_repo/'backend/memory_withdrawal/tests')]
import dev_auth,local_run_context,run_worker
from cj_api.local_app import scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_background import LocalBackgroundHost
from cj_api.local_cleanup import Configuration
from cj_agent.provider import FakeProvider,ProviderFailed
from cj_memory.manual import ManualPolicy
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory.typed_api import create_local_typed_app
from cj_memory_jobs.collection_app import create_automatic_decision_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.producer import ProducerHost
from cj_memory_jobs.decision_producer import DecisionConversationProducer
from cj_memory_jobs.worker_adapter import MemoryCollectionAdapterV2
from cj_memory_withdrawal.erasure_app import create_erasure_app_v2
from cj_memory_withdrawal.erasure_service import ORDER
from cj_cleanup.core import encode
from cj_cleanup.memory_payloads import hooks,hold_payloads
from cj_run.background import BackgroundJobsV2
from cj_run.background_store import JobRequest
from cj_run.step_usage import ledger_scope_for
from memory_test_inventory import write_inventory

def exercise(root,path,*,phase='unprepared',long_id=False,empty_history=False):
    who='manual-before-history';owner=scope_for(ISSUER,who)
    auth=root/'auth';dev_auth.init(auth,[who]);now=int(time.time())
    quota=root/'quota.json';quota.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=20,period_start=now-60,period_end=now+3600,max_steps=5,max_tools=5,max_output=20000,max_seconds=600),
        output_limits=dict(model=4000,tool=4000,memory=4000)))))
    run=load_run_context(quota);local_run_context.provision_budget(path,run,who)
    token=dev_auth.token(auth,who,30);headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    extraction=CollectionPolicy(frozenset({'self'}),frozenset({'diet.spicy'}),5,4096,lambda entry:True,lambda entry,rows:all(entry.text==row.text for row in rows))
    memory=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term'}),frozenset(),deadline,lambda c,r:True,lambda c,r:True)
    resolve=lambda p:(extraction,memory,lambda e:(None,None))
    app=create_automatic_decision_collection_app(conninfo_path=path,auth_dir=auth,run_context=run,resolve_collection=resolve)
    host=app.state.memory_history;c=host.service
    profile=dict(subjects=['self'],slots={'diet.spicy':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),profiles={who:profile}),travel_contexts={who:[]})
    runtime=TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',collection=collection,selections={who:dict(subject='self',slots=['diet.spicy'],max_bytes=8000)})))
    def ok(response):
        assert response.status_code==200,response.text
        return response.json()
    def send(client,cid,text):
        head=ok(client.put('/v1/conversations',params={'conversation_id':cid},headers=headers))
        message_id='m'*4101 if long_id and cid=='old-chat' else cid
        result=ok(client.post('/v1/messages',content=encode(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=message_id,text=text,
            trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0)),headers=headers))
        return head,result
    with TestClient(app) as client:
        if not empty_history:
            head,original=send(client,'old-chat','No spicy food')
            ok(client.post('/v3/memory-history-actions',content=encode(dict(version='MEMORY-HISTORY@1',action_id='enable-old',operation='enable',
                conversation_id='old-chat',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)),headers=headers))
            assert [r.status for r in run_worker.run_once(host.database,FakeProvider(),auth,memory_configuration=runtime)]==['completed']
    jobs=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=MemoryCollectionAdapterV2(c),max_payload_bytes=262144)
    prepared=[];records=[]
    def submit(t,jid,attempt,query,data):
        prepared.append(data);result=jobs.prepare(t,JobRequest(jid,attempt,query,None,data));records.append(result);return result
    def no_decision(*args):raise AssertionError('ordinary source became a Trip grant')
    producer=DecisionConversationProducer(c,submit,no_decision,max_payload_bytes=262144,max_conversations=100)
    background=LocalBackgroundHost(jobs,auth)
    combined=ProducerHost(producer,lambda:[dev_auth.token(auth,who,5)],background)
    if phase=='pending':
        planned=producer.incremental._plan(token)
        assert len(planned)==1
        c.enqueue_serialized(token,base64.b64decode(planned[0]))
    elif phase in ('prepared','unknown'):
        assert len(producer.poll(token).submitted)==1 and len(records)==1
        if phase=='unknown':
            class Unknown(FakeProvider):
                def stream(self,messages,system=None):self.calls+=1;raise ProviderFailed('synthetic original outcome unknown')
            uncertain=Unknown();run_worker.run_once(host.database,uncertain,auth,memory_configuration=runtime,background_jobs=background)
            assert uncertain.calls==1
    with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=runtime.collection)) as manager:
        ok(manager.post('/v2/memories',content=encode(dict(version='MEMORY-manual.2',operation_id='explicit-save',item_id='explicit-item',subject='self',
            slot='diet.spicy',kind='preference',text='No spicy food',extent='long_term',context=None,occurred_at='date unknown')),headers=headers))
    if empty_history:
        from cj_agent.draft import trip_scope_for
        with psycopg.connect(**json.loads(path.read_text())) as audit:
            assert audit.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(owner,)).fetchone()==(0,)
            assert audit.execute('SELECT count(*) FROM cj_trip_scope WHERE scope=%s',(trip_scope_for(owner),)).fetchone()==(0,)
    registry=root/'registry.json';write_inventory(registry,'manual-old-source-reextract')
    before_delete_prepared=len(prepared)
    account=ledger_scope_for(owner,run.current.meter)
    with psycopg.connect(**json.loads(path.read_text())) as audit:
        ledger=audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0]
    if phase=='unknown':assert any(a['state']=='unknown' and a['receipt'] is None for a in ledger['attempts'].values())
    config=Configuration({'local':b'manual-old-history-synthetic-only'},'local',3600,ORDER,registry)
    erasure=create_erasure_app_v2(conninfo_path=path,auth_dir=auth,run_context=run,resolve_collection=resolve,
        cleanup_configuration=config,resolve_backend_hooks=hooks,hold_payloads=hold_payloads)
    with TestClient(erasure) as client:
        deleted=ok(client.post('/v1/memory-erasures',content=encode(dict(version='MEMORY-ERASURE@1',action_id='delete-manual',item_id='explicit-item',
            expected_version=1,derived_range='owned_trip_derived_scope')),headers=headers))['result']
        assert deleted['online_status']=='complete',deleted
    with host.database.connect(owner) as conn:assert conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(0,)
    with psycopg.connect(**json.loads(path.read_text())) as audit:
        assert audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0]==ledger
    if phase!='unprepared':
        with host.database.connect(owner) as conn:copied=conn.execute('SELECT job_id,state FROM cj_memory_history_job').fetchall()
        originals=[jobs.query_original(token,r['job_id'],r['attempt_id']) for r in records]
        print(json.dumps({'phase':phase,'delete':deleted['online_status'],'C_retained_jobs':copied,'B_originals':originals},ensure_ascii=False),flush=True)
        assert not copied,'deletion reported complete while old C source/job copy remained'
        assert all(r['input_state']=='erased' for r in originals),'deletion retained original B input copies'
        assert all(r['meter_attempt_id']==before['meter_attempt_id'] and r['meter_operation_id']==before['meter_operation_id']
                   for r,before in zip(originals,records))
    class Model(FakeProvider):
        def __init__(self):super().__init__();self.normal=[]
        def stream(self,messages,system=None):
            if system is None:self.normal.append(messages);yield from super().stream(messages,system);return
            self.calls+=1;data=json.loads(messages[0]['content']);message=data['messages'][0]
            yield encode(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot='diet.spicy',kind='preference',text='No spicy food',
                extent='long_term',occurred_at='date unknown',evidence=[dict(ref=message['ref'],quote='No spicy food')])])).decode()
    model=Model();results=run_worker.run_once(host.database,model,auth,memory_configuration=runtime,background_jobs=combined)
    with host.database.connect(owner) as conn:rows=conn.execute('SELECT item_id,status FROM cj_memory_item').fetchall()
    with TestClient(app) as client:send(client,'new-question','What preferences have I saved?')
    new=Model();run_worker.run_once(host.database,new,auth,memory_configuration=runtime)
    print(json.dumps({'delete':deleted['online_status'],'background_outcomes':[r.status for r in results],'rows_after_old_extract':rows,
        'old_text_in_prepared':any(b'No spicy food' in p for p in prepared),'new_model_inputs':new.normal},ensure_ascii=False),flush=True)
    assert not rows,'old authorized pre-delete chat re-extraction revived a deleted manual preference'
    assert not any(b'No spicy food' in value for value in prepared[before_delete_prepared:])
    with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=runtime.collection)) as manager:
        ok(manager.post('/v2/memories',content=encode(dict(version='MEMORY-manual.2',operation_id='fresh-explicit-save',item_id='fresh-explicit-item',subject='self',
            slot='diet.spicy',kind='preference',text='No spicy food',extent='long_term',context=None,occurred_at='date unknown')),headers=headers))
    with TestClient(app) as client:send(client,'explicit-new-question','Use my newly explicitly saved preference')
    fresh=Model();run_worker.run_once(host.database,fresh,auth,memory_configuration=runtime)
    payload=json.loads(fresh.normal[0][0]['content'].split('\n',1)[1])
    assert [item['text'] for item in payload['items']]==['No spicy food']


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('unprepared','pending','prepared','unknown'),default='unprepared')
    parser.add_argument('--long-id',action='store_true')
    parser.add_argument('--empty-history',action='store_true')
    options=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='manual-history-erasure-') as folder:
        exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']),phase=options.phase,long_id=options.long_id,empty_history=options.empty_history)
