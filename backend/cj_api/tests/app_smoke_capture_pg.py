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
    print('PASS signed ordinary Home MESSAGE, runtime-role RLS, exact outer/canonical hashes, worker zero-op claim, ACK/producer-return, restart, foreign/JWT/RUN rejection; cloud/model/tool0')


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
