"""Actual signed Lio/PG/registered exits, fixture model HTTP; no live vendor."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from unittest.mock import patch

import httpx
import local_history_pg as harness

from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_REAL_OUTPUT_TOKENS,M4_NATIVE_TURN_BUFFERED
from cj_api.real_services import RealServices,RealTools
from cj_api.runtime_weather_fault import NativeWeatherFault
from cj_api.runtime_run_requests import RunRequests
from cj_api.runtime_originals import RuntimeOriginals
from cj_api.runtime_collector import RuntimeCollector
from cj_api.runtime_model import RuntimeModel
from cj_api.runtime_message_input import lio_input
from cj_api.tool_evidence import ToolEvidence
from cj_message.lio_context import original_for
from cj_run.core import Binding
from cj_run.display_snapshot import DisplaySnapshotReader,DisplaySnapshotConfiguration
from cj_usage.authorization_budget import HK_PRODUCER
from runtime_adapter.contract import VERSION,decode,digest,encode
from runtime_adapter.evidence import check_snapshot
from test_m4_real_services import KEY
import run_worker


def exercise(auth,database,session,pins,budget,subjects,subject,conninfo):
    boundary=session['boundary'];claims=session['claims'];token=session['token']();scope=session['binding'].scope
    dataset=decode((Path(__file__).resolve().parents[3]/'eval/optimization/cases.v2.json').read_bytes())
    task=next(item for item in dataset['tasks'] if item['id']=='dev-tool-failure')
    attempt='native-weather-fault-control';prior=[]
    def request(kind,payload):
        return dict(version=VERSION,attempt_id=attempt,step_id='runtime-'+digest([scope,attempt,len(prior)]),
            binding_sha256=claims.binding.key,pins_sha256=pins.key,kind=kind,payload=payload,candidate=pins.value['c0'],
            prior_step_ids=list(prior))
    setup=request('task_setup',dict(task_id=task['id'],language='en',setup=task['setup'],dataset_sha256=pins.value['task_sha256']))
    raw=encode(setup);fresh=claims.claim(raw,deadline=time.monotonic()+30);assert fresh.fresh
    claims.consume(raw,fresh.capability,deadline=time.monotonic()+30);prior.append(setup['step_id'])
    message=request('message',{'text':task['variants']['en']['turns'][0]})
    raw=encode(message);fresh=claims.claim(raw,deadline=time.monotonic()+30);assert fresh.fresh
    claims.consume(raw,fresh.capability,deadline=time.monotonic()+30)
    boundary.receive_lio(token,lio_input(scope,message,'en'),prepare_scope=database._provision_scope,version='LIO-message.2')
    stored=boundary.with_history_context(token,lambda context:claims.query(context,message['step_id']))
    receipt=stored.receipt
    binding=Binding(scope,receipt.conversation_id,receipt.generation,receipt.message_id,receipt.run_id,receipt.sequence)
    source=original_for(database,binding);assert source is not None and source.question_day is not None
    day=(source.question_day+timedelta(days=1)).isoformat();http_calls=[]
    def response(request):
        body=json.loads(request.content);http_calls.append(body)
        assert body['max_tokens']==M4_REAL_OUTPUT_TOKENS
        if body['messages'][-1]['role']=='tool':
            actual=json.loads(body['messages'][-1]['content'])['results'][0]['result']
            assert actual['status']=='error' and actual['fault_injected'] and actual['vendor_sent'] is False
            assert actual['query_day']==day
            delta={'content':'The synthetic weather tool failed before any vendor request. I cannot provide a forecast.'}
            finish='stop'
        else:
            delta={'tool_calls':[dict(index=0,id='native_weather_fault_call',type='function',function=dict(
                name='weather',arguments=json.dumps(dict(start_date=day,end_date=day))))]}
            finish='tool_calls'
        event=dict(id='chatcmpl-weather-fault-'+str(len(http_calls)),model=M4_MODEL,
            choices=[dict(index=0,delta=delta,finish_reason=finish)],usage=dict(prompt_tokens=40,completion_tokens=10,total_tokens=50))
        return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY,max_output_tokens=M4_REAL_OUTPUT_TOKENS),
        budget,transport=httpx.MockTransport(response))
    services=RealServices(model,KEY,frozenset(subjects),demo_subjects=frozenset({subject}),national_subjects=frozenset({subject}))
    tools=RealTools(services,buffered_streaming_subjects=frozenset({subject}))
    routing=RunRequests(claims,boundary,lambda:token,tools,profile='national.2')
    directory=auth.parent/'weather-fault-evidence';directory.mkdir(mode=0o700)
    manifest=auth.parent/'weather-fault-evidence.json'
    manifest.write_bytes(encode(dict(version='G2C-runtime-evidence-window.4',directory=str(directory),subjects=[subject],
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),source_commit=pins.value['code_sha'],kinds=['model','tool'])))
    manifest.chmod(0o600)
    tools.tool_evidence=ToolEvidence.load(manifest,frozenset(subjects),runtime_selection=routing.selects)
    fault=NativeWeatherFault(claims,routing,database,budget,directory,pins,lambda:token)
    routing.registry_transformer=fault.wrap
    checker=session['authority'].checker
    worker=run_worker._worker_for_scope(database,model,auth,scope,checker,tools_configuration=tools,
        runtime_registrations_for_run=routing.registrations,runtime_reflection=routing.reflection)
    before=len(budget.inspect());vendor_calls=[]
    async def forbidden_vendor(*args,**kwargs):
        vendor_calls.append(True)
        raise AssertionError('weather fixture attempted an external vendor call')
    with patch.dict('os.environ',{'CJ_M4_BUDGET_PRODUCER':HK_PRODUCER}), \
            patch('cj_fact.live_source._weather_exchange',forbidden_vendor),worker.execution_lease():
        outcome=worker._one(receipt)
    assert vendor_calls==[]
    if outcome.status!='completed':
        with database.connect(scope) as connection:
            operations=connection.execute('SELECT registration_id,kind,input_bytes FROM cj_run_metered_operation WHERE run_id=%s ORDER BY operation_key',(receipt.run_id,)).fetchall()
            events=connection.execute('SELECT kind,value FROM cj_run_event WHERE run_id=%s ORDER BY sequence',(receipt.run_id,)).fetchall()
        print('LOCAL_WEATHER_CONTROL',[(registration,kind,None if kind!='tool' else decode(bytes(raw))) for registration,kind,raw in operations],events,flush=True)
    assert outcome.status=='completed',(outcome,model.calls)
    assert model.calls==len(http_calls)==2 and len(budget.inspect())==before+2
    originals=RuntimeOriginals(boundary,database,budget,directory,query_original=claims.query)
    inventory=decode(originals.inventory(token,receipt.message_id))
    registrations=[op['registration_id'] for op in inventory['operations']]
    assert registrations.count('model.tool_turn')==2 and registrations.count('tool.weather')==1 and len(registrations)==3
    weather=next(op for op in inventory['operations'] if op['registration_id']=='tool.weather')
    actual=decode(originals.artifact(token,receipt.message_id,weather['operation_id']))
    assert actual['version']=='G2C-runtime-weather-fault.1' and actual['original_dispatches']==1 and actual['vendor_sends']==0
    with budget.connect() as journal:
        assert journal.execute('SELECT 1 FROM attempt WHERE id=?',(weather['attempt_id'],)).fetchone() is None
    display=DisplaySnapshotReader(boundary,lambda principal,owner:database.run_repository(owner),
        configuration=DisplaySnapshotConfiguration(512000,1_048_576))
    references=auth.parent/'weather-fault-references';references.mkdir(mode=0o700)
    collector=RuntimeCollector(originals,claims,routing,lambda:token,pins,references,
        guard=lambda **kwargs:session['authority'].require(binding=claims.binding,pins_sha256=pins.key,purpose='query',
            deadline=time.monotonic()+30,read_only=True),state_reader=display.read_travel_events,
        model_reader=RuntimeModel(originals,model,native_turn_profile=M4_NATIVE_TURN_BUFFERED))
    snapshot=collector.inspect(attempt,message['step_id'],deadline=time.monotonic()+30)
    verified=check_snapshot(snapshot,request=message,binding=claims.binding,pins=pins,
        original=lambda ref:collector.original(ref,deadline=time.monotonic()+30))
    assert verified['status']=='PASS' and [op['status'] for op in verified['operation_checks']]==['PASS']*3,verified
    assert len(verified['snapshot']['state_evidence'])==2
    observed_weather=next(op for op in verified['snapshot']['operations'] if op['registration_id']=='tool.weather')
    assert observed_weather['provider_state']=='NOT_SENT'
    assert observed_weather['provider'] is None and observed_weather['fee'] is None
    assert model.calls==2 and len(budget.inspect())==before+2
    print('PASS signed native question day/Beijing tomorrow -> one original registered weather fault dispatch -> real settled Meter and no vendor/financial attempt; two model originals remain in sole journal, G verifies exhaustive output/receipt/NOT_SENT proofs without replay')


def standalone(auth,conninfo):
    import uuid
    import dev_auth
    import local_run_context
    from cj_api.local_app import LocalDatabase,scope_for,ISSUER
    from cj_api.local_run_context import load_run_context
    from cj_api.local_account_admission_v2 import account_checker_for
    from cj_api.runtime_authority import RuntimeAuthority
    from cj_api.runtime_message_claims import MessageClaims
    from cj_api.runtime_text_slots import source_c0_national_v2,freeze_national_v2
    from cj_message.auth_boundary import Boundary
    from cj_message.travel import ABI
    from cj_usage.authorization_budget import AuthorizationBudget,CNY_SCALE
    from cj_usage.sublimits import activate,scope_hash
    subject='m4-synthetic-demo-222233334444'
    dev_auth.init(auth,[subject]);scope=scope_for(ISSUER,subject)
    now=int(time.time());path=auth.parent/'weather-period.json'
    path.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,
        period_start=now-60,period_end=now+3600,max_steps=8,max_tools=4,max_output=60000,max_seconds=600),
        output_limits=dict(model=12000,tool=24000,memory=1000)),history=[])))
    context=load_run_context(path);local_run_context.provision_budget(conninfo,context,subject)
    dev_auth.activate_travel(conninfo,subject,context,ABI)
    import psycopg
    # Initial private-fixture qualification only, before any task MESSAGE.
    # The existing M52 producer stamps the original Beijing question day.
    with psycopg.connect(**json.loads(conninfo.read_bytes())) as operator:
        operator.execute("UPDATE cj_message_scope SET demo_invite_digest=%s,demo_invite_expires_at=clock_timestamp()+interval '1 hour',demo_session_floor=0 WHERE scope=%s",
            ('b'*64,scope))
    database=LocalDatabase(conninfo,run_context=context,travel_context=True)
    checker=account_checker_for(auth,database);token=dev_auth.token(auth,subject,30)
    boundary=Boundary(checker,lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    budget=AuthorizationBudget(auth.parent/'weather-financial',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc))
    budget.begin('retained-weather-local-control','model',b'pre-allocation fixture')
    base=dict(cap=None,active_cap=None,model_cap=None,tool_cap=None,max_calls=None,model_calls=None,tool_calls=None)
    grants={line:dict(base) for line in ('A','B','L','C','E','F')}
    for line in ('L','C','E','F'):grants[line].update(cap=50*CNY_SCALE,active_cap=50*CNY_SCALE)
    activate(budget,grants,{scope_hash(scope):'E'})
    source=source_c0_national_v2()
    pins=freeze_national_v2(dict(code_sha='a'*40,image_digest='sha256:'+'a'*64,model=source['model']))
    authority=RuntimeAuthority(checker,lambda:token,budget,pins,lambda:pins.raw,line='E',
        wall_clock=lambda:datetime(2026,11,12,13,5,tzinfo=timezone.utc))
    directory=auth.parent/'weather-canonical';directory.mkdir(mode=0o700)
    claims=MessageClaims(directory,boundary,lambda:token,authority,pins,history_profile='lio.2')
    session=dict(boundary=boundary,claims=claims,authority=authority,binding=claims.binding,token=lambda:token)
    exercise(auth,database,session,pins,budget,[subject],subject,conninfo)


if __name__=='__main__':
    harness.exercise=standalone
    harness.main()
