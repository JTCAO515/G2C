"""Native DUT claims/admission/worker in signed private PG; no live calls.

The deliberately partial observer below proves only current public presentation.
It cannot certify accepted profiles, injected Memory or an exploration boundary.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]

import httpx
import dev_auth, local_run_context, run_worker
import local_history_pg as harness
from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_api.local_app import LocalDatabase, ISSUER, scope_for, load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices, RealTools
from cj_api.runtime_actor_source import ActorDutSource
from cj_api.runtime_actor import ActorSpecification
from cj_api.runtime_actor_host import NativeActorHost
from cj_api.runtime_actor_originals import ActorOriginals
from cj_api.runtime_originals import RuntimeOriginals
from cj_api.runtime_simulator_dut import DutSpecification, NativeSimulatorDut
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
        max_steps=12, max_tools=12, max_output=65536, max_seconds=600),
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
        schema = body['response_format']['json_schema']['schema']
        version = schema['properties']['version']['const']
        extra = json.loads(body['messages'][-1]['content'])
        if version == 'LIO-exploration-understanding.1':
            value = dict(version=version, intent='explore', current_source_index=extra['current_source_index'], updates=[])
        elif version == 'LIO-exploration-response.1':
            value = dict(version=version, body='Let us explore your travel ideas.', groups=extra['candidates'])
        else:
            raise AssertionError('unexpected actual DUT profile '+version)
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
        demo_planning=True, national_planning=True, lio_confirmation=load_confirmation_signer(auth))
    ids = tuple('c936-'+sha256(('local-dut-'+str(n)).encode()).hexdigest() for n in range(3))
    spec = DutSpecification('local-episode', profile['opening'], 'en', ids,
        compact(dict(code_sha='a'*40, image_digest='sha256:'+'b'*64, model=dict(endpoint=M4_BASE, id=M4_MODEL))))
    allowed_keys={spec.key,actor_spec.key}
    admission_hook=[None]
    message_guards=[0]
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
            if purpose=='message'and not read_only:
                message_guards[0]+=1
                if admission_hook[0]is not None and admission_hook[0][0]==message_guards[0]:
                    _,callback=admission_hook[0];admission_hook[0]=None;callback()
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
    first = dut.reply(spec.opening, 'en', first=True)
    assert first['run_outcome'] == 'completed' and not first['profile_complete']
    assert len(sent) == 2 and dut.latest == ids[0]
    actor = NativeActorHost(database,tools,source,actor_spec,Authority(),directory,
        profile_id=profile['id'],attempt=1,dut_message=lambda:dut.latest,deadline=time.monotonic()+120)
    links = EpisodeLinks(directory,actor.owner,actor_spec,guard=actor._guard)
    bridge = SimulatorActorBridge(actor,dut,links,render_choice,InputError,HostUnavailable)
    history=[dict(speaker='user',text=spec.opening),dict(speaker='assistant',text=first['text'])]
    choice=bridge.choose(simulator_messages(profile,history,1))
    text=render_choice(profile,choice,None,1)['text'];link=dut.pending[1]
    assert text==profile['hidden_answers']['interests']['text'] and len(sent)==3
    assert actor.originals[0].argument.binding.conversation_id!=dut.conversation_id
    second = dut.reply(text, 'en', first=False)
    assert len(sent) == 5 and not second['questions_complete'] and not second['exploration_complete']
    original = dut.query(ids[1]);assert original.receipt.conversation_id == dut.conversation_id
    assert observed[0]['conversation_id'] == observed[1]['conversation_id']
    assert observed[0]['generation'] == observed[1]['generation']
    assert all('hidden_answers' not in compact(value).decode() for value in (sent[0],sent[1],sent[3],sent[4]))
    artifacts=root/'artifacts';artifacts.mkdir(mode=0o700)
    actor_reader=ActorOriginals(actor,artifacts)
    dut_reader=RuntimeOriginals(boundary,database,budget,artifacts,query_original=lambda c,m:c.query_lio_message(m))
    native_actor_id=actor.originals[0].argument.binding.message_id
    actor_ops=json.loads(actor_reader.inventory(token,native_actor_id))['operations']
    assert len(actor_ops)==1
    dut_ops=[(mid,op)for mid in ids[:2]for op in json.loads(dut_reader.inventory(token,mid))['operations']]
    assert len(dut_ops)==4
    for mid,op in dut_ops:
        assert json.loads(dut_reader.fee(token,mid,op['operation_id']))['state']=='RECEIVED'
    assert json.loads(actor_reader.fee(token,native_actor_id,actor_ops[0]['operation_id']))['state']=='RECEIVED'
    assert len({op['attempt_id']for _,op in dut_ops}|{op['attempt_id']for op in actor_ops})==5
    with database.connect(scope) as db:
        db.execute('SET TRANSACTION READ ONLY')
        assert db.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s', (scope,)).fetchone() == (2,)
        assert db.execute('SELECT count(*) FROM cj_memory_history_job WHERE scope=%s', (scope,)).fetchone() == (0,)
    # A restarted host has no send capability. The original durable claim is
    # query-only, including when a native ACK may have been lost.
    recovered = NativeSimulatorDut(database, boundary, Authority(), spec, lambda: current_token[0],
        directory, wait_original, PartialObserver(), deadline=time.monotonic()+120)
    assert recovered.query(ids[0]) is not None
    try:recovered.reply(spec.opening, 'en', first=True)
    except Unavailable as error:assert str(error) == 'SIMULATOR_DUT_ALREADY_CLAIMED_QUERY_ONLY'
    else:raise AssertionError('recovered DUT resent original')
    assert recovered.stopped and len(sent) == 5
    # The original claim survives a missing admission ACK and cannot be reused.
    dut.release(text, link)
    def lost_ack(receipt, deadline):raise Unavailable('ORIGINAL_WAIT_UNKNOWN')
    dut.wait_original = lost_ack
    try:dut.reply(text, 'en', first=False)
    except Unavailable as error:assert str(error) == 'ORIGINAL_WAIT_UNKNOWN'
    else:raise AssertionError('unknown wait hidden')
    assert dut.stopped and dut.query(ids[2]) is not None and len(sent) == 5
    try:dut.reply(text, 'en', first=False)
    except Unavailable:pass
    else:raise AssertionError('unknown DUT replayed')
    current_token[0] = dev_auth.token(auth, foreign, 300)
    try:dut.query(ids[0])
    except Unavailable:pass
    else:raise AssertionError('changed identity read original')
    assert len(sent) == 5
    current_token[0]=token
    # Complete only the already admitted original from the lost-ACK fixture.
    # This worker reconciliation creates no new MESSAGE or replacement claim.
    assert [outcome.status for outcome in worker.process()]==['completed']
    assert len(sent)==7
    def scenario(name):
        selected=DutSpecification(name,profile['opening'],'en',
            tuple('c936-'+sha256((name+str(n)).encode()).hexdigest()for n in range(2)),spec.runtime_card)
        allowed_keys.add(selected.key)
        return NativeSimulatorDut(database,boundary,Authority(),selected,lambda:current_token[0],
            directory,wait_original,PartialObserver(),deadline=time.monotonic()+120)
    changed_identity=scenario('identity-race')
    admission_hook[0]=(message_guards[0]+2,
        lambda:current_token.__setitem__(0,dev_auth.token(auth,foreign,300)))
    before_calls=len(sent)
    try:changed_identity.reply(profile['opening'],'en',first=True)
    except Unavailable as error:assert str(error)=='SIMULATOR_DUT_ADMISSION_SESSION_CHANGED'
    else:raise AssertionError('post-guard identity change admitted a MESSAGE')
    assert changed_identity.stopped and len(sent)==before_calls
    for owner in(scope,scope_for(ISSUER,foreign)):
        with database.connect(owner)as db:
            db.execute('SET TRANSACTION READ ONLY')
            assert db.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s AND message_id=%s',
                (owner,changed_identity.specification.message_ids[0])).fetchone()==(0,)
    current_token[0]=token
    changed_head=scenario('head-race')
    opening=changed_head.reply(profile['opening'],'en',first=True)
    race_actor=NativeActorHost(database,tools,source,actor_spec,Authority(),directory,
        profile_id=profile['id'],attempt=1,dut_message=lambda:changed_head.latest,deadline=time.monotonic()+120)
    race_bridge=SimulatorActorBridge(race_actor,changed_head,
        EpisodeLinks(directory,race_actor.owner,actor_spec,guard=race_actor._guard),
        render_choice,InputError,HostUnavailable)
    public=[dict(speaker='user',text=profile['opening']),dict(speaker='assistant',text=opening['text'])]
    race_bridge.choose(simulator_messages(profile,public,1))
    continuation=changed_head.pending[0]
    def ordinary_message():
        boundary.receive_lio(token,compact(dict(version='LIO-message.4',message_id='ordinary-interleaved',
            text='I have another question.',locale='en',conversation_id=changed_head.conversation_id)),
            prepare_scope=database._provision_scope,version='LIO-message.4')
    # Insert after the final authority callback, later than claim consumption.
    # Both ordinary admission and the bridge must use the same native M lock.
    admission_hook[0]=(message_guards[0]+2,ordinary_message)
    before_calls=len(sent);before_journal=budget.inspect()
    try:changed_head.reply(continuation,'en',first=False)
    except Unavailable as error:assert str(error)=='SIMULATOR_DUT_ADMISSION_SOURCE_CHANGED'
    else:raise AssertionError('actor text appended after an intervening native message')
    assert changed_head.stopped and changed_head.query(changed_head.specification.message_ids[1])is None
    assert len(sent)==before_calls and budget.inspect()==before_journal
    with database.connect(scope)as db:
        db.execute('SET TRANSACTION READ ONLY')
        assert db.execute('SELECT last_sequence FROM cj_message_chat WHERE scope=%s AND conversation_id=%s AND active',
            (scope,changed_head.conversation_id)).fetchone()==(2,)
    assert len(sent)==10
    print('PASS signed native4 DUT -> original actor RUN -> unchanged C renderer -> next native DUT, same CID/gen, hidden profile only actor, 4 DUT/1 actor distinct original fee attempts; partial observation stays UNKNOWN, restart and lost ACK query-only, cross-identity denied; final-authority identity switch and intervening ordinary MESSAGE both deny new admission/fees under original M; 10 fixture HTTP including explicit original reconciliation and race setup, live0')


if __name__ == '__main__':
    harness.exercise = exercise
    harness.main()
