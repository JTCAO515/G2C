"""Non-Demo signed M2: a failed or UNKNOWN turn never blocks the next turn (#1025 P1-C).

Outside Demo scopes no receipt carries demo_question_day. The failed original is
unusable DATA: it ends the history window exactly as on main and grants nothing,
and the conversation continues. Fixture HTTP only, 0 real calls.
Run: uv run --locked python -B backend/cj_api/tests/lio_failed_history_nondemo_pg.py
"""
from datetime import datetime,timedelta,timezone
import json,time,uuid
from unittest.mock import patch
import httpx
import local_history_pg as harness
import dev_auth,local_run_context,run_worker
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices,RealTools
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_REAL_OUTPUT_TOKENS
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode
from test_lio_planning_flow import flow


def exercise(root,conninfo,*,failure):
    root.mkdir(mode=0o700);auth=root/'auth';subject='m4-synthetic-nondemo-'+failure
    dev_auth.init(auth,[subject]);owner=scope_for(ISSUER,subject)
    meter=root/'meter.json';now=int(time.time())
    meter.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,
        period_start=now-60,period_end=now+3600,max_steps=8,max_tools=4,max_output=60000,max_seconds=600),
        output_limits=dict(model=12000,tool=24000,memory=2000)),history=[])))
    context=load_run_context(meter)
    local_run_context.provision_budget(conninfo,context,subject);dev_auth.activate_travel(conninfo,subject,context,ABI)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    profile=dict(subjects=['self'],extents=['long_term'],context_ids=[],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)})
    memory=TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',collection=dict(
        version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=expiry,profiles={subject:profile}),
        travel_contexts={subject:[]}),selections={subject:dict(subject='self',slots=['travel.pace'],max_bytes=1000)})))
    checker=checker_for(auth);token=dev_auth.token(auth,subject,120)
    boundary=Boundary(checker,lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    budget=AuthorizationBudget(root/'financial',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc));sent=[]
    def response(request):
        body=json.loads(request.content);sent.append(body)
        if len(sent)==1:
            if failure=='unknown':raise httpx.ReadTimeout('synthetic first-turn UNKNOWN; never retried',request=request)
            return httpx.Response(500,json=dict(error='synthetic definite provider failure'))
        index=body['response_format']['json_schema']['schema']['properties']['current_source_index']['const']
        wire=flow('Synthetic general travel question',city=None,days=None,intent='consult',
            reply='I can help you plan a visit. Which places interest you?',questions=(),index=index)
        wire.update(version='LIO-planning-intake.8',planning_request_index=None,needs_tools=False)
        value=dict(id='chatcmpl-nondemo-'+str(len(sent)),model=M4_MODEL,
            choices=[dict(index=0,delta={'content':json.dumps(wire)},finish_reason='stop')],
            usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
        return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(value)+'\n\ndata: [DONE]\n\n').encode()))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'fixture-key-not-live',max_output_tokens=M4_REAL_OUTPUT_TOKENS),
        budget,transport=httpx.MockTransport(response))
    services=RealServices(model,'fixture-key-not-live',frozenset({subject}),demo_subjects=frozenset({subject}),national_subjects=frozenset({subject}))
    tools=RealTools(services,buffered_streaming_subjects=frozenset({subject}))
    worker=run_worker._worker_for_scope(database,model,auth,owner,checker,memory_configuration=memory,
        tools_configuration=tools,draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,
        lio_confirmation=load_confirmation_signer(auth))
    statuses=[];conversation=None
    for i,text in enumerate(('Could you help me with a travel question?','Please tell me more.','Anything else?')):
        request=dict(version='LIO-message.2',message_id='nondemo-'+failure+'-'+str(i),text=text,locale='en')
        if conversation is None:request['new_conversation']=True
        else:request['conversation_id']=conversation
        receipt=boundary.receive_lio(token,encode(request),prepare_scope=database._provision_scope,version='LIO-message.2')
        conversation=receipt.conversation_id
        statuses+=[o.status for o in worker.process()]
    with database.connect(owner)as db:
        days=db.execute('SELECT demo_question_day FROM cj_message_receipt WHERE scope=%s',(owner,)).fetchall()
    assert all(day is None for day, in days),'fixture must be a non-Demo scope'
    # The provider records a definite HTTP 500 as unknown too; either way the
    # first RUN is a non-completed terminal original.
    assert statuses[0]in('failed','unknown')and statuses[1:]==['completed','completed'],statuses
    print('PASS non-Demo first turn '+failure+'('+statuses[0]+') -> next two turns completed; failed original without its own day ends the window, grants nothing; fixture HTTP only',flush=True)


def main():
    for failure in ('unknown','failed'):
        def run(auth,conninfo):exercise(auth.parent/('nondemo-'+failure),conninfo,failure=failure)
        with patch.object(harness,'exercise',run):harness.main()


if __name__=='__main__':main()
