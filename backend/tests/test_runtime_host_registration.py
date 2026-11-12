"""Local composition evidence, not runtime admission or live provider evidence."""
from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_api.local_lio_national import intake_prompt
from cj_api.local_worker_context import LocalBudgetRouter
from cj_api.real_services import ModelInput, RealServices, RealTools, TOOL_SYSTEM
from cj_message.lio_context import answer_prompt
from cj_usage.core import Config
from cj_usage.metered_exit import BudgetUnknown
from runtime_adapter.contract import decode,Invalid
from runtime_adapter.profiles import C0, REFLECTION_SYSTEM


@pytest.fixture
def tools():
    # Construction only; any attempted provider use is a test failure.
    def forbidden(*args, **kwargs):
        raise AssertionError('no financial or external operation in preparation')
    finance=SimpleNamespace(begin=forbidden,finish=forbidden)
    provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'local-fixture-key'),finance)
    return RealTools(RealServices(provider,'a'*16,frozenset({'m4-synthetic-runtime'})))


def arguments(tools,locale='en'):
    messages=[dict(role='user',content='去成都玩三天' if locale=='zh' else 'Plan 3 days in Chengdu')]
    turns=[SimpleNamespace(question_day=datetime(2026,11,12,tzinfo=timezone.utc).date())]
    return (messages,intake_prompt(locale,turns),tools.services.model,0)


@pytest.mark.parametrize('locale',['zh','en'])
def test_c0_prepared_bytes_equal_for_actual_answer_and_intake_profiles(tools,locale):
    registry=tools.runtime_registrations(C0)
    native=ModelInput([dict(role='user',content='Hello')],TOOL_SYSTEM+' '+answer_prompt(locale),
                      tools.services.model,{},lio_answer=True,national=True)
    for registration,argument in (('model.answer',native),('model.lio_intake.8',arguments(tools,locale))):
        assert registry[registration].prepare_input(argument).original_bytes==tools.registrations[registration].prepare_input(argument).original_bytes
    assert 'model.runtime_reflection.1' not in tools.registrations


def test_run_candidates_cannot_mutate_each_other_or_authority_fields(tools):
    first={**C0,'prompt.answer_style':'First voice.','tool.lookup.description':'First lookup.'}
    registry=tools.runtime_registrations(first)
    second=tools.runtime_registrations({**C0,'prompt.answer_style':'Second voice.'})
    first['prompt.answer_style']='Changed caller dictionary'
    original=arguments(tools)
    baseline=decode(tools.registrations['model.lio_intake.8'].prepare_input(original).original_bytes)
    actual=decode(registry['model.lio_intake.8'].prepare_input(original).original_bytes)
    assert actual=={**baseline,'system':baseline['system'].replace(C0['prompt.answer_style'],'First voice.',1)}
    assert 'Second voice.' in decode(second['model.lio_intake.8'].prepare_input(original).original_bytes)['system']
    native=ModelInput(original[0],TOOL_SYSTEM,tools.services.model,{},national=True)
    before=decode(tools.registrations['model.tool_turn'].prepare_input(native).original_bytes)
    after=decode(registry['model.tool_turn'].prepare_input(native).original_bytes)
    expected=deepcopy(before)
    search=next(row['function'] for row in expected['native_tools'] if row['function']['name']=='place_search')
    search['description']='First lookup.'
    assert after==expected
    assert tools.national_tools==before['native_tools']


def test_reflection_and_memory_do_not_consume_style_or_native_tools(tools):
    registry=tools.runtime_registrations({**C0,'prompt.answer_style':'Different voice.'})
    payload=dict(candidate=C0,components=['prompt.answer_style'])
    original=decode(registry['model.runtime_reflection.1'].prepare_input(payload).original_bytes)
    assert original['system']==REFLECTION_SYSTEM and original['native_tools'] is None
    argument=([dict(role='user',content='synthetic data')],'Original memory authority.',tools.services.model)
    assert registry['memory.lio_extract.1'].prepare_input(argument).original_bytes==tools.registrations['memory.lio_extract.1'].prepare_input(argument).original_bytes


def test_unsupported_clarification_and_missing_or_duplicate_anchor_fail_before_operation(tools):
    with pytest.raises(BudgetUnknown,match='not connected'):
        tools.runtime_registrations({**C0,'example.clarification':'A new instruction.'})
    registry=tools.runtime_registrations(C0)
    for system in ('Drifted baseline',C0['prompt.answer_style']*2):
        argument=([dict(role='user',content='Hello')],system,tools.services.model,0)
        with pytest.raises(BudgetUnknown,match='baseline changed'):
            registry['model.lio_intake.8'].prepare_input(argument)


def test_each_owned_run_resolves_its_original_registry():
    # RunWorker._one creates an owned worker per receipt with its parent router;
    # _execute resolves that receipt's original RUN. No sticky/global candidate.
    selected=[]
    config=Config('provider_call',20,0,1000,8,8,20000,90)
    profile=SimpleNamespace(meter=config,output_limits=dict(model=16000,tool=2000,memory=1000))
    rows=SimpleNamespace(fetchall=lambda:[])
    connection=SimpleNamespace(execute=lambda *args:rows)
    database=SimpleNamespace(run_context=SimpleNamespace(version='CJ-LOCAL-RUN@2',profiles=[profile],current=profile),
        connect=lambda *args,**kwargs:nullcontext(connection),require_budget_account=lambda *args,**kwargs:None)
    def resolve(binding):
        selected.append(binding)
        return {'selected':binding.run_id}
    router=LocalBudgetRouter(database,registrations_for_run=resolve)
    for run in ('A','B','A'):
        binding=SimpleNamespace(scope='original-synthetic-owner',run_id=run)
        current=router.for_run(binding,SimpleNamespace(events=()))
        assert current.registrations['selected']==run
    assert [binding.run_id for binding in selected]==['A','B','A']


@pytest.mark.parametrize('locale',['zh','en'])
def test_national_v2_three_slot_baseline_is_noop_and_reply_authority_unchanged(tools,locale):
    from cj_api.runtime_text_slots import C0_NATIONAL_V2,REPLY_ANCHOR
    argument=arguments(tools,locale)
    original=tools.registrations['model.lio_intake.8'].prepare_input(argument).original_bytes
    baseline=tools.runtime_registrations(C0_NATIONAL_V2,profile='national.2')
    assert baseline['model.lio_intake.8'].prepare_input(argument).original_bytes==original
    selected={**C0_NATIONAL_V2,'prompt.answer_style':'A different concise style.',
        'example.clarification':'reply briefly and ask one useful optional question'}
    changed=decode(tools.runtime_registrations(selected,profile='national.2')['model.lio_intake.8'].prepare_input(argument).original_bytes)
    before=decode(original)
    expected=before['system'].replace(C0_NATIONAL_V2['prompt.answer_style'],selected['prompt.answer_style'],1).replace(
        REPLY_ANCHOR,selected['example.clarification'],1)
    assert changed=={**before,'system':expected}
    tail='; for plan/save give only a brief acknowledgement or question, no proposed itinerary. Never claim saved/booked/remembered effects.'
    assert tail in before['system'] and tail in changed['system']


def test_national_v2_replaces_original_offsets_without_matching_inserted_candidate_anchors(tools):
    from cj_api.runtime_text_slots import C0_NATIONAL_V2,REPLY_ANCHOR,render_national_intake
    system=arguments(tools)[1]
    selected={**C0_NATIONAL_V2,'prompt.answer_style':'Quoted text: '+REPLY_ANCHOR,
        'example.clarification':'Quoted style: '+C0_NATIONAL_V2['prompt.answer_style']}
    before,remaining=system.split(C0_NATIONAL_V2['prompt.answer_style'])
    middle,after=remaining.split(REPLY_ANCHOR)
    assert render_national_intake(system,selected)==before+selected['prompt.answer_style']+middle+selected['example.clarification']+after
    with pytest.raises(Invalid,match='ANCHOR_DRIFT'):
        render_national_intake(system+REPLY_ANCHOR,C0_NATIONAL_V2)


def test_national_v2_source_and_pins_are_explicit_and_do_not_activate_or_change_old_default():
    from cj_api.runtime_text_slots import C0_NATIONAL_V2,source_c0_national_v2,freeze_national_v2
    from runtime_adapter.configuration import source_c0
    old=source_c0();source=source_c0_national_v2()
    assert source['configuration']=='C0-source-national.2' and source['c0']==C0_NATIONAL_V2
    assert source['activation_status']=='UNRUN' and set(source['slot_host_status'].values())=={'UNRUN'}
    assert source_c0()==old and old['c0']==C0
    card=dict(code_sha='a'*40,image_digest='sha256:'+'b'*64,model=source['model'])
    pinned=freeze_national_v2(card)
    assert pinned.value['c0']==C0_NATIONAL_V2 and pinned.c0()['runtime_eligible'] is False


@pytest.mark.parametrize('locale',['zh','en'])
def test_plain_discussion_answer_consumes_style_only_without_changing_legacy_authority(tools,locale):
    from cj_api.local_lio_planning import DISCUSSION_PROMPT
    from cj_api.runtime_text_slots import C0_NATIONAL_V2
    argument=([dict(role='user',content='Discuss three days in Chengdu')],
        answer_prompt(locale)+DISCUSSION_PROMPT,tools.services.model)
    before=tools.registrations['model.answer'].prepare_input(argument).original_bytes
    baseline=tools.runtime_registrations(C0_NATIONAL_V2,profile='national.2')
    assert baseline['model.answer'].prepare_input(argument).original_bytes==before
    candidate={**C0_NATIONAL_V2,'prompt.answer_style':'Use a different concise style.',
        'example.clarification':'reply with a useful optional question'}
    selected=tools.runtime_registrations(candidate,profile='national.2')
    original=decode(before);actual=decode(selected['model.answer'].prepare_input(argument).original_bytes)
    assert actual=={**original,'system':original['system'].replace(C0['prompt.answer_style'],candidate['prompt.answer_style'],1)}
    assert actual['system'].endswith(DISCUSSION_PROMPT)
    assert selected['model.draft'].prepare_input(argument).original_bytes==tools.registrations['model.draft'].prepare_input(argument).original_bytes
