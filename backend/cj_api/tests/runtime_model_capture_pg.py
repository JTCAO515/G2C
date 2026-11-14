"""Native Lio/Typed Memory/registered capture; private signed PG and fixture HTTP."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import base64
import json,time,uuid
import httpx
import local_history_pg as harness
import dev_auth,local_run_context,run_worker
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices,RealTools
from cj_api.tool_evidence import ToolEvidence
from cj_api.runtime_originals import RuntimeOriginals
from cj_api.runtime_surface_inventory import NativeSurfaceInventory
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_REAL_OUTPUT_TOKENS
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode,decode,Unavailable
from test_lio_planning_flow import flow


def exercise(root,conninfo):
    root.mkdir(mode=0o700);auth=root/'auth';subject='m4-synthetic-capture-lease';foreign='m4-synthetic-capture-foreign'
    dev_auth.init(auth,[subject,foreign]);owner=scope_for(ISSUER,subject)
    meter=root/'meter.json';now=int(time.time())
    meter.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,
        period_start=now-60,period_end=now+3600,max_steps=8,max_tools=4,max_output=60000,max_seconds=600),
        output_limits=dict(model=12000,tool=24000,memory=2000)),history=[])))
    context=load_run_context(meter)
    for actor in (subject,foreign):
        local_run_context.provision_budget(conninfo,context,actor);dev_auth.activate_travel(conninfo,actor,context,ABI)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    profile=dict(subjects=['self'],extents=['long_term'],context_ids=[],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)})
    memory=TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',collection=dict(
        version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=expiry,profiles={subject:profile}),
        travel_contexts={subject:[]}),selections={subject:dict(subject='self',slots=['travel.pace'],max_bytes=1000)})))
    checker=checker_for(auth);token=dev_auth.token(auth,subject,120)
    boundary=Boundary(checker,lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    directory=root/'artifacts';directory.mkdir(mode=0o700);manifest=root/'window.json'
    mids=['capture-native-first','capture-native-follow-up']
    manifest.write_bytes(encode(dict(version='G2C-runtime-evidence-window.3',directory=str(directory),
        messages=[dict(subject=subject,message_id=mid)for mid in mids],expires_at=expiry,source_commit='a'*40,kinds=['model','tool'])))
    manifest.chmod(0o600);evidence=ToolEvidence.load(manifest,frozenset({subject}))
    budget=AuthorizationBudget(root/'financial',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc));sent=[]
    def response(request):
        body=json.loads(request.content);sent.append(body)
        index=body['response_format']['json_schema']['schema']['properties']['current_source_index']['const']
        wire=flow('Synthetic general travel question',city=None,days=None,intent='consult',
            reply='I can help you plan a visit. Which places interest you?',questions=(),index=index)
        wire.update(version='LIO-planning-intake.8',planning_request_index=None,needs_tools=False)
        value=dict(id='chatcmpl-capture-'+str(len(sent)),model=M4_MODEL,
            choices=[dict(index=0,delta={'content':json.dumps(wire)},finish_reason='stop')],
            usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
        return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(value)+'\n\ndata: [DONE]\n\n').encode()))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'fixture-key-not-live',max_output_tokens=M4_REAL_OUTPUT_TOKENS),
        budget,transport=httpx.MockTransport(response))
    services=RealServices(model,'fixture-key-not-live',frozenset({subject}),demo_subjects=frozenset({subject}),national_subjects=frozenset({subject}))
    tools=RealTools(services,buffered_streaming_subjects=frozenset({subject}),tool_evidence=evidence)
    worker=run_worker._worker_for_scope(database,model,auth,owner,checker,memory_configuration=memory,
        tools_configuration=tools,draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,
        lio_confirmation=load_confirmation_signer(auth))
    observed_history=[];before_model=worker.history_adapter.before_model
    def observe_history(*args,**kwargs):
        actual=before_model(*args,**kwargs)
        observed_history.append(actual)
        return actual
    worker.history_adapter.before_model=observe_history
    receipts=[]
    for i,mid in enumerate(mids):
        request=dict(version='LIO-message.2',message_id=mid,text='Could you help me with a travel question?'if i==0 else 'Please tell me more.',locale='en')
        if i==0:request['new_conversation']=True
        else:request['conversation_id']=receipts[0].conversation_id
        receipt=boundary.receive_lio(token,encode(request),prepare_scope=database._provision_scope,version='LIO-message.2');receipts.append(receipt)
        assert [o.status for o in worker.process()]==['completed']
    assert len(sent)==model.calls==2 and len(budget.inspect())==2
    assert all(row['state']=='RECEIVED'for row in budget.inspect())
    assert len(observed_history)==2 and len(observed_history[-1].references.messages)==2,'intake9 must retain prior original MESSAGE references'
    originals=RuntimeOriginals(boundary,database,budget,directory,query_original=lambda ctx,mid:ctx.query_lio_message(mid))
    for receipt in receipts:
        inventory=decode(originals.inventory(token,receipt.message_id));operation,=inventory['operations']
        assert operation['registration_id']=='model.lio_intake.9'
        original=decode(originals.artifact(token,receipt.message_id,operation['operation_id']))
        wire=decode(originals.artifact(token,receipt.message_id,operation['operation_id'],wire_input=True))
        assert sha256(original['result_utf8'].encode()).hexdigest()==original['receipt']['output_sha256']
        assert wire['wire_input_sha256']==original['receipt']['input_sha256']
        meter=decode(originals.meter(token,receipt.message_id,operation['operation_id']))
        assert meter['state']=='settled'and meter['receipt']is not None and not meter['cancelled']
        calls_before=model.calls;fees_before=len(budget.inspect())
        surfaces=decode(NativeSurfaceInventory(originals,lambda:token,guard=lambda:None).collect(receipt.message_id))
        assert surfaces['evidence_status']=='COMPLETE'and surfaces['missing']==[]
        raw=[base64.b64decode(s['bytes_base64'])for s in surfaces['surfaces']]
        assert wire['wire_input_utf8'].encode()in raw and original['result_utf8'].encode()in raw
        assert model.calls==calls_before and len(budget.inspect())==fees_before
    assert len(list(directory.glob('*.json')))==4
    foreign_token=dev_auth.token(auth,foreign,30)
    try:originals.visible_original(foreign_token,receipts[0].message_id)
    except Unavailable:pass
    else:raise AssertionError('foreign identity read private visible surfaces')
    (auth/'invited.json').write_text(json.dumps([foreign]))
    try:NativeSurfaceInventory(originals,lambda:token,guard=lambda:None).collect(receipts[0].message_id)
    except Unavailable:pass
    else:raise AssertionError('revoked identity collected cached native surfaces')
    print('PASS private native surface collection, actual input/events/model wire/output, original ACK/terminal, zero new model/fees and foreign/revoke withheld')
    print('PASS native signed Lio2/two same-chat profile9 intakes through actual Typed Memory and registered PG Meter; original Memory reheld for full model capture, both financial RECEIVED/Meter settled, four protected model/wire originals, previous MESSAGE reference retained; fixture HTTP only')


if __name__=='__main__':
    harness.exercise=lambda auth,conninfo:exercise(auth.parent/'native-model-capture',conninfo)
    harness.main()
