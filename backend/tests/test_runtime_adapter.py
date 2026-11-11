"""Local synthetic contract controls; no live identity, ledger or provider is opened."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from runtime_adapter import Binding, Pins, RuntimeAdapter, Invalid, Unavailable
from runtime_adapter.contract import VERSION, decode, digest, encode, raw_digest
from runtime_adapter.profiles import C0, REFLECTION_SYSTEM, render, reflection_registration
from runtime_adapter.ports import PreparedOriginal

ROOT = Path(__file__).resolve().parents[2]


def pins():
    return Pins.from_dict(dict(version=VERSION, code_sha='a'*40, image_digest='sha256:'+'b'*64,
        adapter_sha256='c'*64, model=dict(endpoint='https://dashscope.aliyuncs.com/compatible-mode/v1',
        id='qwen3.8-flash', parameters={'stream': True, 'enable_thinking': False}),
        system_prompt_sha256='d'*64, tool_schema_sha256='e'*64, tool_implementation_sha256='f'*64,
        c0=C0, task_version='G2C-dialogue-cases.2', task_sha256=raw_digest(
        (ROOT/'eval/optimization/cases.v2.json').read_bytes()), score_version='G2C-dialogue-score.2',
        score_sha256=raw_digest((ROOT/'eval/optimization/score_v2.py').read_bytes()),
        preregistration_sha256='285500035df89e848ef20f9c34fc8f53887b3050cdf7b69e33d818334c7ea91f'))


class LocalBackend:
    """Controlled B seam, explicitly NOT an implementation of live admission."""
    def __init__(self, binding, frozen):
        self.current = binding
        self.frozen = frozen
        self.sent = []
        self.snapshots = {}
        self.proofs = {}
        self.guards = []
        self.lose_ack = False
        self.unavailable = False
        self.unsettled = False
        self.mutate_after_read = False
        self.inspect_count = 0
        self.claims = {}
        self.lose_claim_ack = False
        self.inspected = []

    def binding(self): return self.current
    def pins(self): return self.frozen.raw

    def require(self, **value):
        self.guards.append(value)
        if self.unavailable:
            raise Unavailable('B_WINDOW_OR_SUBLIMIT_NOT_DELIVERED')

    def prepare_task(self, task, language):
        if task['id'] == 'val-owner' and self.unavailable:
            raise Unavailable('NO_LEGAL_SETUP')

    def proof(self, value):
        raw = encode(value)
        ref = 'local-original-' + raw_digest(raw)
        self.proofs[ref] = raw
        return dict(ref=ref, sha256=raw_digest(raw))

    def original(self, reference, *, deadline): return self.proofs[reference]

    def claim(self, raw, *, deadline):
        step = decode(raw)['step_id']
        if step in self.claims:
            return PreparedOriginal(False, None)
        capability = object()
        self.claims[step] = capability
        if self.lose_claim_ack:
            raise TimeoutError('simulated claim ACK loss')
        return PreparedOriginal(True, capability)

    def dispatch(self, raw, *, capability, deadline):
        request = decode(raw)
        assert self.claims[request['step_id']] is capability
        self.sent.append(request)
        sid = request['step_id']
        mid = None if request['kind'] in ('lio_undo_current_trip', 'reflection', 'task_setup') else 'message-'+sid
        run_ids = [] if request['kind'] == 'lio_undo_current_trip' else ['run-'+sid]
        action_id = 'action-'+sid if request['kind'] == 'lio_undo_current_trip' else None
        operations = []
        if request['kind'] in ('message', 'reflection', 'new_conversation_message', 'start_controlled_generation'):
            opid, aid = 'op-'+sid, 'meter-'+sid
            original = self.proof({'actual': request['payload'], 'candidate': request['candidate']})
            if request['kind'] == 'reflection':
                value = {key: 'new text' for key in request['payload']['components']}
            else:
                value = {'actual_reply': 'local synthetic only'}
            output = self.proof(value)
            operations.append(dict(operation_id=opid, attempt_id=aid, run_id=run_ids[0],
                registration_id='model.runtime_reflection.1' if request['kind']=='reflection' else 'model.tool_turn',
                kind='model', input=original, output=output,
                meter=self.proof(dict(attempt_id=aid, operation_id=opid, binding_sha256=self.current.key,
                                      status='SETTLED')),
                provider=None if self.unsettled else self.proof(dict(attempt_id=aid,
                    input_sha256=original['sha256'], response_sha256=output['sha256'])),
                fee=self.proof(dict(attempt_id=aid, ledger_id=self.current.ledger_id,
                                    state='INTENT' if self.unsettled else 'RECEIVED')),
                provider_state='INTENT' if self.unsettled else 'RECEIVED', meter_state='SETTLED',
                fee_state='INTENT' if self.unsettled else 'RECEIVED', model=self.frozen.value['model']))
        status = 'CANCELLED' if request['kind']=='cancel_original_run' else 'PASS'
        if request['kind']=='start_controlled_generation': status='RUNNING'
        if request['kind']=='cancel_original_run':
            for prior in self.snapshots.values():
                if prior['status'] == 'RUNNING': prior['status'] = 'CANCELLED'
        result = operations[-1]['output'] if operations else None
        snapshot = dict(version=VERSION, attempt_id=request['attempt_id'], step_id=sid,
            request_sha256=digest(request), binding_sha256=self.current.key, pins_sha256=self.frozen.key,
            status=status, message_id=mid, run_ids=run_ids, action_id=action_id,
            action=None,
            inventory=self.proof(dict(binding_sha256=self.current.key, client_step_id=sid,
                request_sha256=digest(request), message_id=mid, action_id=action_id, run_ids=run_ids,
                                    operation_ids=[op['operation_id'] for op in operations])),
            operations=operations, result=result, state_evidence=[self.proof({'actual_state': 'local'})])
        self.bind_action(snapshot, request)
        self.snapshots[sid] = snapshot
        if self.lose_ack:
            raise TimeoutError('simulated ACK loss')

    def bind_action(self, snapshot, request):
        snapshot['action'] = self.proof(dict(binding_sha256=self.current.key,
            client_step_id=request['step_id'], request_sha256=digest(request),
            **{key: snapshot[key] for key in ('message_id', 'action_id', 'run_ids',
                                             'inventory', 'result', 'state_evidence')}))

    def inspect(self, attempt_id, step_id, *, deadline):
        self.inspected.append(step_id)
        self.inspect_count += 1
        value = self.snapshots.get(step_id)
        if value is None: return None
        if self.mutate_after_read and self.inspect_count % 2 == 0:
            value = {**value, 'status': 'UNKNOWN'}
        return encode(value)


@pytest.fixture
def local(tmp_path):
    binding = Binding('local-synthetic-owner', 'original-auth-session', 'local-fixture-ledger', 'local-fixture-producer')
    frozen = pins()
    backend = LocalBackend(binding, frozen)
    adapter = RuntimeAdapter(backend, binding, frozen, tmp_path/'mapping')
    return adapter, backend


def call(adapter, aid='task-1', task='dev-airport', language='en'):
    return adapter.call({'id': task, 'language': language}, C0, aid, 30)


def test_normal_task_original_mapping_and_reentry_no_send(local):
    adapter, backend = local
    result = call(adapter)
    assert result['status'] == 'PASS' and result['quality_status'] == 'UNKNOWN'
    assert len(backend.sent) == 2  # existing legal setup + one original message
    before = deepcopy(backend.sent)
    assert call(adapter)['status'] == 'PASS'
    assert backend.sent == before
    assert all(item['attempt_id'] == 'task-1' for item in backend.sent)
    assert all(item['pins_sha256'] == adapter.pins.key for item in backend.sent)


@pytest.mark.parametrize('task,expected', [('dev-local-edit', ['task_setup','message','message']),
    ('val-confirm-save', ['task_setup','message','message','message']),
    ('val-undo', ['task_setup','message','message','lio_undo_current_trip'])])
def test_v2_full_steps_and_native_undo_not_fabricated(local, task, expected):
    adapter, backend = local
    assert call(adapter, task=task)['status'] == 'PASS'
    assert [request['kind'] for request in backend.sent] == expected
    if task == 'val-undo':
        snapshot = backend.snapshots[backend.sent[-1]['step_id']]
        assert snapshot['message_id'] is None and snapshot['run_ids'] == [] and snapshot['action_id']


def test_all_public_languages_preserve_plan_without_expected_observations(tmp_path):
    data = decode((ROOT/'eval/optimization/cases.v2.json').read_bytes())
    for task in data['tasks']:
        for language in ('zh','en'):
            binding = Binding('owner', 'session', 'fixture-ledger', 'fixture-producer')
            frozen = pins(); backend = LocalBackend(binding, frozen)
            adapter = RuntimeAdapter(backend,binding,frozen,tmp_path/(task['id']+language))
            result = call(adapter, task=task['id'], language=language)
            assert result['status'] in ('PASS','UNKNOWN','CANCELLED')
            assert all('behavior' not in request['payload'] and 'state' not in request['payload']
                       for request in backend.sent)


def test_cancel_only_targets_original_no_retry(local):
    adapter, backend = local
    result = call(adapter, task='dev-cancel')
    assert [r['kind'] for r in backend.sent] == ['task_setup','start_controlled_generation','cancel_original_run']
    assert result['status'] in ('UNKNOWN','CANCELLED')
    count = len(backend.sent)
    assert call(adapter, task='dev-cancel')['status'] in ('UNKNOWN','CANCELLED')
    assert len(backend.sent) == count


def test_ack_loss_never_redispatches_even_after_restart(local):
    adapter, backend = local
    backend.lose_ack = True
    assert call(adapter)['status'] == 'UNKNOWN'
    assert len(backend.sent) == 1
    backend.lose_ack = False
    resumed = RuntimeAdapter(backend,adapter.binding,adapter.pins,adapter.store.directory)
    assert call(resumed)['status'] == 'UNKNOWN'  # setup proof alone cannot resume later steps
    assert len(backend.sent) == 1
    assert call(resumed,aid='replacement')['status'] == 'UNRUN'


def test_unknown_not_found_never_means_safe_to_resend(local):
    adapter, backend = local
    assert adapter.query('not-found')['status'] == 'UNKNOWN'
    backend.lose_ack = True
    call(adapter)
    backend.snapshots.clear()
    assert adapter.query('task-1')['status'] == 'UNKNOWN'
    assert call(adapter)['status'] == 'UNKNOWN'
    assert len(backend.sent) == 1


def test_lost_local_mapping_cannot_replay_b_original(local):
    adapter, backend = local
    call(adapter)
    count = len(backend.sent)
    adapter.store.path('task-1').unlink()
    assert call(adapter)['reason'] == 'B_ORIGINAL_ALREADY_EXISTS_QUERY_ONLY'
    assert len(backend.sent) == count
    adapter.store.path('task-1').unlink()
    assert call(adapter,task='dev-required-date')['reason'] == 'B_ORIGINAL_ALREADY_EXISTS_QUERY_ONLY'
    assert len(backend.sent) == count


def test_claim_ack_loss_has_no_dispatch_or_fresh_replacement(local):
    adapter, backend = local
    backend.lose_claim_ack = True
    assert call(adapter)['status'] == 'UNKNOWN'
    assert backend.sent == []
    backend.lose_claim_ack = False
    assert call(adapter)['status'] == 'UNKNOWN'
    assert call(adapter,aid='replacement')['status'] == 'UNRUN'
    assert backend.sent == []


def test_reused_attempt_with_different_input_is_refused(local):
    adapter, _ = local
    call(adapter)
    with pytest.raises(Invalid, match='ORIGINAL_ATTEMPT_INPUT_CHANGED'):
        call(adapter, task='dev-required-date')


def test_unsettled_fee_holds_remain_unknown_no_clear(local):
    adapter, backend = local
    backend.unsettled = True
    assert call(adapter)['status'] == 'UNKNOWN'
    originals = deepcopy(backend.snapshots)
    assert adapter.query('task-1')['status'] == 'UNKNOWN'
    assert backend.snapshots == originals
    assert call(adapter, aid='replacement')['status'] == 'UNRUN'


@pytest.mark.parametrize('mutation', ['scope','pins','inventory','provider','fee','meter','bytes'])
def test_wrong_or_missing_original_evidence_is_unknown(local, mutation):
    adapter, backend = local
    call(adapter)
    snapshot = backend.snapshots[backend.sent[-1]['step_id']]
    op = snapshot['operations'][0]
    if mutation == 'scope': snapshot['binding_sha256'] = 'f'*64
    elif mutation == 'pins': snapshot['pins_sha256'] = 'f'*64
    elif mutation == 'inventory': snapshot['operations'] = []
    elif mutation == 'provider': op['provider'] = backend.proof({'attempt_id':'foreign'})
    elif mutation == 'fee': op['fee'] = backend.proof({'attempt_id':op['attempt_id'],'ledger_id':'other','state':'RECEIVED'})
    elif mutation == 'meter': op['meter'] = backend.proof({'attempt_id':'other'})
    else: backend.proofs[op['input']['ref']] = b'damaged original'
    assert adapter.query('task-1')['status'] == 'UNKNOWN'
    assert len(backend.sent) == 2


def test_original_inventory_race_and_identity_change_stop_read(local):
    adapter, backend = local
    call(adapter)
    backend.mutate_after_read = True
    assert adapter.query('task-1')['status'] == 'UNKNOWN'
    backend.mutate_after_read = False
    backend.current = replace(adapter.binding, auth_session_id='other-session')
    assert adapter.query('task-1')['status'] == 'UNKNOWN'
    assert len(backend.sent) == 2


def test_query_reads_all_started_steps_even_if_one_is_unsettled(local):
    adapter, backend = local
    call(adapter,task='dev-local-edit')
    snapshots=list(backend.snapshots.values())
    snapshots[0]['status']='UNKNOWN'
    backend.inspected.clear()
    assert adapter.query('task-1')['status'] == 'UNKNOWN'
    assert set(backend.inspected) == {request['step_id'] for request in backend.sent}


@pytest.mark.parametrize('failure', ['missing', 'corrupt'])
def test_query_missing_or_invalid_first_step_does_not_hide_later_originals(local, failure):
    adapter, backend = local
    call(adapter, task='dev-local-edit')
    sid = backend.sent[0]['step_id']
    if failure == 'missing': del backend.snapshots[sid]
    else: backend.snapshots[sid]['request_sha256'] = 'f'*64
    backend.inspected.clear()
    result = adapter.query('task-1')
    assert result['status'] == 'UNKNOWN' and len(result['steps']) == 3
    assert set(backend.inspected) == {request['step_id'] for request in backend.sent}


@pytest.mark.parametrize('failure', ['identity', 'revoked'])
def test_query_does_not_release_previous_private_results_after_authority_loss(local, failure):
    adapter, backend = local
    call(adapter, task='dev-local-edit')
    inspect = backend.inspect
    def lose_authority(attempt, step, **kwargs):
        value = inspect(attempt, step, **kwargs)
        if step == backend.sent[-1]['step_id']:
            if failure == 'identity': backend.current = replace(adapter.binding, scope='another-owner')
            else: backend.unavailable = True
        return value
    backend.inspect = lose_authority
    result = adapter.query('task-1')
    assert result['status'] == 'UNKNOWN'
    assert 'steps' not in result and 'result' not in result


def test_same_owner_old_run_cannot_hide_new_original_hold(local):
    adapter, backend = local
    call(adapter, aid='old')
    old = deepcopy(backend.snapshots[backend.sent[-1]['step_id']])
    backend.unsettled = True
    assert call(adapter, aid='new')['status'] == 'UNKNOWN'
    new_request = backend.sent[-1]
    current = backend.snapshots[new_request['step_id']]
    for field in ('run_ids', 'inventory', 'operations', 'result'):
        current[field] = old[field]
    assert adapter.query('new')['status'] == 'UNKNOWN'
    # Even if an action projection accepts the foreign refs, inventory must
    # independently bind the actual original client step/request/message.
    backend.bind_action(current, new_request)
    assert adapter.query('new')['status'] == 'UNKNOWN'
    assert call(adapter, aid='replacement')['status'] == 'UNRUN'


def test_reflection_result_must_be_the_unique_original_provider_output(local):
    adapter, backend = local
    feedback = dict(split='development', dataset_sha256=adapter.pins.value['task_sha256'], rows=[
        dict(task_id='dev-airport', language='en', feedback='public control', evidence=['B-original'])])
    assert adapter.propose(C0, feedback, ['prompt.answer_style'], 'reflect', 30)['status'] == 'PASS'
    request = backend.sent[0]
    current = backend.snapshots[request['step_id']]
    current['result'] = backend.proof({'prompt.answer_style': 'valid text never generated by this provider'})
    backend.bind_action(current, request)
    assert adapter.query('reflect')['status'] == 'UNKNOWN'
    assert len(backend.sent) == 1


def test_model_json_boolean_cannot_be_substituted_with_integer(local):
    adapter, backend = local
    call(adapter)
    op=backend.snapshots[backend.sent[-1]['step_id']]['operations'][0]
    op['model']['parameters']['stream']=1
    assert adapter.query('task-1')['status'] == 'UNKNOWN'


def test_deadline_reached_does_not_start_the_next_step(local):
    adapter, backend = local
    now=[100.0]
    adapter.clock=lambda:now[0]
    original=backend.dispatch
    def finished_after_deadline(raw, **kwargs):
        original(raw,**kwargs)
        now[0]=200.0
    backend.dispatch=finished_after_deadline
    assert call(adapter)['status']=='UNKNOWN'
    assert len(backend.sent)==1


def test_missing_admission_and_runtime_pin_drift_send_nothing(local):
    adapter, backend = local
    backend.unavailable = True
    assert call(adapter)['status'] == 'UNRUN' and backend.sent == []
    backend.unavailable = False
    backend.frozen = Pins.from_dict({**adapter.pins.value,'image_digest':'sha256:'+'e'*64})
    assert call(adapter)['status'] == 'UNRUN' and backend.sent == []


def test_propose_development_only_selected_texts_and_original_receipts(local):
    adapter, backend = local
    feedback = dict(split='development',dataset_sha256=adapter.pins.value['task_sha256'],rows=[
        dict(task_id='dev-airport',language='en',feedback='public control',evidence=['B-original'])])
    result = adapter.propose(C0,feedback,['prompt.answer_style'],'reflect-1',30)
    assert result['status'] == 'PASS' and result['result'] == {'prompt.answer_style':'new text'}
    assert len(backend.sent) == 1 and backend.sent[0]['kind'] == 'reflection'
    assert adapter.propose(C0,feedback,['prompt.answer_style'],'reflect-1',30)['status'] == 'PASS'
    assert len(backend.sent) == 1
    for changed in ({**feedback,'split':'validation'}, {**feedback,'rows':[
        {**feedback['rows'][0],'task_id':'val-undo'}]}):
        with pytest.raises(Invalid): adapter.propose(C0,changed,['prompt.answer_style'],'bad',30)
    with pytest.raises(Invalid): adapter.propose(C0,feedback,['permissions'],'bad',30)


def test_slot_c0_is_actual_source_noop_and_cannot_patch_authority():
    from cj_message.lio_context import PERSONA
    from cj_api.local_lio_planning import DISCUSSION_PROMPT
    from cj_api.real_services import NATIONAL_TOOLS
    assert render(PERSONA,NATIONAL_TOOLS,C0,profile='answer') == (PERSONA,NATIONAL_TOOLS)
    assert render(DISCUSSION_PROMPT,[],C0,profile='discussion') == (DISCUSSION_PROMPT,[])
    modified = {**C0,'prompt.answer_style':'Use brief sentences.'}
    system, tools = render(PERSONA,NATIONAL_TOOLS,modified,profile='answer')
    assert system.replace(modified['prompt.answer_style'],C0['prompt.answer_style']) == PERSONA
    assert tools == NATIONAL_TOOLS
    with pytest.raises(Invalid): render(PERSONA,[],{**C0,'owner':'other'},profile='answer')


def test_c0_source_cannot_mint_live_image_or_authority():
    from runtime_adapter.configuration import source_c0, freeze_pins
    reference=source_c0()
    assert reference['activation_status']=='UNRUN'
    assert 'actual_runtime_image_digest' in reference['required_from_B']
    with pytest.raises(Invalid): freeze_pins(reference)
    material=freeze_pins(dict(code_sha='a'*40,image_digest='sha256:'+'b'*64,model=reference['model']))
    assert material.c0()['runtime_eligible'] is False
    assert material.c0()['fragments']==C0
    assert decode((ROOT/'backend/runtime_adapter/c0.source.json').read_bytes())==reference


def test_reflection_registration_delegates_only_original_model_preparation():
    from types import SimpleNamespace
    captured = []
    model = object()
    class ExistingTools:
        services = SimpleNamespace(model=model)
        def _model_input(self, argument): captured.append(argument); return 'original-input'
    registration = reflection_registration(ExistingTools())
    assert registration.kind == 'model'
    assert registration.prepare_input({'candidate':C0}) == 'original-input'
    messages, system, provider = captured[0]
    assert provider is model and system == REFLECTION_SYSTEM and messages[0]['role'] == 'user'


def test_reflection_through_actual_registered_exit_and_original_provider_code():
    """Existing code composition, with only HTTP/storage controlled locally."""
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import patch
    import httpx
    from backend.usage.tests.test_core import TransactionFake
    from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
    from cj_api.real_services import RealServices, RealTools
    from cj_api.local_app import ISSUER, scope_for
    from cj_run.operation_usage import RegisteredOperation
    from cj_run.usage_binding import UsageBinding
    from cj_run.step_usage import ledger_scope_for
    from cj_usage.core import Config, Command, Meter
    from cj_usage.registered_exit import RegisteredExit, OperationStore
    from cj_usage.metered_exit import BudgetUnknown

    packets=[]
    class OriginalFinanceFixture:
        def __init__(self): self.events=[]
        def clock(self): return datetime(2026,11,11,tzinfo=timezone.utc)
        def check_date(self): pass
        def begin(self,aid,kind,raw): self.events.append(('INTENT',aid,kind))
        def finish(self,aid,metadata): self.events.append(('RECEIVED',aid,metadata['model_id']))
    finance=OriginalFinanceFixture()
    response=encode({'prompt.answer_style':'short clear text'}).decode()
    def http(request):
        packets.append(decode(request.content))
        body=dict(id='local-original-response',model=M4_MODEL,
            choices=[dict(index=0,delta={'content':response},finish_reason='stop')],
            usage=dict(prompt_tokens=10,completion_tokens=5,total_tokens=15))
        return httpx.Response(200,headers={'content-type':'text/event-stream'},
                              stream=httpx.ByteStream(b'data: '+encode(body)+b'\n\ndata: [DONE]\n\n'))
    provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'local-fixture-key'),
                                      finance,transport=httpx.MockTransport(http))
    services=RealServices(provider,'a'*16,frozenset({'m4-synthetic-runtime'}))
    tools=RealTools(services)
    binding=SimpleNamespace(scope=scope_for(ISSUER,'m4-synthetic-runtime'),run_id='original-run')
    config=Config('provider_call',20,0,1000,8,8,20000,90)
    repository=TransactionFake(); repository.scope=ledger_scope_for(binding.scope,config)
    meter=Meter(repository,config,lambda:100)
    exit=RegisteredExit(config,lambda binding,account:meter,clock=lambda:100,
        output_limits=dict(model=16000,tool=2000,memory=1000),environment='local',
        registrations={'model.runtime_reflection.1':reflection_registration(tools)})
    def create(store,bound,key,registration,kind,raw,limit):
        command=Command('original-provider-attempt','original-operation',bound.run_id,kind,raw_digest(raw),1,limit)
        return RegisteredOperation(bound,key,registration,repository.scope,(0,1000),UsageBinding.from_command(command,raw))
    runs=SimpleNamespace(valid=lambda bound:True)
    with patch.object(OperationStore,'create',create):
        prepared=exit.prepare_operation(runs,binding,'model.runtime_reflection.0',
            'model.runtime_reflection.1',{'candidate':C0,'components':['prompt.answer_style']},stage='reflection')
        assert ''.join(exit.stream(prepared))==response
        # The canonical engine refuses an already executed original operation.
        with pytest.raises(BudgetUnknown, match='original prepared call unavailable'):
            list(exit.stream(prepared))
    assert len(packets)==1
    assert packets[0]['model']==M4_MODEL and packets[0]['enable_thinking'] is False
    assert 'tools' not in packets[0] and packets[0]['max_tokens']==1024
    assert [row[1] for row in finance.events]==['original-provider-attempt']*2
    assert meter.query('original-provider-attempt').state=='settled'


def test_corrupt_local_mapping_and_lock_not_accepted(local):
    adapter, backend = local
    call(adapter)
    path = adapter.store.path('task-1')
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"purpose":"call"',b'"purpose":"other"'))
    with pytest.raises(Invalid): adapter.query('task-1')
    path.write_bytes(raw)
    with adapter.store.locked():
        with pytest.raises(Invalid,match='ADAPTER_BUSY'): call(adapter,aid='new')
