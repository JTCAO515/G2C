"""Actual signed Memory/registered model ACK and private rejected-output fixture."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import json,time,uuid,httpx,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import local_history_pg as harness
import dev_auth,local_run_context,run_worker
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices,RealTools
from cj_api.runtime_originals import RuntimeOriginals
from runtime_adapter.contract import Unavailable
from cj_api import rejected_intake_capture as capture_module
from cj_api.rejected_intake_capture import RejectedIntakeSink,use_rejected_intake_sink,IntakeCapture
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_REAL_OUTPUT_TOKENS
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory.typed_api import create_local_typed_app
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_usage.authorization_budget import AuthorizationBudget
from fastapi.testclient import TestClient
from test_lio_planning_flow import flow


def exercise(root,conninfo):
    root.mkdir(mode=0o700);auth=root/'auth';subject='m4-synthetic-rejected-output';owner=scope_for(ISSUER,subject)
    foreign='m4-synthetic-rejected-foreign';dev_auth.init(auth,[subject,foreign]);now=int(time.time());meter=root/'meter.json'
    meter.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,
        period_start=now-60,period_end=now+3600,max_steps=24,max_tools=12,max_output=65536,max_seconds=600),
        output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
    context=load_run_context(meter);local_run_context.provision_budget(conninfo,context,subject)
    dev_auth.activate_travel(conninfo,subject,context,ABI)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    profile=dict(subjects=['self'],extents=['long_term'],context_ids=[],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)})
    memory=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=dict(
        version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=expiry,profiles={subject:profile}),
        travel_contexts={subject:[]}),selections={subject:dict(subject='self',slots=['travel.pace'],max_bytes=1000)})).encode())
    token=dev_auth.token(auth,subject,300);headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    with TestClient(create_local_typed_app(conninfo_path=conninfo,auth_dir=auth,configuration=memory.collection))as api:
        result=api.post('/v2/memories',headers=headers,content=json.dumps(dict(version='MEMORY-manual.2',operation_id='seed',item_id='pace',
            subject='self',slot='travel.pace',kind='preference',text='I prefer a relaxed pace.',extent='long_term',occurred_at='date unknown',context=None)).encode())
        assert result.status_code==200,result.text
    mode=['valid'];sent=[];raws=[]
    text='Could you help me with a travel question?'
    unclear_text='Please plan three days in Beijing starting around Dec 1'
    def response(request):
        body=json.loads(request.content);sent.append(body)
        system=body['messages'][0]['content']
        if 'LIO-planning-intake.8'in system:
            assert any('Stored memory data'in m['content']for m in body['messages'])
            assert capture_module._current.get()is not None
            if mode[0]=='transport':raise httpx.ReadTimeout('injected fixture transport UNKNOWN',request=request)
            value=flow(text,city=None,days=None,intent='consult',questions=(),index=0,
                reply='I can help with a visit. Which places interest you?')
            value.update(version='LIO-planning-intake.8',planning_request_index=None,needs_tools=False)
            if mode[0]=='invalid':value['duration_days']='not-an-integer'
            if mode[0]=='date-clarification':
                value=flow(unclear_text,city='Beijing',days=3,start='2026-12-01',intent='plan',questions=())
                value.update(version='LIO-planning-intake.8')
                value['field_sources']=[dict(field='duration_days',source_index=0,quote='three days'),
                    dict(field='start_date',source_index=0,quote='around Dec 1')]
            raw=json.dumps(value);raws.append(raw.encode())
        else:
            assert capture_module._current.get()is None
            raw=(json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[]))if 'MEMORY-EXTRACT@2'in system else
                'I can help shape the visit. Which places interest you?')
        event=dict(id='fixture-rejection-'+str(len(sent)),model=M4_MODEL,choices=[dict(index=0,delta=dict(content=raw),finish_reason='stop')],
            usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
        return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
    budget=AuthorizationBudget(root/'financial',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'fixture-no-live-key',max_output_tokens=M4_REAL_OUTPUT_TOKENS),
        budget,transport=httpx.MockTransport(response))
    services=RealServices(model,'fixture-no-live-key',frozenset({subject}),demo_subjects=frozenset({subject}),national_subjects=frozenset({subject}))
    tools=RealTools(services,buffered_streaming_subjects=frozenset({subject}))
    checker=checker_for(auth);boundary=Boundary(checker,lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    directory=root/'rejected';directory.mkdir(mode=0o700);sink=RejectedIntakeSink(directory)
    actual_reject=IntakeCapture.reject;captures=[]
    def rejected(capture,code,raw):
        receipt=actual_reject(capture,code,raw)
        assert mode[0]=='invalid'and capture.observed is not None and capture.settled is not None
        captures.append(receipt);observed_operation=capture.observed[0]
        actual_lifetime=capture.read_lifetime()
        current=RuntimeOriginals(boundary,database,budget,directory,query_original=lambda ctx,mid:ctx.query_lio_message(mid),
            rejected_memory_lifetime=actual_lifetime)
        raw_original=current.rejected_intake(token,capture.binding.message_id,observed_operation.command.operation_id,
            receipt.reference,directory=directory)
        assert json.loads(raw_original)['result_utf8'].encode()==raws[-1]==raw
        return receipt
    with use_rejected_intake_sink(sink),patch.object(IntakeCapture,'reject',rejected):
        for name,expected in(('valid','completed'),('invalid','completed'),('date-clarification','completed'),('transport','unknown')):
            mode[0]=name;before=len(sent)
            boundary.receive_lio(token,json.dumps(dict(version='LIO-message.2',message_id='capture-'+name,
                text=unclear_text if name=='date-clarification'else text,locale='en',new_conversation=True)).encode(),
                prepare_scope=database._provision_scope,version='LIO-message.2')
            worker=run_worker._worker_for_scope(database,model,auth,owner,checker,memory_configuration=memory,
                tools_configuration=tools,draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,
                lio_confirmation=load_confirmation_signer(auth),lio_memory_enabled=True)
            outcomes=worker.process();assert[o.status for o in outcomes]==[expected],outcomes
            kinds=['memory'if 'MEMORY-EXTRACT@2'in body['messages'][0]['content']else
                'intake'if 'LIO-planning-intake.8'in body['messages'][0]['content']else'generic'for body in sent[before:]]
            assert kinds==dict(valid=['intake','memory'],invalid=['intake','generic','memory'],
                **{'date-clarification':['intake'],'transport':['intake']})[name],(name,kinds)
    assert len(sent)==model.calls==7 and len(captures)==1 and captures[0].status=='CAPTURED',dict(
        sends=len(sent),model_calls=model.calls,captures=[receipt.status for receipt in captures],
        request_kinds=['memory'if 'MEMORY-EXTRACT@2'in body['messages'][0]['content']else
            'intake'if 'LIO-planning-intake.8'in body['messages'][0]['content']else'generic'for body in sent])
    files=list(directory.iterdir());assert len(files)==1
    stored=json.loads(files[0].read_bytes());assert stored['result_utf8'].encode()==raws[1]
    assert stored['registration_id']=='model.lio_intake.9'and stored['message_id']=='capture-invalid'
    originals=RuntimeOriginals(boundary,database,budget,directory,query_original=lambda ctx,mid:ctx.query_lio_message(mid),rejected_memory_lifetime=None)
    try:originals.rejected_intake(token,'capture-invalid',stored['operation_id'],captures[0].reference,directory=directory)
    except Unavailable:pass
    else:raise AssertionError('historical file reconstructed a Memory permission')
    try:originals.rejected_intake(dev_auth.token(auth,foreign,120),'capture-invalid',stored['operation_id'],captures[0].reference,directory=directory)
    except Unavailable:pass
    else:raise AssertionError('foreign read private rejected output')
    wrong='f'*64 if captures[0].reference!='f'*64 else'e'*64
    try:originals.rejected_intake(token,'capture-invalid',stored['operation_id'],wrong,directory=directory)
    except Unavailable:pass
    else:raise AssertionError('caller substituted private ref')
    no_memory=RuntimeOriginals(boundary,database,budget,directory,query_original=lambda ctx,mid:ctx.query_lio_message(mid))
    try:no_memory.rejected_intake(token,'capture-invalid',stored['operation_id'],captures[0].reference,directory=directory)
    except Unavailable:pass
    else:raise AssertionError('missing current Memory guard accepted old private output')
    with TestClient(create_local_typed_app(conninfo_path=conninfo,auth_dir=auth,configuration=memory.collection))as api:
        paused=api.post('/v2/memory-management-actions',headers=headers,content=json.dumps(dict(version='MEMORY-management.2',
            action_id='pause-captured-memory',operation='pause',item_id='pace',expected_version=1,expected_source_version=1)).encode())
        assert paused.status_code==200,paused.text
    try:originals.rejected_intake(token,'capture-invalid',stored['operation_id'],captures[0].reference,directory=directory)
    except Unavailable:pass
    else:raise AssertionError('paused original Memory allowed private rejected output')
    (auth/'invited.json').write_text(json.dumps([foreign]))
    try:originals.rejected_intake(token,'capture-invalid',stored['operation_id'],captures[0].reference,directory=directory)
    except Unavailable:pass
    else:raise AssertionError('revoked owner read private rejected output')
    rows=budget.inspect();assert len(rows)==7
    assert sum(row['state']=='RECEIVED'for row in rows)==6
    assert files[0].stat().st_mode&0o777==0o600
    print('PASS signed saved Memory + actual model input/native ACK: valid parse/date clarification no file; real schema reject exact private bytes then guarded generic+Memory outside capture; transport UNKNOWN no file/no replay; actual original Memory lifetime positive; historical/missing-holder/pause/config-missing denial; 7 fixture sends/6 RECEIVED/1 UNKNOWN and original financial rows, no live provider',flush=True)


def main():
    with patch.object(harness,'exercise',lambda auth,conninfo:exercise(auth.parent/'rejected-intake-capture',conninfo)):
        harness.main()


if __name__=='__main__':main()
