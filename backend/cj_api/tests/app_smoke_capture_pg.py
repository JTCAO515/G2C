"""Real signed MESSAGE/runtime-role PG and zero-provider ordinary Home worker.

The temporary allocation database is a local capture fixture, not an HK grant.
No real credentials, cloud configuration or supplier requests are used.
"""
from datetime import datetime, timezone
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
import json
import sys
import time
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]

import httpx
import psycopg
import dev_auth,local_run_context,run_worker
import local_history_pg as harness
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.app_smoke_capture import AppSmokeCapture,CLAIMS
from cj_api.real_services import RealServices,RealTools
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
from cj_auth.interfaces import AdmissionStatus
from cj_message.auth_boundary import Boundary,AccessBlocked
from cj_message.travel import ABI
from cj_run.core import Binding
from cj_strict_json import compact
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.metered_exit import BudgetUnknown
from deploy.tests.test_app_smoke_capture import fixture,write,SUBJECTS,NOW,OriginalBudget


def exercise(auth,conninfo):
    root=auth.parent/'app-smoke';root.mkdir(mode=0o700)
    f=fixture(root)
    subject=SUBJECTS[0];foreign='m4-synthetic-local-foreign'
    subjects=frozenset((*SUBJECTS,foreign));dev_auth.init(auth,subjects)
    now=int(time.time());meter=root/'meter.json'
    meter.write_bytes(compact(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
        unit='provider_call',budget=800,period_start=now-60,period_end=now+3600,
        max_steps=24,max_tools=12,max_output=65536,max_seconds=600),
        output_limits=dict(model=12000,tool=24000,memory=2000)),history=[])))
    context=load_run_context(meter)
    for name in subjects:
        local_run_context.provision_budget(conninfo,context,name)
        dev_auth.activate_travel(conninfo,name,context,ABI)
    # Local operator setup of the real Demo admission precondition; never
    # disable the trigger or substitute a non-Demo owner to evade it.
    with psycopg.connect(**json.loads(conninfo.read_bytes())) as operator:
        for name in SUBJECTS:
            operator.execute("UPDATE cj_message_scope SET demo_invite_digest=%s,"
                "demo_invite_expires_at=clock_timestamp()+interval '1 hour',demo_session_floor=0 WHERE scope=%s",
                (sha256(('fixture-only:'+name).encode()).hexdigest(),scope_for(ISSUER,name)))
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    checker=checker_for(auth);token=dev_auth.token(auth,subject,30)
    boundary=Boundary(checker,lambda p:database.message_repository(scope_for(p.issuer,p.subject)),lambda:str(uuid.uuid4()))
    # The normal Home new-chat wire is accepted by the actual signed boundary.
    # Only its outer digest is stored by the legacy path: do not invent bytes.
    text='你是谁';f.policy['slots'][0]['text_sha256']=sha256(text.encode()).hexdigest()
    f.policy['slots'][1]['text_sha256']=sha256('你能做啥'.encode()).hexdigest()
    write(f.path,f.policy)
    write(f.claims/'claims.json',dict(version=CLAIMS,policy_sha256=sha256(f.path.read_bytes()).hexdigest(),state='ACTIVE',claims=[]))
    local_budget=AuthorizationBudget(root/'financial',clock=lambda:datetime(2026,11,16,tzinfo=timezone.utc))
    sent=[]
    def no_provider(request):
        sent.append(request);raise AssertionError('fixed identity must not call a provider')
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'fixture-only-not-live'),
        local_budget,transport=httpx.MockTransport(no_provider))
    services=RealServices(model,'fixture-only-not-live',subjects,demo_subjects=subjects,national_subjects=subjects)
    tools=RealTools(services,buffered_streaming_subjects=subjects)
    smoke=AppSmokeCapture(f.path,subjects,tools.registrations,database,OriginalBudget(f.budget),clock=lambda:NOW)
    tools.tool_evidence=smoke.evidence
    raw=compact(dict(version='LIO-message.2',message_id=str(uuid.uuid4()),text=text,locale='zh',new_conversation=True))
    receipt=boundary.receive_lio(token,raw,prepare_scope=database._provision_scope,version='LIO-message.2')
    def bound(context):
        stored=context.query_lio_message(receipt.message_id);r=stored.receipt
        return Binding(context.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence),stored
    b,stored=boundary.with_history_context(token,bound)
    worker=run_worker._worker_for_scope(database,model,auth,b.scope,checker,tools_configuration=tools,
        draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,
        lio_confirmation=load_confirmation_signer(auth),runtime_registrations_for_run=smoke.registrations)
    outcomes=worker.process();assert len(outcomes)==1 and outcomes[0].status=='completed'
    smoke.completed(outcomes)
    claim=json.loads((f.claims/'claims.json').read_bytes())['claims'][0]
    assert claim['binding']==asdict(b) and claim['input_sha256']==sha256(raw).hexdigest()
    assert claim['canonical_sha256']==stored.receipt.input_sha256!=claim['input_sha256']
    assert claim['producer_return']['acknowledged']is True and claim['producer_return']['cost_coverage']=='NOT_ASSERTED'
    assert not sent and smoke.selects(b)
    with database.connect(b.scope)as db:
        assert db.execute('SELECT current_user').fetchone()[0]=='cj_m1_runtime'
        assert db.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s',(b.scope,b.run_id)).fetchone()[0]==0
    # A foreign RLS scope cannot read the retained native receipt; a forged
    # binding that keeps the original MID but changes the owner is not admitted.
    with database.connect(scope_for(ISSUER,foreign))as db:
        assert db.execute('SELECT count(*) FROM cj_message_receipt WHERE message_id=%s',(b.message_id,)).fetchone()[0]==0
    changed=replace(b,run_id=str(uuid.uuid4()))
    try:smoke.registrations(changed)
    except BudgetUnknown:pass
    else:raise AssertionError('different native RUN was admitted')
    try:boundary.receive_lio('invalid',raw,prepare_scope=database._provision_scope,version='LIO-message.2')
    except AccessBlocked:pass
    else:raise AssertionError('invalid JWT was admitted')
    again=AppSmokeCapture(f.path,subjects,tools.registrations,database,OriginalBudget(f.budget),clock=lambda:NOW)
    assert again.selects(b) and len(json.loads((f.claims/'claims.json').read_bytes())['claims'])==1
    # An actual ASGI request carries these bytes; an idempotent native accept
    # verifies the same protected original instead of reconstructing its outer.
    import asyncio
    from deploy.hk.app_smoke_outer import OuterControls,OuterCapture,OuterMiddleware,VERSION as OUTER_WINDOW
    from cj_api.runtime_originals import RuntimeOriginals
    from cj_api.app_smoke_originals import SmokeOriginals
    from cj_api.app_smoke_state import SmokeState
    outer_temporary=tempfile.TemporaryDirectory(prefix='g2c-pg-http-',dir='/tmp')
    outer_dir=Path(outer_temporary.name)/'outer';outer_dir.mkdir(mode=0o700)
    api_policy=root/'http-outer-policy.json'
    write(api_policy,dict(version=OUTER_WINDOW,policy_path=str(f.path),policy_sha256=sha256(f.path.read_bytes()).hexdigest(),
        directory=str(outer_dir),directory_device=outer_dir.stat().st_dev,directory_inode=outer_dir.stat().st_ino))
    controls=OuterControls(api_policy,subjects,clock=lambda:NOW)
    # Local attribution table for the already existing fixture journal. No HK
    # policy is activated and the zero-op path creates no paid attempt.
    with local_budget.connect()as journal:
        journal.execute('CREATE TABLE attempt_sublimit(attempt_id TEXT PRIMARY KEY,line TEXT NOT NULL)')
    originals=RuntimeOriginals(boundary,database,local_budget,outer_dir,
        query_original=lambda context,mid:context.query_lio_message(mid))
    observer=OuterCapture(controls,checker,originals,clock=lambda:NOW)
    async def call(body=raw):
        consumed=[];responses=[]
        async def app(scope,receive,send):
            packet=await receive();consumed.append(packet['body'])
            current=boundary.receive_lio(token,packet['body'],prepare_scope=database._provision_scope,version='LIO-message.2')
            assert current.message_id==json.loads(body)['message_id'] and current.input_sha256==sha256(body).hexdigest()
            await send(dict(type='http.response.start',status=200,headers=[]))
            await send(dict(type='http.response.body',body=b'original native ACK',more_body=False))
        async def receive():return dict(type='http.request',body=body,more_body=False)
        async def send(message):responses.append(message)
        await OuterMiddleware(app,observer)(dict(type='http',method='POST',path='/v2/lio/messages',
            headers=[(b'authorization',('Bearer '+token).encode())],query_string=b''),receive,send)
        assert consumed==[body]and responses[-1]['body']==b'original native ACK'
    try:
        asyncio.run(call())
        end=time.monotonic()+5
        while (observer.queue.unfinished_tasks or observer.read_queue.unfinished_tasks)and time.monotonic()<end:time.sleep(.01)
        assert observer.queue.unfinished_tasks==observer.read_queue.unfinished_tasks==0
        from deploy.hk.app_smoke_lifecycle import require_live
        protected=SmokeOriginals(controls,originals,lambda:require_live(controls,observer.lifecycle.instance_id))
        footprint=SmokeState(controls,boundary,database).read(token)
        assert footprint['runtime_role']=='cj_m1_runtime'and footprint['role_flags']==[False]*7
        assert b.message_id in footprint['message_ids']and footprint['pending']==footprint['active']==0
        before=protected.checkpoint()
        financial=protected.accounting(token,b.message_id,before,background_before=footprint['background_rows'],
            background_after=SmokeState(controls,boundary,database).read(token)['background_rows'])
        assert financial['coverage']=='complete'and financial['attempts']==[]and financial['producer_closure_verified']is True
        changed=protected.accounting(token,b.message_id,before,background_before=[],background_after=[['unexpected-job']])
        assert changed['coverage']=='UNKNOWN'and changed['producer_closure_verified']is False
        output=json.loads(protected.outer(token,b.message_id))
        assert output['outer_utf8'].encode()==raw and output['binding']==asdict(b)
        visible=json.loads(protected.message(token,b.message_id))
        assert visible['answer']and visible['input_sha256']==sha256(raw).hexdigest()
        http_before=protected.http_checkpoint(token)
        from cj_api.lio_dialogue_routes import _timeline
        actual_read=_timeline(boundary,lambda scope:database.run_repository(scope),None,None,
            token,b.conversation_id,None,multiple=True).body
        async def call_read(target=b,body=actual_read,path='/v2/lio/timeline'):
            sent=[]
            async def app(scope,receive,send):
                await send(dict(type='http.response.start',status=200,headers=[]))
                await send(dict(type='http.response.body',body=body,more_body=False))
            async def receive():raise AssertionError('no GET body read')
            async def send(message):sent.append(message)
            await OuterMiddleware(app,observer)(dict(type='http',method='GET',path=path,
                query_string=b''if path=='/v1/lio/timeline'else('conversation_id='+target.conversation_id).encode(),
                headers=[(b'authorization',('Bearer '+token).encode())]),receive,send)
            assert sent[-1]['body']==body
        # The actual GET begins before the next checkpoint, but publication
        # deliberately completes after it. Its bytes belong only to the
        # original request fence, never to that later step.
        from threading import Event
        entered=Event();release=Event();publish=observer.publish_read
        def delayed_read(item,claim):
            entered.set()
            if not release.wait(10):raise AssertionError('fixture publication fence not released')
            return publish(item,claim)
        observer.publish_read=delayed_read
        asyncio.run(call_read())
        assert entered.wait(3)
        next_step=protected.http_checkpoint(token)
        release.set()
        end=time.monotonic()+5
        while (observer.queue.unfinished_tasks or observer.read_queue.unfinished_tasks)and time.monotonic()<end:time.sleep(.01)
        assert observer.queue.unfinished_tasks==observer.read_queue.unfinished_tasks==0
        observed=protected.http_observed(token,http_before)
        assert observed['post_count']==0 and len(observed['actual_reads'])==1
        assert observed['actual_reads'][0]['response_utf8'].encode()==actual_read
        assert protected.http_observed(token,next_step)['actual_reads']==[]
        assert observed['read_coverage']=='OBSERVED'and observed['pending_read_exchanges']==[]
        # A terminal native timeline can be returned before the host records
        # run_once-return. Keep that exact HTTP response, without inventing the
        # missing producer witness or waiting at the head of the reader queue.
        raw2=compact(dict(version='LIO-message.2',message_id=str(uuid.uuid4()),text='你能做啥',locale='zh',new_conversation=True))
        receipt2=boundary.receive_lio(token,raw2,prepare_scope=database._provision_scope,version='LIO-message.2')
        def second(context):
            item=context.query_lio_message(receipt2.message_id);r=item.receipt
            return Binding(context.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        b2=boundary.with_history_context(token,second)
        worker2=run_worker._worker_for_scope(database,model,auth,b.scope,checker,tools_configuration=tools,
            draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,
            lio_confirmation=load_confirmation_signer(auth),runtime_registrations_for_run=smoke.registrations)
        outcomes2=worker2.process();assert len(outcomes2)==1 and outcomes2[0].status=='completed'
        assert controls.claim(b2.scope,b2.message_id)['producer_return']is None
        actual_read2=_timeline(boundary,lambda scope:database.run_repository(scope),None,None,
            token,b2.conversation_id,None,multiple=True).body
        point2=protected.http_checkpoint(token)
        asyncio.run(call(raw2))
        assert observer.queue.unfinished_tasks==1
        asyncio.run(call_read(b2,actual_read2))
        end=time.monotonic()+5
        while observer.read_queue.unfinished_tasks and time.monotonic()<end:time.sleep(.01)
        assert observer.read_queue.unfinished_tasks==0 and observer.queue.unfinished_tasks==1
        observed2=protected.http_observed(token,point2)
        assert len(observed2['actual_reads'])==1 and observed2['actual_reads'][0]['response_utf8'].encode()==actual_read2
        assert controls.claim(b2.scope,b2.message_id)['producer_return']is None
        smoke.completed(outcomes2)
        assert controls.claim(b2.scope,b2.message_id)['producer_return']['acknowledged']is True
        end=time.monotonic()+5
        while observer.queue.unfinished_tasks and time.monotonic()<end:time.sleep(.01)
        assert observer.queue.unfinished_tasks==0
        assert json.loads(protected.outer(token,b2.message_id))['outer_utf8'].encode()==raw2
        # The signed App always has a default history row, including no-M
        # empty state. Capture the real v1 GET without manufacturing a claim.
        empty_default=protected.default_history(token,footprint)
        assert empty_default['generation']is None and empty_default['messages']==[]
        body_default=_timeline(boundary,lambda scope:database.run_repository(scope),None,None,
            token,None,None,multiple=False).body
        default_point=protected.http_checkpoint(token)
        asyncio.run(call_read(body=body_default,path='/v1/lio/timeline'))
        end=time.monotonic()+5
        while observer.read_queue.unfinished_tasks and time.monotonic()<end:time.sleep(.01)
        assert observer.read_queue.unfinished_tasks==0
        default_reads=protected.http_observed(token,default_point)['actual_reads']
        assert len(default_reads)==1 and default_reads[0]['origin']=='readonly_default'and default_reads[0]['binding']is None
        assert default_reads[0]['response_utf8'].encode()==body_default
        before_claims=(f.claims/'claims.json').read_bytes()
        default_wire=compact(dict(version='LIO-message.1',message_id=str(uuid.uuid4()),text='你是谁',locale='zh'))
        default_receipt=boundary.receive_lio(token,default_wire,prepare_scope=database._provision_scope,version='LIO-message.1')
        default_worker=run_worker._worker_for_scope(database,model,auth,b.scope,checker,tools_configuration=tools,
            draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,
            lio_confirmation=load_confirmation_signer(auth))
        default_outcomes=default_worker.process();assert len(default_outcomes)==1 and default_outcomes[0].status=='completed'
        original_default=protected.default_history(token,footprint)
        assert original_default['messages'][0]['message_id']==default_receipt.message_id
        body_default=_timeline(boundary,lambda scope:database.run_repository(scope),None,None,
            token,None,None,multiple=False).body
        default_point=protected.http_checkpoint(token)
        asyncio.run(call_read(body=body_default,path='/v1/lio/timeline'))
        end=time.monotonic()+5
        while observer.read_queue.unfinished_tasks and time.monotonic()<end:time.sleep(.01)
        default_reads=protected.http_observed(token,default_point)['actual_reads']
        assert len(default_reads)==1 and default_reads[0]['binding']['message_id']==default_receipt.message_id
        assert(f.claims/'claims.json').read_bytes()==before_claims
        try:originals.input(token,default_receipt.message_id,'any-model-operation')
        except Exception as error:
            from runtime_adapter.contract import Unavailable
            assert type(error)is Unavailable
        else:raise AssertionError('default read exposed a model input without a writer claim')
        try:protected.outer(dev_auth.token(auth,foreign,30),b.message_id)
        except Exception as error:
            from runtime_adapter.contract import Unavailable
            assert type(error)is Unavailable
        else:raise AssertionError('foreign HTTP outer read escaped')
    finally:observer.close();outer_temporary.cleanup()
    # A later window may read genuine old conversations without claiming
    # their model/input artifacts as new-window writes.
    from cj_api.app_smoke_history import export_anchor
    en_token=dev_auth.token(auth,SUBJECTS[1],30)
    en_wire=compact(dict(version='LIO-message.2',message_id=str(uuid.uuid4()),text='Who are you?',locale='en',new_conversation=True))
    en_receipt=boundary.receive_lio(en_token,en_wire,prepare_scope=database._provision_scope,version='LIO-message.2')
    en_worker=run_worker._worker_for_scope(database,model,auth,scope_for(ISSUER,SUBJECTS[1]),checker,tools_configuration=tools,
        draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,
        lio_confirmation=load_confirmation_signer(auth))
    assert en_worker.process()[0].status=='completed'
    zh_anchor=export_anchor(boundary,database,token,b.conversation_id)
    en_anchor=export_anchor(boundary,database,en_token,en_receipt.conversation_id)
    later_root=auth.parent/'later-window';later_root.mkdir(mode=0o700);later=fixture(later_root)
    plan=dict(first_setup=False,old_chats=dict(zh=zh_anchor,en=en_anchor))
    write(later_root/'plan.json',plan)
    from cj_usage.authorization_budget import canonical
    later.policy['plan_sha256']=sha256(canonical(plan)).hexdigest();write(later.path,later.policy)
    write(later.claims/'claims.json',dict(version=CLAIMS,policy_sha256=sha256(later.path.read_bytes()).hexdigest(),state='ACTIVE',claims=[]))
    later_temporary=tempfile.TemporaryDirectory(prefix='g2c-old-http-',dir='/tmp')
    later_outer=Path(later_temporary.name)/'outer';later_outer.mkdir(mode=0o700);later_api=later_root/'api.json'
    write(later_api,dict(version=OUTER_WINDOW,policy_path=str(later.path),policy_sha256=sha256(later.path.read_bytes()).hexdigest(),
        directory=str(later_outer),directory_device=later_outer.stat().st_dev,directory_inode=later_outer.stat().st_ino))
    later_controls=OuterControls(later_api,subjects,clock=lambda:NOW)
    later_native=RuntimeOriginals(boundary,database,local_budget,later_outer,
        query_original=lambda context,mid:context.query_lio_message(mid))
    observer=OuterCapture(later_controls,checker,later_native,clock=lambda:NOW)
    try:
        # API publication and worker-side protected reader are separate native
        # Runtime instances in production. Do not let the test mutate the
        # API's query function when installing the worker's claim-only reader.
        later_reader=RuntimeOriginals(boundary,database,local_budget,later_outer,
            query_original=lambda context,mid:context.query_lio_message(mid))
        protected=SmokeOriginals(later_controls,later_reader,lambda:require_live(later_controls,observer.lifecycle.instance_id))
        before=later.claims.joinpath('claims.json').read_bytes()
        state=SmokeState(later_controls,boundary,database).read(token)
        assert protected.verified_history(token,state)==[zh_anchor]
        point=protected.http_checkpoint(token)
        asyncio.run(call_read())
        end=time.monotonic()+5
        while observer.read_queue.unfinished_tasks and time.monotonic()<end:time.sleep(.01)
        reads=protected.http_observed(token,point)['actual_reads']
        assert len(reads)==1 and reads[0]['origin']=='readonly_history'and reads[0]['binding']==asdict(b)
        assert reads[0]['response_utf8'].encode()==actual_read
        assert later.claims.joinpath('claims.json').read_bytes()==before
        from runtime_adapter.contract import Unavailable
        def claim_only(context):return protected.query(context,b.message_id)
        try:boundary.with_history_context(token,claim_only)
        except Unavailable:pass
        else:raise AssertionError('old readonly history acquired a current-window writer claim')
        try:export_anchor(boundary,database,en_token,b.conversation_id)
        except Unavailable:pass
        else:raise AssertionError('foreign old conversation was exported')
    finally:observer.close();later_temporary.cleanup()
    print('PASS signed ordinary Home MESSAGE, runtime-role RLS, exact outer/canonical hashes, worker zero-op claim, ACK/producer-return, restart, foreign/JWT/RUN rejection; cloud/model/tool0')
    print('PASS actual ASGI HTTP bytes, idempotent native accept, private guarded outer receipt/readback, original answer and foreign denial; no fabricated legacy wire')


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
