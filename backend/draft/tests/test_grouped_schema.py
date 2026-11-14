"""Generation constraints and original grouped validation stay separate."""
from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace

from jsonschema import Draft202012Validator, ValidationError
import pytest

from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL, ProviderFailed
from cj_draft.grouped_plan import (GENERATION_PROFILES, expand, grouped_input,
    response_format, response_format_sha256)
from cj_draft.rich_schema import GENERATION_PROFILES as RICH_GENERATION_PROFILES
from cj_trip.domain import packed
from cj_trip.structured import FieldRejected
from grouped_draft_fixtures import reply
from test_grouped_plan import publisher


ORIGINAL = '''{"version":"TRIP-lio-first-plan.2","title":"上海豪华三日游","days":[["2026-12-01",[["s1","外滩",14,0,"18:00"],["self","party"]],["s2","上海柏悦酒店·餐厅",19,0,"21:30"],["self","party"]]],"2026-12-02":[["s3","豫园",9,0,"12:00"],["self","party"]],
"s4": ["陆家嘴中心绿地", 14, "0", "17:00"],
"s5": ["Ultraviolet by Paul Pairet", 19, "0", "22:00"]
}'''


@pytest.mark.parametrize('ordinal', [False, True])
@pytest.mark.parametrize('retained', [False, True])
@pytest.mark.parametrize('language', ['zh', 'en'])
def test_four_profiles_accept_complete_groups_and_keep_first_delta_exclusive(ordinal, retained, language):
    value=reply(4,language,ordinal=ordinal,delta=retained)
    schema=response_format(value['version'])['json_schema']['schema']
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema);validator.validate(value)
    other=reply(4,language,ordinal=ordinal,delta=not retained)
    with pytest.raises(ValidationError):validator.validate(other)


def test_original_malformed_result_is_rejected_without_repair():
    import hashlib
    raw=ORIGINAL.encode()
    assert hashlib.sha256(raw).hexdigest()=='ac1bdd701f71af54b0cea22164c6a7a3f8f0745eaa156efa55db55b3a0abe331'
    with pytest.raises(ValidationError):
        Draft202012Validator(response_format(GENERATION_PROFILES[0])['json_schema']['schema']).validate(json.loads(raw))
    with pytest.raises(FieldRejected, match='exact grouped model fields required'):
        expand(raw,None,retained=False,ordinal=False)


@pytest.mark.parametrize('change', [
    lambda v:v.update(extra=[]), lambda v:v.pop('title'),
    lambda v:v['days'][0].append([]),
    lambda v:v['days'][0][1][0].__setitem__(2,14),
    lambda v:v['days'][0][1][0].__setitem__(2,'25:00'),
    lambda v:v['days'][0][1].append(['self','party']),
    lambda v:v['days'][0][1][0].__setitem__(4,[]),
])
def test_root_pair_clock_and_participant_shapes_are_constrained(change):
    value=reply(4,'en');change(value)
    with pytest.raises(ValidationError):
        Draft202012Validator(response_format(value['version'])['json_schema']['schema']).validate(value)


@pytest.mark.parametrize('ordinal', [False, True])
@pytest.mark.parametrize('retained', [False, True])
def test_factory_selects_actual_publisher_context_and_freezes_original_call(ordinal, retained):
    host,capture=publisher(4,'en',ordinal=ordinal)
    host.source.contexts[capture.binding]=object() if retained else None
    host.system='original system'
    messages=[dict(role='user',content='original traveler message')];provider=object()
    packet=grouped_input(host,capture,messages,provider)
    assert packet.profile==reply(4,'en',ordinal=ordinal,delta=retained)['version']
    messages[0]['content']='changed caller alias';host.system='later publisher system'
    host.source.contexts[capture.binding]=None if retained else object()
    packet.messages[0]['content']='changed returned materialization'
    assert packet.messages==[dict(role='user',content='original traveler message')]
    assert packet.system=='original system' and packet.provider is provider
    with pytest.raises(FrozenInstanceError):packet.profile='forged'
    assert grouped_input(SimpleNamespace(system=packet.system+' '+packet.profile),None,messages,provider) is None


def test_schema_does_not_replace_dynamic_source_and_companion_guards():
    for change in (lambda v:v['days'][0].__setitem__(0,'2026-12-31'),
                   lambda v:v['days'][0][1][0].__setitem__(4,['companion:madeup'])):
        host,capture=publisher(4,'en');value=reply(4,'en');change(value)
        Draft202012Validator(response_format(value['version'])['json_schema']['schema']).validate(value)
        with pytest.raises(ValueError):host.build_plan(packed(value),capture)


def test_unknown_profile_has_no_generated_format():
    with pytest.raises(KeyError):response_format('unselected-profile')


@pytest.mark.parametrize('profile', GENERATION_PROFILES[:4])
def test_provider_wire_binds_schema_and_keeps_original_1024_cap(profile):
    class Captured(Exception):pass
    class Ledger:
        def begin(self,attempt,kind,raw):self.raw=raw;raise Captured()
    ledger=Ledger();provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'offline-only',max_output_tokens=1536),ledger)
    stream=provider.invoke([dict(role='user',content='plan')],'trusted system','one-original',receipt={},guard=lambda:None,
        draft_profile=profile,draft_schema_sha256=response_format_sha256(profile))
    with pytest.raises(Captured):next(stream)
    body=json.loads(ledger.raw)
    assert body['response_format']==response_format(profile)
    assert body['max_tokens']==1024 and body['model']==M4_MODEL and body['enable_thinking'] is False


@pytest.mark.parametrize('profile', RICH_GENERATION_PROFILES)
@pytest.mark.parametrize('configured,expected', [(1536,1536),(768,768)])
def test_rich_provider_wire_binds_schema_and_respects_exact_profile_and_config_caps(profile,configured,expected):
    class Captured(Exception):pass
    class Ledger:
        def begin(self,attempt,kind,raw):self.raw=raw;raise Captured()
    ledger=Ledger();provider=MeteredDashScopeProvider(DashScopeConfig(
        M4_BASE,M4_MODEL,'offline-only',max_output_tokens=configured),ledger)
    stream=provider.invoke([dict(role='user',content='plan')],'trusted system','one-original',receipt={},guard=lambda:None,
        draft_profile=profile,draft_schema_sha256=response_format_sha256(profile))
    with pytest.raises(Captured):next(stream)
    body=json.loads(ledger.raw)
    assert body['response_format']==response_format(profile)
    assert body['max_tokens']==expected and body['model']==M4_MODEL and body['enable_thinking'] is False


@pytest.mark.parametrize('options', [dict(draft_profile='forged',draft_schema_sha256='0'*64),
    dict(draft_profile=GENERATION_PROFILES[0]),
    dict(draft_profile=GENERATION_PROFILES[0],draft_schema_sha256='0'*64),
    dict(draft_profile=GENERATION_PROFILES[0],draft_schema_sha256=response_format_sha256(GENERATION_PROFILES[0]),lio_answer=True),
    dict(draft_profile=GENERATION_PROFILES[0],draft_schema_sha256=response_format_sha256(GENERATION_PROFILES[0]),structured_profile='LIO-planning-intake.9')])
def test_forged_missing_or_inapplicable_profile_hash_cannot_dispatch(options):
    class Ledger:
        calls=0
        def begin(self,*args):self.calls+=1
    ledger=Ledger();provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'offline-only'),ledger)
    stream=provider.invoke([dict(role='user',content='plan')],'trusted system','one-original',receipt={},guard=lambda:None,**options)
    with pytest.raises(ProviderFailed):next(stream)
    assert ledger.calls==0 and provider.calls==0


def test_unselected_text_marker_keeps_old_wire_bytes():
    class Captured(Exception):pass
    class Ledger:
        def begin(self,attempt,kind,raw):self.raw=raw;raise Captured()
    wires=[]
    for profile in (None,GENERATION_PROFILES[0]):
        ledger=Ledger();provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'offline-only'),ledger)
        text='ordinary system mentions '+GENERATION_PROFILES[0]
        options={} if profile is None else dict(draft_profile=None,draft_schema_sha256=None)
        stream=provider.invoke([dict(role='user',content='plan')],text,'same-original',receipt={},guard=lambda:None,**options)
        with pytest.raises(Captured):next(stream)
        wires.append(ledger.raw)
    assert wires[0]==wires[1] and json.loads(wires[0])['response_format']=={'type':'json_object'}
