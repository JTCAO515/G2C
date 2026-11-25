"""Original legacy2 DUT/actor/registered guards in signed private PG.

MockTransport and the TCP denial are fixture-only. The deliberately partial
observer does not certify a profile, Memory injection, end or live baseline.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts'), str(ROOT/'backend/cj_api/tests')]

import httpx
import psycopg
import dev_auth, local_run_context, run_worker
from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_api.local_app import LocalDatabase, ISSUER, scope_for, load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices, RealTools
from cj_api.runtime_actor_source import ActorDutSource
from cj_api.runtime_actor import ActorSpecification
from cj_api.runtime_actor_host import NativeActorHost
from cj_api.runtime_simulator_dut import NativeSimulatorDut
from cj_api.runtime_simulator_requests import SimulatorRunRequests
from cj_api.runtime_simulator_baseline import BaselineDutSpecification as DutSpecification
from cj_api.runtime_simulator_episode import EpisodeLinks, SimulatorActorBridge
from cj_auth.interfaces import AdmissionStatus
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_strict_json import compact
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter import Binding
from runtime_adapter.contract import Unavailable
from eval.lio_simulated_user.core import SIMULATOR_SYSTEM, actor_output_schema, simulator_messages, render_choice, InputError
from eval.lio_simulated_user.runner import HostUnavailable


def exercise(auth, conninfo):
    root = auth.parent/'dut';root.mkdir(mode=0o700)
    subject = 'm4-synthetic-local-c936'
    foreign = 'm4-synthetic-local-c936-foreign'
    subjects = frozenset({subject, foreign})
    dev_auth.init(auth, subjects)
    now = int(time.time());meter = root/'meter.json'
    meter.write_bytes(compact(dict(version='CJ-LOCAL-RUN@2', current=dict(meter=dict(
        unit='provider_call', budget=800, period_start=now-60, period_end=now+3600,
        max_steps=8, max_tools=4, max_output=65536, max_seconds=600),
        output_limits=dict(model=12000, tool=48000, memory=2000)), history=[])))
    context = load_run_context(meter)
    for name in subjects:
        local_run_context.provision_budget(conninfo, context, name)
        dev_auth.activate_travel(conninfo, name, context, ABI)
    database = LocalDatabase(conninfo, run_context=context, travel_context=True, needs_context=True)
    checker = checker_for(auth);token = dev_auth.token(auth, subject, 300)
    current_token = [token];scope = scope_for(ISSUER, subject)
    boundary = Boundary(checker, lambda p: database.message_repository(scope_for(p.issuer, p.subject)), lambda: str(uuid.uuid4()))
    budget = AuthorizationBudget(root/'financial', clock=lambda: datetime(2026,11,14,tzinfo=timezone.utc))
    card = compact(dict(code_sha='a'*40, image_digest='sha256:'+'b'*64, model=dict(
        endpoint=M4_BASE, id=M4_MODEL, parameters=dict(stream=True, stream_options={'include_usage':True},
        enable_thinking=False, max_tokens=1024, response_format={'type':'json_object'}))))
    actor_spec = ActorSpecification((ROOT/'eval/lio_simulated_user/profiles.v1.json').read_bytes(),
        SIMULATOR_SYSTEM, compact(actor_output_schema(),sort_keys=True), card)
    profile = next(p for p in json.loads(actor_spec.dataset)['profiles']
                   if p['locale']=='en' and p['behavior']['direct_after']>1)
    sent = []
    def response(request):
        body = json.loads(request.content);sent.append(body)
        if body['messages'][0]['content'].startswith(SIMULATOR_SYSTEM+'\n'):
            value=dict(answers=['interests'],action='continue')
            event=dict(id='chatcmpl-c936-actor-'+str(len(sent)),model=M4_MODEL,
                choices=[dict(index=0,delta=dict(content=json.dumps(value)),finish_reason='stop')],
                usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
            return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
        if 'response_format' not in body:
            # JT 2026-11-25 B: after intake, a consult message continues to the detailed answer path.
            event=dict(id='chatcmpl-c936-answer-'+str(len(sent)),model=M4_MODEL,
                choices=[dict(index=0,delta=dict(content='I can help you plan a visit. What are your travel interests?'),finish_reason='stop')],
                usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
            return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
        from test_lio_planning_flow import flow
        schema = body['response_format']['json_schema']['schema']
        index = schema['properties']['current_source_index']['const']
        value = flow('Synthetic general travel question', city=None, days=None, intent='consult',
                     reply='I can help you plan a visit. What are your travel interests?', questions=(), index=index)
        value.update(version='LIO-planning-intake.8', planning_request_index=None, needs_tools=False)
        event = dict(id='chatcmpl-c936-'+str(len(sent)), model=M4_MODEL,
            choices=[dict(index=0, delta=dict(content=json.dumps(value)), finish_reason='stop')],
            usage=dict(prompt_tokens=100, completion_tokens=100, total_tokens=200))
        return httpx.Response(200, stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
    model = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, 'fixture-only-not-live'),
        budget, transport=httpx.MockTransport(response))
    tools = RealTools(RealServices(model, 'fixture-only-not-live', subjects,
        demo_subjects=subjects, national_subjects=subjects), buffered_streaming_subjects=subjects)
    worker = run_worker._worker_for_scope(database, model, auth, scope, checker,
        tools_configuration=tools, draft_profile='needs-structured.1', assembly_planning=True,
        demo_planning=True, national_planning=True, lio_confirmation=load_confirmation_signer(auth),
        runtime_registrations_for_run=lambda binding:routing.registrations(binding),
        runtime_reflection=lambda binding:routing.reflection(binding))
    ids = tuple('c936-'+sha256(('local-dut-'+str(n)).encode()).hexdigest() for n in range(3))
    spec = DutSpecification('local-episode', profile['opening'], 'en', ids,
        compact(dict(code_sha='a'*40, image_digest='sha256:'+'b'*64, model=dict(endpoint=M4_BASE, id=M4_MODEL))))
    allowed_keys={spec.key,actor_spec.key}
    class Authority:
        line = 'C'
        token_supplier = staticmethod(lambda:current_token[0])
        def binding(self):
            decision = checker.check(current_token[0])
            if decision.status is not AdmissionStatus.ALLOWED:raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE')
            return Binding(scope_for(decision.principal.issuer, decision.principal.subject),
                sha256(current_token[0].encode()).hexdigest(), budget.ledger_id, budget.producer)
        def require(self, *, binding, pins_sha256, purpose, deadline, read_only):
            assert time.monotonic() < deadline and pins_sha256 in allowed_keys
            if self.binding() != binding:raise Unavailable('ORIGINAL_AUTH_CHANGED')
        def require_current_operation(self, *, binding, pins_sha256, deadline):
            self.require(binding=binding,pins_sha256=pins_sha256,purpose='actor',deadline=deadline,read_only=False)
        def require_operation_clock(self, *, deadline):
            assert time.monotonic()<deadline
    source = ActorDutSource(boundary, database)
    observed = []
    class PartialObserver:
        def read(self, credential, mid, wire):
            def project(raw, check, projection):
                native = json.loads(wire)
                assert projection.page.messages[-1].text == native['text']
                check();observed.append(json.loads(raw))
                return dict(text=projection.history[-1]['text'], run_outcome='completed',
                    exploration_complete=False, questions=[], questions_complete=False,
                    question_evidence='unavailable', profile=None, profile_complete=False,
                    profile_evidence='unavailable', observation_ref=json.loads(raw)['observer_ref'],
                    memory_observation=None)
            return source.observe(credential, mid, project)
    def wait_original(receipt, deadline):
        assert time.monotonic() < deadline
        assert [outcome.status for outcome in worker.process()] == ['completed']
    directory = root/'canonical';directory.mkdir(mode=0o700)
    dut = NativeSimulatorDut(database, boundary, Authority(), spec, lambda: current_token[0],
        directory, wait_original, PartialObserver(), deadline=time.monotonic()+120)
    routing=SimulatorRunRequests(dut,tools)
    first=dut.reply(spec.opening,'en',first=True)
    assert first['run_outcome']=='completed' and not first['profile_complete']
    assert len(sent)==2 and dut.latest==ids[0]  # JT 2026-11-25 B: DUT consult = intake + answer
    actor=NativeActorHost(database,tools,source,actor_spec,Authority(),directory,
        profile_id=profile['id'],attempt=1,dut_message=lambda:dut.latest,deadline=time.monotonic()+120)
    links=EpisodeLinks(directory,actor.owner,actor_spec,guard=actor._guard)
    bridge=SimulatorActorBridge(actor,dut,links,render_choice,InputError,HostUnavailable)
    history=[dict(speaker='user',text=spec.opening),dict(speaker='assistant',text=first['text'])]
    choice=bridge.choose(simulator_messages(profile,history,1))
    text=render_choice(profile,choice,None,1)['text']
    assert dut.pending[0]==text and len(sent)==3  # JT 2026-11-25 B: DUT consult = intake + answer
    second=dut.reply(text,'en',first=False)
    assert second['run_outcome']=='completed' and len(sent)==5  # JT 2026-11-25 B: DUT consult = intake + answer
    assert dut.previous.receipt.conversation_id==dut.conversation_id
    assert all('hidden_answers'not in compact(b).decode() and SIMULATOR_SYSTEM not in compact(b).decode() for b in(sent[0],sent[1],sent[3],sent[4]))
    assert SIMULATOR_SYSTEM in compact(sent[2]).decode()  # JT 2026-11-25 B: DUT consult = intake + answer
    rogue='c936-'+'f'*64
    rogue_wire=compact(dict(version='LIO-message.2',message_id=rogue,text='Synthetic unclaimed guard control',locale='en',new_conversation=True))
    rogue_receipt=boundary.receive_lio(token,rogue_wire,prepare_scope=database._provision_scope,version='LIO-message.2')
    assert [x.status for x in worker.process()]==['unknown']
    assert len(sent)==5  # JT 2026-11-25 B: DUT consult = intake + answer
    with database.connect(scope)as db:
        db.execute('SET TRANSACTION READ ONLY')
        formats=db.execute('SELECT format_version FROM cj_usage_ledger_candidate').fetchall()
        wires=db.execute('SELECT lio_wire_protocol FROM cj_message_receipt WHERE scope=%s AND message_id=ANY(%s) ORDER BY sequence',(scope,list(ids[:2]))).fetchall()
    with database.connect(scope)as db:
        db.execute('SET TRANSACTION READ ONLY')
        assert db.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s',(scope,rogue_receipt.run_id)).fetchone()==(0,)
    assert formats and all(x==(1,)for x in formats),formats
    assert wires==[(None,),(None,)],wires
    print(json.dumps(dict(state='LOCAL_SIGNED_PG_LEGACY2_OPERATION_GUARDS_PASS',source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dut_messages=2,actor_originals=len(actor.originals),fixture_provider_calls=len(sent),live_provider_calls=0,legacy_ledger_formats_unchanged=True,actual_wire='LIO-message.2',claim_version=spec.claim_version,unclaimed_native_message='UNKNOWN_ZERO_OPERATIONS_ZERO_PROVIDER',operation_guards=True,observation='partial_not_qualified',whole_lifecycle_cost='UNRUN',hongkong='UNRUN')))

if __name__=='__main__':
    import subprocess
    if os.environ.get('CJ_ENV')!='local':
        raise SystemExit('CJ_ENV=local required for fixture PG only')
    from eval.runtime import private_database
    from eval.lio_simulated_user.local_controls import no_tcp
    with no_tcp(),private_database('b936baseline')as conninfo:
        exercise(conninfo.parent/'auth',conninfo)
