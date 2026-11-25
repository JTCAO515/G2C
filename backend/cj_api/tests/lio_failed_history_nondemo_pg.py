"""Non-Demo signed M2: a failed or UNKNOWN turn never blocks the next turn (#1025 P1-C).

Outside Demo scopes no receipt carries demo_question_day. An undated failed
original ends the planning evidence window, while a subsequent ordinary answer
can use its text. Fixture HTTP only, 0 real calls.
Run: uv run --locked python -B backend/cj_api/tests/lio_failed_history_nondemo_pg.py
"""
from datetime import datetime,timedelta,timezone
import asyncio
import json,time,uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi.testclient import TestClient
import local_history_pg as harness
import dev_auth,local_run_context,run_worker
from cj_api.local_app import LocalDatabase,ISSUER,create_local_app,scope_for,load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices,RealTools
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_REAL_OUTPUT_TOKENS,ProviderFailed
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode
from test_lio_planning_flow import flow


def exercise(root,conninfo,*,failure,answer_locale=None,followup_text=None):
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
    ordinary={
        'zh':('请规划成都三天行程，多安排安静的公园。','第一次来中国应该怎么玩？','在成都可以先在公园散步。你想从哪个街区开始？'),
        'en':('Plan a three-day trip in Chengdu with quiet parks.','First time in China, any tips?',
              'Start with a quiet park in Chengdu. Which neighborhood interests you?'),
    }
    if followup_text is not None:
        first,_,reply=ordinary[answer_locale]
        ordinary[answer_locale]=first,followup_text,reply
    def response(request):
        body=json.loads(request.content);sent.append(body)
        if len(sent)==1:
            if failure=='unknown':raise httpx.ReadTimeout('synthetic first-turn UNKNOWN; never retried',request=request)
            if answer_locale is not None:raise ProviderFailed('synthetic definite first-turn failure')
            return httpx.Response(500,json=dict(error='synthetic definite provider failure'))
        if answer_locale is not None:
            first,follow,reply=ordinary[answer_locale]
            assert [m['content'] for m in body['messages'] if m['role']=='user'][-2:]==[first,follow], (
                'ordinary response lost earlier traveler text',answer_locale,failure)
            value=dict(id='answer-history-'+answer_locale+'-'+failure,model=M4_MODEL,
                choices=[dict(index=0,delta={'content':reply},finish_reason='stop')],
                usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
            return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(value)+'\n\ndata: [DONE]\n\n').encode()))
        if 'response_format' not in body:
            # JT 2026-11-25 B: after intake, a consult message continues to the detailed answer path.
            value=dict(id='answer-nondemo-'+str(len(sent)),model=M4_MODEL,
                choices=[dict(index=0,delta={'content':'I can help you plan a visit. Which places interest you?'},finish_reason='stop')],
                usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
            return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(value)+'\n\ndata: [DONE]\n\n').encode()))
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
    statuses=[];conversation=None;original_fees=()
    reads=[]
    if answer_locale is not None:
        app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context,
            account_admission=True,demo_dialogue_subjects=frozenset({subject}),lio_dialogue_subjects=frozenset({subject}))

    def signed_timeline():
        with TestClient(app) as api:
            page=api.get('/v2/lio/timeline',headers={'Authorization':'Bearer '+token},
                         params={'conversation_id':conversation})
        assert page.status_code==200,page.status_code
        return page.json()['messages']

    async def connect(host,port,*,server_hostname,**options):
        assert answer_locale is not None and host==server_hostname=='dashscope.aliyuncs.com' and port==443
        assert len(sent)==1
        first,current=await asyncio.to_thread(signed_timeline)
        assert (first['status'],first['answer'],first['text'])==('failed','',ordinary[answer_locale][0])
        assert (current['status'],current['answer'],current['trip'])==('answering','',None)
        reads.append(True)
        reader=asyncio.StreamReader()

        def write(raw):
            headers,_,request=raw.partition(b'\r\n\r\n')
            assert headers.startswith(b'POST /compatible-mode/v1/chat/completions ')
            payload=response(SimpleNamespace(content=request)).read()
            header=('HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                    f'Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n').encode()
            reader.feed_data(header+payload)
            reader.feed_eof()

        return reader,SimpleNamespace(write=write,drain=AsyncMock(),transport=SimpleNamespace(abort=lambda:None))

    turns=ordinary[answer_locale][:2] if answer_locale is not None else (
        'Could you help me with a travel question?','Please tell me more.','Anything else?')
    for i,text in enumerate(turns):
        request=dict(version='LIO-message.2',message_id='nondemo-'+failure+'-'+str(i),text=text,locale=answer_locale or 'en')
        if conversation is None:request['new_conversation']=True
        else:request['conversation_id']=conversation
        receipt=boundary.receive_lio(token,encode(request),prepare_scope=database._provision_scope,version='LIO-message.2')
        conversation=receipt.conversation_id
        if i==1 and answer_locale is not None:
            model.transport=None
        with patch('asyncio.open_connection',new=connect):
            statuses+=[o.status for o in worker.process()]
        if i==0 and answer_locale is not None:
            original_fees=tuple(budget.inspect())
    with database.connect(owner)as db:
        days=db.execute('SELECT demo_question_day FROM cj_message_receipt WHERE scope=%s',(owner,)).fetchall()
    assert all(day is None for day, in days),'fixture must be a non-Demo scope'
    if answer_locale is not None:
        assert statuses==[failure,'completed'],statuses
        assert len(sent)==2 and len(original_fees)==1 and reads==[True]
        assert tuple(budget.inspect()[:1])==original_fees
        before,after=signed_timeline()
        assert before['message_id']=='nondemo-'+failure+'-0'
        assert before['status']=='failed'and not before['answer']
        assert after['message_id']=='nondemo-'+failure+'-1'
        assert after['status']=='completed'and after['answer']==ordinary[answer_locale][2]
        assert before['trip'] is None and after['trip'] is None
        current=worker._binding(worker.messages.query(after['message_id']).receipt)
        draft_inputs=[dict(role='user',content=ordinary[answer_locale][1])]
        draft_history,draft_refs=worker.lio_planning.answer_context(current,draft_inputs)
        assert draft_history==draft_inputs and draft_refs==()
        with database.connect(owner)as db:
            needs=db.execute('SELECT count(*) FROM cj_message_needs_binding').fetchone()[0]
            trips=db.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]
            memories=db.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0]
        assert needs==0 and trips==0 and memories==0
        shape='standalone question'if followup_text is None else 'plain continuation'
        print('PASS visible ordinary follow-up retains '+failure+' text, excludes draft evidence and leaves NEEDS/Trip/Memory unchanged, '+answer_locale+' '+shape,flush=True)
        return
    # The provider records a definite HTTP 500 as unknown too; either way the
    # first RUN is a non-completed terminal original.
    assert statuses[0]in('failed','unknown')and statuses[1:]==['completed','completed'],statuses
    print('PASS non-Demo first turn '+failure+'('+statuses[0]+') -> next two turns completed; failed original without its own day ends the window, grants nothing; fixture HTTP only',flush=True)


def main():
    for failure in ('unknown','failed'):
        def run(auth,conninfo):exercise(auth.parent/('nondemo-'+failure),conninfo,failure=failure)
        with patch.object(harness,'exercise',run):harness.main()
        for locale,followup_text in (('zh',None),('en',None),('zh','继续'),('en','Continue.')):
            def run_answer(auth,conninfo):
                exercise(auth.parent/('answer-'+failure),conninfo,failure=failure,answer_locale=locale,
                    followup_text=followup_text)
            with patch.object(harness,'exercise',run_answer):harness.main()


if __name__=='__main__':main()
