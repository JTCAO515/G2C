"""Private signed reproduction for the v1 server smoke's Beijing plan."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import time
from unittest.mock import patch
from uuid import uuid4

import lio_projection_pg as projection
import psycopg
from fastapi.testclient import TestClient
from cj_agent.provider import DashScopeConfig, M4_BASE, M4_MODEL, MeteredDashScopeProvider, _M4_REQUEST_SENT
from cj_api.local_app import ISSUER, LocalDatabase, create_local_app, load_confirmation_signer, scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_memory_history import HistoryMemory
from cj_api.real_services import RealServices, RealTools
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory.erasure_fence import References
from cj_memory.runtime import RuntimeDenied
from cj_message.travel import ABI
from cj_usage.authorization_budget import AuthorizationBudget
from cj_run.payload_evidence import key_digest, owner_digest
from runtime_adapter.contract import encode
import dev_auth
import local_run_context
import run_worker
from test_lio_city import data as city_catalog
from test_lio_planning_flow import flow


def exercise(auth, conninfo):
    root = auth.parent
    subject = 'm4-synthetic-demo-999999999999'
    subjects = frozenset({subject})
    dev_auth.init(auth, subjects)
    scope = scope_for(ISSUER, subject)
    now = int(time.time())
    meter_file = root / 'meter.json'
    meter_file.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2', current=dict(meter=dict(
        unit='provider_call', budget=80, period_start=now-60, period_end=now+3600,
        max_steps=12, max_tools=4, max_output=60000, max_seconds=600),
        output_limits=dict(model=12000, tool=4000, memory=12000)), history=[])))
    meter = load_run_context(meter_file)
    local_run_context.provision_budget(conninfo, meter, subject)
    dev_auth.activate_travel(conninfo, subject, meter, ABI)
    with psycopg.connect(**json.loads(conninfo.read_bytes())) as admin:
        assert admin.execute("UPDATE cj_message_scope SET demo_invite_digest=%s,"
                             "demo_invite_expires_at=clock_timestamp()+interval '1 hour',demo_session_floor=0 WHERE scope=%s",
                             (sha256(b'private-plan-fixture').hexdigest(),scope)).rowcount==1
    db = LocalDatabase(conninfo, run_context=meter, travel_context=True, needs_context=True, trip_context=True)
    memory = TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',
        collection=dict(version='local-memory-typed.1', collection=dict(version='local-memory-policy.1',
            expires_at='2099-01-01T00:00:00Z', profiles={subject:dict(subjects=['self'], extents=['long_term'],
                context_ids=[], slots={'travel.pace':dict(kind='preference', collection_allowed=True,
                                                         semantic_resolved=True)})}),
            travel_contexts={subject: []}),
        selections={subject:dict(subject='self', slots=['travel.pace'], max_bytes=1000)})))
    budget = AuthorizationBudget(root / 'financial', clock=lambda:datetime(2026,11,19,tzinfo=timezone.utc))
    model = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, 'local-fixture-not-live'), budget)
    services = RealServices(model, 'local-fixture-not-live', subjects,
                            demo_subjects=subjects, national_subjects=subjects)
    tools = RealTools(services, buffered_streaming_subjects=subjects)
    seen = []

    answer = '第一天去故宫，第二天逛胡同，第三天游颐和园。想先细化哪天？'

    async def fake_wire(config, raw, guard, observation, **kwargs):
        packet=json.loads(raw)
        assert guard() is True
        index=packet.get('response_format',{}).get('json_schema',{}).get('schema',{}).get(
            'properties',{}).get('current_source_index',{}).get('const')
        if index is not None:
            seen.append('intake')
            assert index==0
            assert all('你能做什么' not in row['content'] and '你是谁' not in row['content']
                       for row in packet['messages'])
            value=flow('北京三日游',city='北京',days=3,intent='plan',questions=(),index=index)
            value.update(version='LIO-planning-intake.8',needs_tools=False,
                         field_sources=[dict(field='duration_days',source_index=index,quote='三日')])
        else:
            seen.append('discussion')
            value={'answer':answer}
        yield _M4_REQUEST_SENT
        observation['http_status']=200
        frame=dict(id='legacy-plan-fixture-'+str(len(seen)),model=M4_MODEL,choices=[
            dict(index=0,delta=dict(content=json.dumps(value,ensure_ascii=False)),finish_reason='stop')],
            usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
        yield ('data: '+json.dumps(frame,ensure_ascii=False)+'\n\ndata: [DONE]\n\n').encode()

    async def catalog(key, guard, *, send_under_fence=None):
        def admitted():
            assert guard() is True
        if send_under_fence is None:
            admitted()
        else:
            await send_under_fence(admitted)
        return city_catalog()

    async def no_network(*args, **kwargs):
        raise AssertionError('private fixture attempted an unmocked connection')

    app = create_local_app(conninfo_path=None,auth_dir=auth,database=db,run_context=meter,account_admission=True,
                           demo_dialogue_subjects=subjects,lio_dialogue_subjects=subjects)
    headers = {'Authorization':'Bearer '+dev_auth.token(auth,subject,300),
               'Content-Type':'application/octet-stream'}

    def worker():
        return run_worker.run_once(db,model,auth,memory_configuration_for_scope=lambda _:memory,
            tools_configuration=tools,real_services=services,account_admission=True,
            hk_beta_b_run_credential=True,hk_assembly_scopes=frozenset({scope}),
            hk_assembly_run_credential_scopes=frozenset({scope}),hk_demo_scopes=frozenset({scope}),
            lio_confirmation=load_confirmation_signer(auth))

    rejected = []
    before_model = HistoryMemory.before_model
    def observed_before_model(adapter, *args, **kwargs):
        try:
            return before_model(adapter,*args,**kwargs)
        except RuntimeDenied as error:
            rejected.append(str(error))
            raise

    def send(api, text, *, fresh=False):
        mid=str(uuid4())
        version='LIO-message.2' if fresh else 'LIO-message.1'
        target={'new_conversation':True} if fresh else {}
        received=api.post('/v2/lio/messages' if fresh else '/v1/lio/messages',headers=headers,
            content=encode(dict(version=version,message_id=mid,text=text,locale='zh',**target)))
        assert received.status_code==200,received.status_code
        return mid,received.json()['conversation_id']

    def original(outcome):
        with db.connect(scope) as c:
            events=[row[0] for row in c.execute('SELECT kind FROM cj_run_event WHERE run_id=%s ORDER BY sequence',
                                               (outcome.run_id,)).fetchall()]
            operations=c.execute('SELECT count(*) FROM cj_run_metered_operation WHERE run_id=%s',
                                 (outcome.run_id,)).fetchone()[0]
            ack,=c.execute('SELECT acknowledged FROM cj_message_delivery WHERE run_id=%s',
                          (outcome.run_id,)).fetchone()
        return events,operations,ack

    def metadata_fences():
        # Private initializer only. Represent the same irreversible markers
        # without exercising the production erasure operator or rewriting originals.
        with psycopg.connect(**json.loads(conninfo.read_bytes())) as admin:
            rows=admin.execute('SELECT conversation_id,generation,sequence,message_id,input_sha256,run_id '
                               'FROM cj_message_receipt WHERE scope=%s ORDER BY sequence',(scope,)).fetchall()
            assert len(rows)==32
            for cid,generation,sequence,mid,digest,run_id in rows:
                reference,=References.capture([dict(conversation_id=cid,generation=generation,
                    sequence=sequence,message_id=mid,input_sha256=digest)],[]).messages
                admin.execute("INSERT INTO cj_memory_erasure_fence(scope_digest,kind,reference_sha256) VALUES(%s,'message',%s)",
                              (sha256(scope.encode()).hexdigest(),reference))
                admin.execute("INSERT INTO cj_run_payload_erasure(owner_digest,kind,object_digest,outcome) "
                              "VALUES(%s,'run',%s,'stopped')",(owner_digest(scope),key_digest('run',run_id)))

    with TestClient(app) as api, patch('asyncio.open_connection',new=no_network), patch(
            'cj_agent.provider._m4_wire',new=fake_wire), patch.object(
            HistoryMemory,'before_model',observed_before_model), patch('cj_api.lio_city.catalog_response',new=catalog):
        for text in ('你是谁','你能做什么')*16:
            send(api,text)
            outcome,=worker()
            assert outcome.status=='completed' and original(outcome)==(['started','text_delta','completed'],0,True)
        metadata_fences()
        for text in ('你是谁','你能做什么'):
            send(api,text)
            outcome,=worker()
            assert outcome.status=='completed' and original(outcome)==(['started','text_delta','completed'],0,True)
        mid,old_cid=send(api,'北京三日游')
        with db.connect(scope) as c:
            sequence,day_missing,protocol=c.execute(
                'SELECT sequence,demo_question_day IS NULL,lio_wire_protocol FROM cj_message_receipt WHERE message_id=%s',
                (mid,)).fetchone()
        assert (sequence,day_missing,protocol)==(35,False,None)
        old,=worker()
        assert old.status=='context_invalid' and original(old)==(['started','context_invalid'],0,True)
        assert rejected==['original model history contains erased Memory evidence']
        assert seen==[] and budget.inspect()==[]
        old_timeline=api.get('/v1/lio/timeline',headers=headers)
        assert old_timeline.status_code==200
        failed=next(row for row in old_timeline.json()['messages'] if row['message_id']==mid)
        assert (failed['status'],failed['answer'],failed['trip'])==('failed','',None)
        print('PASS v1 sequence 35: erased original history rejected before any model, tool or fee',flush=True)

        fresh_mid,new_cid=send(api,'北京三日游',fresh=True)
        assert new_cid!=old_cid
        fresh,=worker()
        events,operations,ack=original(fresh)
        assert fresh.status=='completed' and events[-1]=='completed' and operations==3 and ack
        assert seen==['intake','discussion']
        timeline=api.get('/v2/lio/timeline',headers=headers,params={'conversation_id':new_cid})
        assert timeline.status_code==200
        planned,=timeline.json()['messages']
        assert planned['message_id']==fresh_mid and planned['status']=='completed'
        assert answer in planned['answer'] and planned['trip'] is None
        assert [entry['state'] for entry in budget.inspect()]==['RECEIVED']*3
        assert original(old)==(['started','context_invalid'],0,True)
        with db.connect(scope) as c:
            assert c.execute("SELECT count(*) FROM cj_memory_erasure_fence WHERE kind='message'").fetchone()==(32,)
            assert c.execute("SELECT count(*) FROM cj_run_payload_erasure WHERE kind='run'").fetchone()==(32,)
        print('PASS same signed account, explicit fresh v2 conversation reaches the original model and returns a plan',flush=True)


if __name__=='__main__':
    with patch.object(projection.harness,'exercise',exercise):
        projection.harness.main()
