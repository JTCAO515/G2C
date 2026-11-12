"""L892 local visitor registration + B protected reader, private PG component.

This forces one registered local invocation to verify original provenance; it is
not G.call, a public task execution or a quality/experimental qualification.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import time
from unittest.mock import patch

import local_history_pg as harness
import runtime_weather_fault_pg as fixture
import run_worker
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_REAL_OUTPUT_TOKENS,M4_NATIVE_TURN_BUFFERED
from cj_api.real_services import RealServices,RealTools
from cj_api.lio_city import CityReference
from cj_api.runtime_message_input import lio_input
from cj_api.runtime_run_requests import RunRequests
from cj_api.runtime_originals import RuntimeOriginals
from cj_api.runtime_collector import RuntimeCollector
from cj_api.runtime_model import RuntimeModel
from cj_api.tool_evidence import ToolEvidence
from cj_run.display_snapshot import DisplaySnapshotReader,DisplaySnapshotConfiguration
from cj_usage.authorization_budget import HK_PRODUCER
from runtime_adapter.contract import VERSION,encode,decode,digest
from runtime_adapter.evidence import check_snapshot
from test_m4_real_services import KEY
import httpx


def exercise(auth,database,session,pins,budget,subjects,subject,conninfo):
    claims=session['claims'];boundary=session['boundary'];token=session['token']();scope=claims.binding.scope
    attempt='native-local-visitor-component';prior=[]
    def request(kind,payload):
        return dict(version=VERSION,attempt_id=attempt,step_id='runtime-'+digest([scope,attempt,len(prior)]),
            binding_sha256=claims.binding.key,pins_sha256=pins.key,kind=kind,payload=payload,candidate=pins.value['c0'],prior_step_ids=list(prior))
    setup=request('task_setup',dict(task_id='local-visitor-component',language='en',setup='test-only original registration',dataset_sha256=pins.value['task_sha256']))
    for value in (setup,):
        raw=encode(value);fresh=claims.claim(raw,deadline=time.monotonic()+30);assert fresh.fresh
        claims.consume(raw,fresh.capability,deadline=time.monotonic()+30)
    prior.append(setup['step_id'])
    message=request('message',{'text':'What should a visitor know about payment in Shanghai?'})
    raw=encode(message);fresh=claims.claim(raw,deadline=time.monotonic()+30);assert fresh.fresh
    claims.consume(raw,fresh.capability,deadline=time.monotonic()+30)
    boundary.receive_lio(token,lio_input(scope,message,'en'),prepare_scope=database._provision_scope,version='LIO-message.2')
    stored=boundary.with_history_context(token,lambda context:claims.query(context,message['step_id']))
    calls=[]
    def forbidden(request):calls.append(True);raise AssertionError('local visitor component must not call a model')
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY,max_output_tokens=M4_REAL_OUTPUT_TOKENS),budget,
        transport=httpx.MockTransport(forbidden))
    services=RealServices(model,KEY,frozenset(subjects),demo_subjects=frozenset({subject}),national_subjects=frozenset({subject}))
    catalogue=Path(__file__).resolve().parents[3]/'knowledge/visitor/entries'
    tools=RealTools(services,buffered_streaming_subjects=frozenset({subject}),visitor_catalogue_directory=catalogue)
    routing=RunRequests(claims,boundary,lambda:token,tools,profile='national.2')
    directory=auth.parent/'visitor-evidence';directory.mkdir(mode=0o700)
    manifest=auth.parent/'visitor-evidence-window.json'
    manifest.write_bytes(encode(dict(version='G2C-runtime-evidence-window.4',directory=str(directory),subjects=[subject],
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),source_commit=pins.value['code_sha'],kinds=['tool'])))
    manifest.chmod(0o600);tools.tool_evidence=ToolEvidence.load(manifest,frozenset(subjects),runtime_selection=routing.selects)
    city=CityReference('310000','上海市','上海市','上海市','city','Asia/Shanghai')
    query=encode(dict(version='FACT-query.2',topic='payment',city=city.adcode))
    def one_local(worker,binding,messages,**kwargs):
        value=''.join(worker._registered_stream(binding,'local-visitor-component','tool.visitor_fact',(query,'visitor-original-request',city)))
        result=decode(value);assert result['version']=='FACT-result.2' and result['status']=='matched'
        yield 'Reviewed local visitor guidance was read; this is not live policy.'
    tools.answer=one_local
    worker=run_worker._worker_for_scope(database,model,auth,scope,session['authority'].checker,tools_configuration=tools,
        runtime_registrations_for_run=routing.registrations,runtime_reflection=routing.reflection)
    before=budget.inspect()
    with patch.dict('os.environ',{'CJ_M4_BUDGET_PRODUCER':HK_PRODUCER}),worker.execution_lease():
        outcome=worker._one(stored.receipt)
    assert outcome.status=='completed' and model.calls==0 and calls==[],outcome
    assert budget.inspect()==before
    originals=RuntimeOriginals(boundary,database,budget,directory,query_original=claims.query)
    inventory=decode(originals.inventory(token,message['step_id']));operation,=inventory['operations']
    assert operation['registration_id']=='tool.visitor_fact'
    captured=decode(originals.artifact(token,message['step_id'],operation['operation_id']))
    result=decode(captured['result_utf8'])
    assert len(result['catalogue_sha256'])==64 and result['evaluated_at'] and result['entries']
    display=DisplaySnapshotReader(boundary,lambda principal,owner:database.run_repository(owner),
        configuration=DisplaySnapshotConfiguration(512000,1_048_576))
    refs=auth.parent/'visitor-refs';refs.mkdir(mode=0o700)
    collector=RuntimeCollector(originals,claims,routing,lambda:token,pins,refs,guard=lambda **kwargs:session['authority'].require(
        binding=claims.binding,pins_sha256=pins.key,purpose='query',deadline=time.monotonic()+30,read_only=True),
        state_reader=display.read_travel_events,model_reader=RuntimeModel(originals,model,native_turn_profile=M4_NATIVE_TURN_BUFFERED))
    verified=check_snapshot(collector.inspect(attempt,message['step_id'],deadline=time.monotonic()+30),request=message,
        binding=claims.binding,pins=pins,original=lambda ref:collector.original(ref,deadline=time.monotonic()+30))
    assert verified['status']=='PASS' and verified['operation_checks'][0]['status']=='PASS',verified
    observed,=verified['snapshot']['operations']
    assert observed['provider_state']==observed['fee_state']=='NOT_SENT' and observed['provider'] is observed['fee'] is None
    assert budget.inspect()==before and model.calls==0
    print('PASS L892 actual visitor registration/catalogue bytes -> original PG/Meter visitor-local output hash -> B protected artifact/G NOT_SENT original proof, no financial row/model/vendor call; component only')


if __name__=='__main__':
    def standalone(auth,conninfo):
        with patch.object(fixture,'exercise',exercise):fixture.standalone(auth,conninfo)
    harness.exercise=standalone
    harness.main()
