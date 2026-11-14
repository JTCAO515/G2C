"""Actual provider/logical-wire observation retains strict runtime pin equality."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from cj_agent.provider import DashScopeConfig,M4_BASE,M4_MODEL,M4_NATIVE_TURN_BUFFERED
from cj_api.runtime_model import RuntimeModel,configured_model
from cj_api.runtime_text_slots import source_c0_national_v2,freeze_national_v2
from cj_draft.grouped_plan import GENERATION_PROFILES
from cj_draft.rich_schema import GENERATION_PROFILES as RICH
from runtime_adapter.contract import encode,Unavailable,Invalid

ROOT=Path(__file__).resolve().parents[2]


def provider(limit):
    return SimpleNamespace(config=DashScopeConfig(M4_BASE,M4_MODEL,'offline-model-observer',max_output_tokens=limit))


def observer(configured,logical,body):
    originals=SimpleNamespace(artifact=lambda *a,**k:encode(dict(wire_input_utf8=encode(body).decode())),
                              input=lambda *a,**k:encode(logical))
    return RuntimeModel(originals,configured,native_turn_profile=M4_NATIVE_TURN_BUFFERED)


def wire(limit):
    return dict(model=M4_MODEL,stream=True,stream_options={'include_usage':True},enable_thinking=False,max_tokens=limit)


@pytest.mark.parametrize('limit',[768,1536])
def test_actual_descriptor_derives_all_profile_caps_from_provider_config(limit):
    value=configured_model(provider(limit),M4_NATIVE_TURN_BUFFERED)
    caps=value['parameters']['max_tokens_by_profile']
    assert caps['answer']==caps['intake']==limit
    assert caps['reflection']==min(1024,limit)
    for profile in GENERATION_PROFILES:assert caps[profile]==(limit if profile in RICH else min(1024,limit))
    if limit==1536:assert value==source_c0_national_v2()['model']


@pytest.mark.parametrize('profile',GENERATION_PROFILES)
@pytest.mark.parametrize('limit',[768,1536])
def test_actual_wire_observer_accepts_only_the_profile_configured_cap(profile,limit):
    configured=provider(limit);expected=limit if profile in RICH else min(1024,limit)
    read=observer(configured,dict(draft_profile=profile),wire(expected))
    assert read('fixture-token','fixture-mid','fixture-op')==configured_model(configured,M4_NATIVE_TURN_BUFFERED)
    for wrong in (expected+1,expected-1):
        with pytest.raises(Unavailable,match='ACTUAL_MODEL_WIRE_PARAMETERS_CHANGED'):
            observer(configured,dict(draft_profile=profile),wire(wrong))('fixture-token','fixture-mid','fixture-op')


@pytest.mark.parametrize('logical',[{},dict(draft_profile='forged-profile')])
def test_unknown_or_old_json_profile_does_not_gain_the_rich_cap(logical):
    configured=provider(1536)
    with pytest.raises(Unavailable,match='ACTUAL_MODEL_WIRE_PARAMETERS_CHANGED'):
        observer(configured,logical,wire(1536))('fixture-token','fixture-mid','fixture-op')
    assert observer(configured,logical,wire(1024))('fixture-token','fixture-mid','fixture-op')==configured_model(configured,M4_NATIVE_TURN_BUFFERED)


@pytest.mark.parametrize('logical',[dict(native_turn_profile=M4_NATIVE_TURN_BUFFERED),
                                  dict(structured_profile='LIO-planning-intake.8')])
def test_original_native_and_structured_full_output_rules_are_unchanged(logical):
    configured=provider(1536)
    assert observer(configured,logical,wire(1536))('fixture-token','fixture-mid','fixture-op')==configured_model(configured,M4_NATIVE_TURN_BUFFERED)
    with pytest.raises(Unavailable,match='ACTUAL_MODEL_WIRE_PARAMETERS_CHANGED'):
        observer(configured,logical,wire(1024))('fixture-token','fixture-mid','fixture-op')


@pytest.mark.parametrize('change',[dict(model='wrong-model'),dict(stream=False),dict(stream_options={}),dict(enable_thinking=True)])
def test_new_rich_profile_does_not_relax_other_actual_wire_parameters(change):
    configured=provider(1536);body=wire(1536);body.update(change)
    with pytest.raises(Unavailable,match='ACTUAL_MODEL_WIRE_PARAMETERS_CHANGED'):
        observer(configured,dict(draft_profile=RICH[0]),body)('fixture-token','fixture-mid','fixture-op')


def test_changed_expected_model_card_still_requires_an_explicit_revision():
    model=deepcopy(source_c0_national_v2()['model'])
    model['parameters']['max_tokens_by_profile'][RICH[0]]=1024
    with pytest.raises(Invalid,match='B_MODEL_PROFILE_REQUIRES_EXPLICIT_REVISION'):
        freeze_national_v2(dict(code_sha='a'*40,image_digest='sha256:'+'b'*64,model=model),resource_root=ROOT)
