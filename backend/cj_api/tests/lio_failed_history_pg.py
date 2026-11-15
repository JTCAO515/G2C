"""Fresh signed M2 history, actual Memory, NEEDS and publisher; fixture HTTP only."""
from pathlib import Path
from datetime import datetime,timedelta,timezone,date
from unittest.mock import patch
import json,time,uuid,sys,httpx

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
import lio_exploration_flow_pg as harness
import dev_auth,local_run_context,run_worker
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices,RealTools
from cj_api.local_lio_national import NationalLioPlanning,CONTEXT
from cj_api.lio_planning_grounding import PlanningTurn
from cj_api.local_memory_history import HistoryMemory
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory.typed_api import create_local_typed_app
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_message.lio_context import selected_lio_original_for
from cj_run.core import Binding
from cj_usage.authorization_budget import AuthorizationBudget
from fastapi.testclient import TestClient
from test_lio_planning_flow import flow
from test_lio_city import data as city_catalog

def exercise(root,config):
    auth=root/'auth';conninfo=root/'connection.json';conninfo.write_text(json.dumps(config))
    subject='m4-synthetic-demo-0123456789ab';owner=scope_for(ISSUER,subject)
    dev_auth.init(auth,[subject]);now=int(time.time());meter=auth.parent/'probe-meter.json'
    meter.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,
        period_start=now-60,period_end=now+3600,max_steps=24,max_tools=12,max_output=65536,max_seconds=600),
        output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
    context=load_run_context(meter)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    # Use the accepted Demo bootstrap so historical question_day is genuine.
    from contextlib import contextmanager
    import psycopg
    from deploy.hk import checkpoint,demo_accounts
    from deploy.hk.configuration import Runtime
    control=auth.parent/'control';operations=auth.parent/'operations';operations.mkdir(mode=0o700)
    profile=dict(subjects=['self'],extents=['long_term'],context_ids=[],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)})
    memory=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=dict(
        version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={subject:profile}),
        travel_contexts={subject:[]}),selections={subject:dict(subject='self',slots=['travel.pace'],max_bytes=1000)})).encode())
    runtime=Runtime(auth,context,meter,[],memory_runtime=memory,subjects=frozenset({subject}),demo_subjects=frozenset({subject}))
    runtime._database=database
    @contextmanager
    def operator():
        config=json.loads(conninfo.read_bytes())
        with psycopg.connect(**config,autocommit=True)as db:yield db,config
    from hashlib import sha256
    with patch.object(checkpoint,'operator',operator):
        checkpoint.bootstrap(control,lambda _:None)
        demo_accounts.manage(runtime,'bootstrap',subject,control,operations,
            (sha256(('D1-0123456789ab.'+'x'*22).encode()).hexdigest(),datetime.now(timezone.utc)+timedelta(hours=1)))
        demo_accounts.manage(runtime,'insert',subject,control,operations)
    token=dev_auth.token(auth,subject,300)
    with TestClient(create_local_typed_app(conninfo_path=conninfo,auth_dir=auth,configuration=memory.collection))as api:
        seed=api.post('/v2/memories',headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'},content=json.dumps(dict(
            version='MEMORY-manual.2',operation_id='seed',item_id='pace',subject='self',slot='travel.pace',kind='preference',
            text='I prefer a relaxed pace.',extent='long_term',occurred_at='synthetic',context=None)).encode())
        assert seed.status_code==200,seed.text
    phase=['first'];requests=[]
    def response(request):
        body=json.loads(request.content);system=body['messages'][0]['content'];requests.append((phase[0],system))
        if 'LIO-planning-intake.8'in system:
            if phase[0]=='translation':
                raise httpx.ReadTimeout('synthetic translation UNKNOWN; no candidate bytes',request=request)
            if phase[0]=='after-translation':
                value=flow('请继续规划三天',city='成都',days=3,start='2026-12-10',party=2,intent='plan',questions=(),index=3)
                value.update(version='LIO-planning-intake.8',planning_request_index=3,needs_tools=False)
                value['city'].update(source_index=0,quote='成都')
                value['field_sources']=[dict(field='duration_days',source_index=3,quote='三天'),
                    dict(field='start_date',source_index=2,quote='2026-12-10'),dict(field='party_size',source_index=2,quote='两个人')]
            elif phase[0]=='first':
                value=flow('去成都玩三天',city='成都',days=3,intent='plan',questions=(),index=0)
                value.update(version='LIO-planning-intake.8',planning_request_index=0,needs_tools=False)
                value['field_sources']=[dict(field='duration_days',source_index=0,quote='三天')]
            else:
                assert len([m for m in body['messages'][1:]if m['role']=='user'and m['content'].startswith('Original traveler')])==2
                value=flow('从2026-12-01开始，请继续规划',city='成都',days=3,start='2026-12-01',intent='plan',questions=(),index=1)
                value.update(version='LIO-planning-intake.8',planning_request_index=1,needs_tools=False)
                value['city'].update(source_index=0,quote='成都')
                value['field_sources']=[dict(field='duration_days',source_index=0,quote='三天'),dict(field='start_date',source_index=1,quote='2026-12-01')]
        elif 'The traveler requested a complete 'in system:
            if phase[0]=='after-translation':
                value=dict(answer='第1天逛街区，第2天看博物馆，第3天试当地美食。想先细化哪一天？')
            else:
                assert phase[0]=='first'
                raise httpx.ReadTimeout('one synthetic original discussion UNKNOWN; never retried',request=request)
        elif 'MEMORY-EXTRACT@2'in system:value=dict(version='MEMORY-EXTRACT@2',entries=[])
        else:
            profile=body['response_format']['json_schema']['schema']['properties']['version']['const']
            assert profile=='TRIP-lio-dated-moderate-first.1',profile
            source=json.loads(body['messages'][-1]['content']);assert source['fields']['party_size']['state']!='known'
            value=dict(version=profile,title='成都三天',days=[['2026-12-0'+str(i),
                [[f'sight-{i}-{n}','成都人民公园',a,b,['self']]for n,(a,b)in enumerate((('09:00','10:00'),('10:30','11:30'),('14:00','15:00')))],
                [[f'meal-{i}-{n}','成都餐馆',a,b,['self']]for n,(a,b)in enumerate((('12:00','13:00'),('18:00','19:00')))]]for i in (1,2,3)])
        event=dict(id='probe-'+str(len(requests)),model=M4_MODEL,choices=[dict(index=0,delta=dict(content=json.dumps(value,ensure_ascii=False)),finish_reason='stop')],usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
        return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
    budget=AuthorizationBudget(auth.parent/'probe-financial',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'fixture-no-live-key',max_output_tokens=1536),budget,transport=httpx.MockTransport(response))
    subjects=frozenset({subject});services=RealServices(model,'fixture-no-live-key',subjects,demo_subjects=subjects,national_subjects=subjects)
    tools=RealTools(services,buffered_streaming_subjects=subjects);checker=checker_for(auth)
    boundary=Boundary(checker,lambda p:database.message_repository(scope_for(p.issuer,p.subject)),lambda:str(uuid.uuid4()))
    def worker():return run_worker._worker_for_scope(database,model,auth,owner,checker,memory_configuration=memory,tools_configuration=tools,
        draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,
        lio_confirmation=load_confirmation_signer(auth),lio_memory_enabled=True)
    first=boundary.receive_lio(token,json.dumps(dict(version='LIO-message.2',message_id='old-unknown',text='去成都玩三天',locale='zh',new_conversation=True)).encode(),prepare_scope=database._provision_scope,version='LIO-message.2')
    async def catalogue(key,guard):assert guard()is True;return city_catalog()
    with patch('cj_api.lio_city._catalog_exchange',side_effect=catalogue):
        one=worker();outcome,=one.process();assert outcome.status=='unknown',outcome
    old_receipt=one.messages.query('old-unknown').receipt
    with database.connect(owner)as db:
        old_effects=db.execute("SELECT value FROM cj_run_event WHERE scope=%s AND run_id=%s AND kind='effect_committed' AND value LIKE 'lio_planning_context.1:%%'",(owner,old_receipt.run_id)).fetchall()
    assert any(json.loads(v.split(':',1)[1])['authority']=='plan'for v, in old_effects)
    old_fees=budget.inspect();unknowns=[r for r in old_fees if r['state']!='RECEIVED'];assert len(unknowns)==1
    print('PASS baseline native UNKNOWN retains a committed plan effect and original unknown financial attempt',flush=True)
    second=boundary.receive_lio(token,json.dumps(dict(version='LIO-message.2',message_id='new-plan',text='从2026-12-01开始，请继续规划',locale='zh',conversation_id=first.conversation_id)).encode(),prepare_scope=database._provision_scope,version='LIO-message.2')
    phase[0]='second';history=HistoryMemory.before_model;references_seen=[]
    def record_history(self,binding,original,messages,system,*,message_refs=()):
        references_seen.extend(r['message_id']for r in message_refs)
        return history(self,binding,original,messages,system,message_refs=message_refs)
    with patch('cj_api.lio_city._catalog_exchange',side_effect=catalogue),patch.object(HistoryMemory,'before_model',record_history):
        two=worker();outcome,=two.process();assert outcome.status=='completed',outcome
    assert 'old-unknown'in references_seen
    repository=two.drafts.repository
    with repository.connect()as db:
        rows=db.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s',(repository.scope,)).fetchall()
    assert len(rows)==1 and rows[0][1]==1,rows
    assert one.runs.snapshot(Binding(owner,old_receipt.conversation_id,old_receipt.generation,old_receipt.message_id,old_receipt.run_id,old_receipt.sequence)).status=='unknown'
    assert next(r for r in budget.inspect()if r['attempt_id']==unknowns[0]['attempt_id'])==unknowns[0]
    assert len([s for p,s in requests if p=='first'and'The traveler requested a complete 'in s])==1
    print('PASS genuine failed user bytes -> M2 source_original -> actual Memory history message_refs -> current NEEDS attach -> actual C source/publisher -> one formal Trip v1',flush=True)
    print('PASS no old planning effects inherited; old native UNKNOWN/financial bytes unchanged; no original unknown resend; all HTTP fixtures,0 real service calls',flush=True)
    phase[0]='translation'
    translated=boundary.receive_lio(token,json.dumps(dict(version='LIO-message.2',message_id='unknown-translation',
        text='请翻译“从2026-12-10开始，两个人”',locale='zh',conversation_id=first.conversation_id)).encode(),
        prepare_scope=database._provision_scope,version='LIO-message.2')
    third=worker();outcome,=third.process();assert outcome.status=='unknown',outcome
    phase[0]='after-translation'
    boundary.receive_lio(token,json.dumps(dict(version='LIO-message.2',message_id='after-translation',
        text='请继续规划三天',locale='zh',conversation_id=first.conversation_id)).encode(),
        prepare_scope=database._provision_scope,version='LIO-message.2')
    with patch('cj_api.lio_city._catalog_exchange',side_effect=catalogue):
        fourth=worker();outcome,=fourth.process();assert outcome.status=='completed',outcome
    with repository.connect()as db:
        after=db.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s',(repository.scope,)).fetchall()
    assert after==rows,'translated facts changed the original saved Trip'
    with database.connect(owner)as db:
        context_rows=db.execute("SELECT e.value FROM cj_message_receipt m JOIN cj_run_event e USING(scope,run_id) "
            "WHERE m.scope=%s AND m.message_id=%s AND e.kind='effect_committed' AND e.value LIKE %s ORDER BY e.sequence",
            (owner,'after-translation',CONTEXT+'%')).fetchall()
    contexts=[json.loads(value.removeprefix(CONTEXT))for value, in context_rows]
    assert contexts and all(not {'start_date','party_size'}&set(value.get('facts',{}))for value in contexts)
    assert next(r for r in budget.inspect()if r['attempt_id']==unknowns[0]['attempt_id'])==unknowns[0]
    print('PASS actual UNKNOWN translation original never supplies date/party/cache to the next explicit plan; original Trip/version/content unchanged and old UNKNOWN fee unchanged; 0 real',flush=True)


def main():
    with patch.object(harness,'exercise',exercise):harness.main()


if __name__=='__main__':main()
