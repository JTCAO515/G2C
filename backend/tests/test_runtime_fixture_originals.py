"""Original sources, stable policy references and current read qualification."""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from runtime_adapter import Invalid,Unavailable
from runtime_adapter.contract import encode,decode
from cj_api.runtime_fixture_originals import FixtureOriginalReferences
from cj_api.runtime_collector import RuntimeCollector
from test_runtime_fixture_registry import fixture


@pytest.fixture
def source(fixture,tmp_path):
    token='local-original-E-token'
    fixture.consumer=replace(fixture.consumer,auth_session_id=sha256(token.encode()).hexdigest())
    fixture.policy['consumer_binding_sha256']=fixture.consumer.key
    fixture.policy_file.write_bytes(encode(fixture.policy))
    registry=fixture.build(bound=fixture.consumer)
    raw=decode(fixture.request());raw['binding_sha256']=fixture.consumer.key;raw=encode(raw)
    directory=tmp_path/'metadata-originals';directory.mkdir(mode=0o700)
    def refs(use=raw):return FixtureOriginalReferences(directory,registry,use)
    return SimpleNamespace(registry=registry,raw=raw,refs=refs,fixture=fixture,
        directory=directory,token=token)


def test_policy_reference_precedes_definition_use_and_is_stable_across_uses(source):
    reader=source.refs();policy=reader.issue(source.token,'registry')
    assert reader.resolve(source.token,policy['ref'])==source.registry.raw
    other=decode(source.raw);other['attempt_id']='second';other=encode(other)
    assert source.refs(other).issue(source.token,'registry')==policy
    assert source.refs(other).resolve(source.token,policy['ref'])==source.registry.raw
    assert not list(source.fixture.directory.iterdir())


def test_reservation_original_is_actual_record_and_stable_identity_not_ordinal(source):
    source.registry.reserve(source.raw);reader=source.refs()
    original=reader.issue(source.token,'reservation')
    raw=reader.resolve(source.token,original['ref'])
    assert decode(raw)==source.registry.read(source.raw)
    assert original['sha256']==sha256(raw).hexdigest()
    identity=source.registry.reservation_identity(source.raw)
    assert len(identity)==64 and identity+'.json'in [p.name for p in source.fixture.directory.iterdir()]
    assert reader.issue(source.token,'reservation')==original
    assert len(list(source.fixture.directory.iterdir()))==1


def test_missing_reservation_does_not_mint_a_body_from_request(source):
    with pytest.raises(Unavailable):source.refs().issue(source.token,'reservation')
    assert not list(source.directory.iterdir())


def test_original_reference_cannot_change_use_or_kind(source):
    source.registry.reserve(source.raw);reader=source.refs();ref=reader.issue(source.token,'reservation')
    other=decode(source.raw);other['candidate_id']='candidate1'
    with pytest.raises(Unavailable,match='ORIGINAL_USE_CHANGED'):
        source.refs(encode(other)).resolve(source.token,ref['ref'])
    with pytest.raises(Invalid):reader.issue(source.token,'expected-qualification')


@pytest.mark.parametrize('field',['source_allowed','consumer_allowed'])
def test_current_revocation_withholds_even_an_existing_policy_or_reservation_ref(source,field):
    source.registry.reserve(source.raw);reader=source.refs()
    refs=[reader.issue(source.token,kind)for kind in ('registry','reservation')]
    source.fixture.state[field]=False
    for ref in refs:
        with pytest.raises(Unavailable):reader.resolve(source.token,ref['ref'])
    assert len(list(source.fixture.directory.iterdir()))==1


def test_wrong_session_does_not_resolve_or_issue_originals(source):
    reader=source.refs();ref=reader.issue(source.token,'registry')
    with pytest.raises(Unavailable):reader.resolve('another-session',ref['ref'])
    with pytest.raises(Unavailable):reader.issue('another-session','registry')


def test_final_source_withdrawal_retains_descriptor_but_never_returns_it(source):
    reader=source.refs();original=source.registry.policy_source;calls=0
    def withdraw():
        nonlocal calls
        calls+=1
        if calls==2:source.fixture.state['source_allowed']=False
        return original()
    with patch.object(source.registry,'policy_source',side_effect=withdraw):
        with pytest.raises(Unavailable):reader.issue(source.token,'registry')
    assert len(list(source.directory.iterdir()))==1
    with pytest.raises(Unavailable):reader.issue(source.token,'registry')


def test_unknown_ack_or_corrupt_descriptor_is_query_only(source):
    reader=source.refs()
    with patch('cj_api.runtime_fixture_originals.os.fsync',side_effect=OSError('local ACK loss')):
        with pytest.raises(OSError):reader.issue(source.token,'registry')
    path,=source.directory.iterdir();ref=path.name.removesuffix('.json')
    assert reader.resolve(source.token,ref)==source.registry.raw
    path.write_bytes(b'{')
    with pytest.raises(ValueError):reader.resolve(source.token,ref)


def test_private_directory_and_no_payload_or_credential_descriptors(source,tmp_path):
    reader=source.refs();reader.issue(source.token,'registry')
    path,=source.directory.iterdir();raw=path.read_bytes()
    assert path.stat().st_mode&0o777==0o600
    assert source.token.encode()not in raw and b'body'not in raw
    source.directory.rename(tmp_path/'retained');source.directory.mkdir(mode=0o700)
    with pytest.raises(Unavailable):reader.issue(source.token,'registry')


def test_restarted_resolver_reconstructs_each_use_from_actual_retained_records(source):
    source.registry.reserve(source.raw)
    first=source.refs().issue(source.token,'reservation')
    other=decode(source.raw);other['attempt_id']='second';other=encode(other)
    source.registry.reserve(other);second=source.refs(other).issue(source.token,'reservation')
    resolver=FixtureOriginalReferences(source.directory,source.registry)
    assert decode(resolver.resolve(source.token,first['ref']))==source.registry.read(source.raw)
    assert decode(resolver.resolve(source.token,second['ref']))==source.registry.read(other)
    with pytest.raises(Unavailable):resolver.issue(source.token,'reservation')
    assert len(list(source.fixture.directory.iterdir()))==2


def test_collector_routes_metadata_without_reinterpreting_or_falling_back(source,tmp_path):
    source.registry.reserve(source.raw)
    ref=source.refs().issue(source.token,'reservation')
    legacy=tmp_path/'legacy';legacy.mkdir(mode=0o700)
    calls=[]
    def inventory(*args):calls.append(args);return b'original-own-inventory'
    collector=RuntimeCollector(SimpleNamespace(inventory=inventory),
        SimpleNamespace(binding=source.registry.consumer),None,lambda:source.token,source.fixture.pins,legacy,
        guard=source.registry.guard,state_reader=None,model_reader=None,
        fixture_originals=FixtureOriginalReferences(source.directory,source.registry),clock=lambda:1)
    old=collector.refs.issue(source.token,kind='inventory',message_id='own-original')
    assert collector.original(ref['ref'],deadline=10)==encode(source.registry.read(source.raw))
    source.fixture.state['source_allowed']=False
    with pytest.raises(Unavailable):collector.original(ref['ref'],deadline=10)
    # Withdrawal of C metadata is not withdrawal of E's own historical bytes.
    assert collector.original(old['ref'],deadline=10)==b'original-own-inventory'
    source.fixture.state['source_allowed']=True
    path=source.directory/(ref['ref']+'.json');path.write_bytes(b'{')
    count=len(calls)
    with pytest.raises(ValueError):collector.original(ref['ref'],deadline=10)
    assert len(calls)==count


def test_preparation_policy_bootstraps_without_definition_but_never_admits_use(source):
    store=source.registry
    def no_definition():raise Unavailable('DEFINITION_NOT_CREATED')
    def qualified():
        if not source.fixture.state['source_allowed']:raise Unavailable('SOURCE_REVOKED')
    store.source_guard=no_definition
    reader=source.refs(None)
    with pytest.raises(Unavailable,match='NOT_CONNECTED'):
        reader.issue(source.token,'preparation_policy')
    store.preparation_guard=qualified
    header=reader.issue(source.token,'preparation_policy')
    assert reader.resolve(source.token,header['ref'])==store.raw
    assert not list(source.fixture.directory.iterdir())
    with pytest.raises(Unavailable,match='DEFINITION_NOT_CREATED'):store.reserve(source.raw)
    with pytest.raises(Unavailable,match='DEFINITION_NOT_CREATED'):reader.issue(source.token,'registry')
    source.fixture.state['source_allowed']=False
    with pytest.raises(Unavailable,match='SOURCE_REVOKED'):reader.resolve(source.token,header['ref'])
    assert len(list(source.directory.iterdir()))==1


def test_bootstrap_header_is_not_a_reservation_or_legacy_policy_reference(source):
    source.registry.preparation_guard=lambda:None
    reader=source.refs(None)
    header=reader.issue(source.token,'preparation_policy')
    legacy=reader.issue(source.token,'registry')
    assert header!=legacy
    source.fixture.state['consumer_allowed']=False
    with pytest.raises(Unavailable):reader.resolve(source.token,header['ref'])


def test_cost_reference_resolves_only_retained_original_and_requalifies(source,tmp_path):
    # Controlled cost reader; native signed financial/Meter coverage lives in
    # runtime_model_capture_pg. No arbitrary caller body enters issue().
    state={'raw':encode({'original':'frozen-cost'}),'allowed':True}
    def read(*,deadline):
        if not state['allowed']:raise Unavailable('COST_WITHHELD')
        return state['raw']
    frozen=SimpleNamespace(inventory=SimpleNamespace(binding=source.registry.producer),read=read)
    source.registry.preparation_guard=lambda:None
    reader=FixtureOriginalReferences(source.directory,source.registry,
        preparation_cost=frozen,clock=lambda:1)
    ref=reader.issue(source.token,'preparation_cost')
    restarted=FixtureOriginalReferences(source.directory,source.registry,
        preparation_cost=frozen,clock=lambda:1)
    assert restarted.resolve(source.token,ref['ref'])==state['raw']
    state['raw']=encode({'original':'replaced-cost'})
    with pytest.raises(Unavailable,match='SOURCE_CHANGED'):restarted.resolve(source.token,ref['ref'])
    state['allowed']=False
    with pytest.raises(Unavailable,match='COST_WITHHELD'):restarted.resolve(source.token,ref['ref'])
    foreign=SimpleNamespace(inventory=SimpleNamespace(binding=source.registry.consumer),read=read)
    with pytest.raises(Invalid,match='PRODUCER_BINDING'):
        FixtureOriginalReferences(source.directory,source.registry,preparation_cost=foreign)
