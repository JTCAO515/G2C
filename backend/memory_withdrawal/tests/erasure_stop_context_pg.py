"""Real producer/worker/context proof while physical B cleanup is UNKNOWN."""
from datetime import datetime,timedelta,timezone
import json,os,sys,tempfile,time
from pathlib import Path
import psycopg

from fastapi.testclient import TestClient
from cj_api.local_app import scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_background import LocalBackgroundHost
from cj_api.local_cleanup import Configuration
from cj_agent.provider import FakeProvider,ProviderFailed
from cj_memory.manual import ManualPolicy
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory.typed_api import create_local_typed_app
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.producer import IncrementalProducer,ProducerHost
from cj_memory_jobs.worker_adapter import MemoryCollectionAdapterV2
from cj_memory_withdrawal.erasure_app import create_erasure_app,create_erasure_app_v2
from cj_memory_withdrawal.erasure_command import VERSION
from cj_memory_withdrawal.erasure_service import ORDER
from cj_cleanup.core import encode
from cj_cleanup.store import receipt_for
from cj_run.background import BackgroundJobsV2
from cj_run.background_store import JobRequest
from cj_run.step_usage import ledger_scope_for

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend/memory_jobs/tests')]
import dev_auth,local_run_context,run_worker
from producer_background_pg import Observed


def exercise(root,path,*,backend_hooks=None,hold_payloads=None,expect_complete=False):
    if expect_complete and (backend_hooks is None or hold_payloads is None):
        raise ValueError('actual B hooks/barrier required for complete cross-domain proof')
    actors=('erase-context-alice','erase-context-bob');auth=root/'auth';dev_auth.init(auth,actors)
    now=int(time.time());quota=root/'quota.json'
    quota.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(meter=dict(unit='provider_call',budget=50,
        period_start=now-60,period_end=now+3600,max_steps=20,max_tools=10,max_output=40000,max_seconds=600),
        output_limits=dict(model=4000,tool=4000,memory=4000)))))
    run=load_run_context(quota)
    for who in actors:local_run_context.provision_budget(path,run,who)
    tokens={who:dev_auth.token(auth,who,30) for who in actors}
    headers={who:{'Authorization':'Bearer '+tokens[who],'Content-Type':'application/octet-stream'} for who in actors}
    kinds={'diet.spicy':'preference','mobility.fact':'fact'};slots=frozenset(kinds)
    extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda e:True,lambda e,rows:all(e.text==r.text for r in rows))
    deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),deadline,lambda c,r:True,lambda c,r:True)
    resolve=lambda p:(extraction,memory,lambda e:(None,None))
    app=create_collection_app(conninfo_path=path,auth_dir=auth,run_context=run,resolve_collection=resolve)
    host=app.state.memory_history;c=host.service;alice,bob=actors
    profile=dict(subjects=['self'],slots={k:dict(kind=v,collection_allowed=True,semantic_resolved=True) for k,v in kinds.items()},
                 extents=['long_term'],context_ids=[])
    config=TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',collection=dict(version='local-memory-typed.1',
        collection=dict(version='local-memory-policy.1',expires_at=deadline.isoformat(),profiles={w:profile for w in actors}),
        travel_contexts={w:[] for w in actors}),selections={w:dict(subject='self',slots=sorted(slots),max_bytes=32768) for w in actors})))
    jobs=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=MemoryCollectionAdapterV2(c),max_payload_bytes=262144)
    records=[]
    def submit(token,jid,attempt,query,data):
        result=jobs.prepare(token,JobRequest(jid,attempt,query,None,data));records.append(result);return result
    producer=IncrementalProducer(c,submit,max_payload_bytes=262144,max_conversations=100)
    combined=ProducerHost(producer,lambda:[dev_auth.token(auth,w,5) for w in actors],LocalBackgroundHost(jobs,auth))
    model=Observed()
    def ok(response):
        assert response.status_code==200,(response.status_code,response.text)
        return response.json()
    def send(client,cid,mid,text,who=alice,sequence=0,generation=None):
        head=ok(client.put('/v1/conversations',params={'conversation_id':cid},headers=headers[who]))
        return ok(client.post('/v1/messages',content=encode(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,text=text,
            trip_id=None,creation_intent='none',expected_generation=generation or head['generation'],expected_sequence=sequence)),headers=headers[who]))
    with TestClient(app) as client:
        first=send(client,'history','spicy','No spicy food');head=first['receipt']['generation']
        send(client,'history','height','My height is 170 cm',sequence=1,generation=head)
        ok(client.post('/v3/memory-history-actions',content=encode(dict(version='MEMORY-HISTORY@1',action_id='enable-history',operation='enable',
            conversation_id='history',expected_generation=head,expected_epoch=0,expected_source_version=0)),headers=headers[alice]))
        outcomes=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
        assert all(r.status=='completed' for r in outcomes),outcomes
        assert len(model.extractions)==1 and len(records)==1
        before=send(client,'before','before-question','What preferences have I saved?')['receipt']
        outcomes=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
        assert all(r.status=='completed' for r in outcomes),outcomes
        assert {i['slot'] for i in model.answers[-1]['items']}==set(kinds)
        uncertain=send(client,'uncertain','uncertain-question','A real original with an unknown model outcome')['receipt']
        class Unknown(FakeProvider):
            def stream(self,messages,system=None):
                self.calls+=1
                raise ProviderFailed('synthetic original provider outcome unknown')
        failed=Unknown();run_worker.run_once(host.database,failed,auth,memory_configuration=config)
        assert failed.calls==1
    with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=config.collection)) as manual:
        ok(manual.post('/v2/memories',content=encode(dict(version='MEMORY-manual.2',operation_id='bob-explicit',item_id='bob-preference',
            subject='self',slot='diet.spicy',kind='preference',text='Bob keeps his independent preference',extent='long_term',context=None,
            occurred_at='date unknown')),headers=headers[bob]))
    with host.database.connect(scope_for(ISSUER,alice)) as conn:
        iid,version=conn.execute("SELECT item_id,version FROM cj_memory_item WHERE slot='diet.spicy'").fetchone()
        sources=[r[0] for r in conn.execute('SELECT source_id FROM cj_memory_history_origin WHERE item_id=%s',(iid,)).fetchall()]
        assert len(sources)==1
    owner=scope_for(ISSUER,alice);account=ledger_scope_for(owner,run.current.meter)
    affected=[before['run_id'],uncertain['run_id']]
    def preservation(audit):
        return dict(ledger=audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0],
            chat=audit.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt WHERE scope=%s ORDER BY message_id',(owner,)).fetchall(),
            events=audit.execute('SELECT run_id,sequence,kind,value FROM cj_run_event WHERE scope=%s ORDER BY run_id,sequence',(owner,)).fetchall())
    def copied_inputs(audit):
        return sum(audit.execute(f'SELECT count(*) FROM {table} WHERE scope=%s AND run_id=ANY(%s) AND {column} IS NOT NULL',
            (owner,affected)).fetchone()[0] for table,column in (
                ('cj_run_record','usage_input_bytes'),('cj_run_step_usage','input_bytes'),('cj_run_metered_operation','input_bytes')))
    with psycopg.connect(**json.loads(path.read_text())) as audit:
        retained=preservation(audit);copies=copied_inputs(audit)
        assert copies>0
        assert any(a['state']=='unknown' and a['receipt'] is None for a in retained['ledger']['attempts'].values())
    registry=root/'selected-registry.json'
    stores=[dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),
        dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
        dict(id='business',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in ORDER if t.startswith('business/')])]
    registry.write_bytes(encode(dict(version='controlled-online-memory-component',stores=stores)))
    cleanup=Configuration({'local':b'local-context-component-synthetic-only'},'local',3600,ORDER,registry)
    observations=[]
    class ObserveUnknown:
        def __init__(self,reader):self.reader=reader
        def execute(self,request):
            self.reader.read_original(request);self.reader.read_evidence(request);observations.append(('execute',request.digest))
            return receipt_for(request,'unknown')
        def reconcile(self,request):observations.append(('reconcile',request.digest));return receipt_for(request,'unknown')
    actual=backend_hooks if backend_hooks is not None else (
        lambda store,scope,reader:{t:ObserveUnknown(reader) for t in ('business/message','checkpoints/run','business/usage')})
    options=dict(conninfo_path=path,auth_dir=auth,resolve_collection=resolve,cleanup_configuration=cleanup,resolve_backend_hooks=actual,run_context=run)
    deletion=create_erasure_app_v2(**options,hold_payloads=hold_payloads) if hold_payloads is not None else create_erasure_app(**options)
    raw=encode(dict(version=VERSION,action_id='delete-spicy',item_id=iid,expected_version=version,derived_range='owned_trip_derived_scope'))
    with TestClient(deletion) as client:
        result=ok(client.post('/v1/memory-erasures',content=raw,headers=headers[alice]))['result']
        assert result['stop_use']=='stopped'
        assert result['online_status']==('complete' if expect_complete else 'unknown'),result
        progress=ok(client.get('/v1/memory-erasure-progress',params={'action_id':'delete-spicy'},headers=headers[alice]))['result']
        assert progress['online_status']==result['online_status']
    with psycopg.connect(**json.loads(path.read_text())) as audit:
        assert preservation(audit)==retained
        if expect_complete:
            assert copied_inputs(audit)==0
            assert audit.execute('SELECT input_bytes FROM cj_run_background_job WHERE scope=%s AND run_id=%s',
                (owner,records[0]['run_id'])).fetchone()==(None,)
        else:assert copied_inputs(audit)==copies
    if expect_complete:
        original=jobs.query_original(tokens[alice],records[0]['job_id'],records[0]['attempt_id'])
        assert original['input_state']=='erased' and original['meter_attempt_id']==records[0]['meter_attempt_id']
    with TestClient(app) as client:
        for number,question in enumerate(('What preferences have I saved?','我保存了什么偏好？')):
            send(client,'after-'+str(number),'after-'+str(number),question)
            outcomes=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
            assert all(r.status=='completed' for r in outcomes),outcomes
            assert {i['slot']:i['text'] for i in model.answers[-1]['items']}=={'mobility.fact':'My height is 170 cm'}
        send(client,'bob-context','bob-question','What preferences have I saved?',who=bob)
        outcomes=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
        assert all(r.status=='completed' for r in outcomes),outcomes
        assert [i['text'] for i in model.answers[-1]['items']]==['Bob keeps his independent preference']
    with host.database.connect(scope_for(ISSUER,alice)) as conn:
        selected=conn.execute('SELECT status FROM cj_memory_item WHERE item_id=%s',(iid,)).fetchone()
        assert selected==(None if expect_complete else ('withdrawn',)),selected
        if expect_complete:
            assert conn.execute('SELECT count(*) FROM cj_memory_source WHERE source_id=ANY(%s)',(sources,)).fetchone()==(0,)
            assert conn.execute('SELECT count(*) FROM cj_memory_operation WHERE item_id=%s',(iid,)).fetchone()==(0,)
            assert conn.execute('SELECT count(*) FROM cj_memory_history_origin WHERE item_id=%s',(iid,)).fetchone()==(0,)
            assert conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest').fetchone()==(0,)
        else:
            assert conn.execute('SELECT count(*) FROM cj_memory_source WHERE source_id=ANY(%s) AND active',(sources,)).fetchone()==(0,)
            assert conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest').fetchone()==(1,)
        assert conn.execute("SELECT status FROM cj_memory_item WHERE slot='mobility.fact'").fetchone()==('active',)
    assert len(model.extractions)==1 and len(records)==1
    if not expect_complete:assert [k for k,_ in observations]==['execute']
    with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=config.collection)) as manual:
        ok(manual.post('/v2/memories',content=encode(dict(version='MEMORY-manual.2',operation_id='new-explicit-save',item_id='new-explicit-diet',
            subject='self',slot='diet.spicy',kind='preference',text='A new explicit preference',extent='long_term',context=None,
            occurred_at='date unknown')),headers=headers[alice]))
    with TestClient(app) as client:
        send(client,'new-explicit-context','new-explicit-question','What have I explicitly saved now?')
        outcomes=run_worker.run_once(host.database,model,auth,memory_configuration=config,background_jobs=combined)
        assert all(r.status=='completed' for r in outcomes),outcomes
        assert {i['slot']:i['text'] for i in model.answers[-1]['items']}=={
            'diet.spicy':'A new explicit preference','mobility.fact':'My height is 170 cm'}
    with host.database.connect(owner) as conn:
        fresh=conn.execute("SELECT source_id FROM cj_memory_item WHERE item_id='new-explicit-diet'").fetchone()[0]
        assert fresh not in sources
        assert conn.execute('SELECT status FROM cj_memory_item WHERE item_id=%s',(iid,)).fetchone()==(None if expect_complete else ('withdrawn',))
    assert len(model.extractions)==1 and len(records)==1
    print('PASS actual signed producer/BG2/run_once/unique Meter/Fake -> signed ERASURE1 stop -> actual EN/CN new model contexts omit deleted preference, independent fact/Bob remain; online='+result['online_status']+'; actual B hook composition='+str(expect_complete)+'; complete B physical acceptance is separate')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='erasure-stop-context-') as folder:
        exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
