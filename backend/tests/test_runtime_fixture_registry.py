"""Reservation mechanics only. No native source, isolation or paid qualification."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime,timezone
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cj_api.runtime_fixture_registry import FixtureUseRegistry,VERSION
from runtime_adapter import Binding,Invalid,Unavailable
from runtime_adapter.contract import decode,encode


@pytest.fixture
def fixture(tmp_path):
    directory=tmp_path/'reservations';directory.mkdir(mode=0o700)
    producer=Binding('C-owner','C-session','same-ledger','same-producer')
    consumer=Binding('E-owner','E-session','same-ledger','same-producer')
    pins=SimpleNamespace(key='a'*64)
    ref={'ref':'original-'+'b'*64,'sha256':'c'*64}
    data=dict(version=VERSION,registry_id='approved-registry',fixture_id='fixture-1',fixture_revision=1,
        producer_binding_sha256=producer.key,consumer_binding_sha256=consumer.key,
        baseline=dict(trip_id_sha256='d'*64,trip_version=3,content_sha256='e'*64),
        consumer_pins_sha256=pins.key,consumer_registration_ref=ref,experiment_ref=ref,public_release_ref=ref,
        batch_ids=['batch1','batch2'],candidate_ids=['C0','candidate1'],languages=['zh','en'],
        valid_from='2026-11-14T00:00:00Z',valid_until='2026-11-14T02:00:00Z',maximum_uses=2)
    policy_file=tmp_path/'B-policy.json';policy_file.write_bytes(encode(data));policy_file.chmod(0o600)
    state=dict(consumer_allowed=True,source_allowed=True,definition_ref=ref,
        now=datetime(2026,11,14,1,tzinfo=timezone.utc))
    admission=Lock()
    def guard(**unused):
        if not state['consumer_allowed']:raise Unavailable('ORIGINAL_CONSUMER_REVOKED')
    def source_guard():
        if not state['source_allowed']:raise Unavailable('ORIGINAL_SOURCE_WITHHELD')
        return state['definition_ref']
    def build(bound=consumer,observer=producer):
        return FixtureUseRegistry(directory,policy_file,producer,observer,bound,pins,guard=guard,
            source_guard=source_guard,admission_lock=lambda:admission,clock=lambda:state['now'])
    def request(attempt='attempt1',step='step1',**updates):
        return encode(dict(binding_sha256=consumer.key,pins_sha256=pins.key,batch_id='batch1',
            candidate_id='C0',task_id='val-owner',language='zh',attempt_id=attempt,step_id=step,
            request_sha256='f'*64,**updates))
    return SimpleNamespace(directory=directory,policy_file=policy_file,policy=data,state=state,
        build=build,request=request,consumer=consumer,producer=producer,pins=pins)


def test_policy_contains_no_future_definition_hash_and_reservation_is_not_dispatch(fixture):
    store=fixture.build();raw=fixture.request();first=store.reserve(raw)
    assert first['ordinal']==1 and first['use']==decode(raw)
    assert store.reserve(raw)==store.read(raw)==first
    path,=fixture.directory.iterdir()
    assert path.stat().st_mode&0o777==0o600
    assert b'text'not in path.read_bytes()and b'token'not in path.read_bytes()
    assert 'definition_sha256'not in fixture.policy and 'PASS'not in path.read_text()


def test_changed_candidate_or_request_cannot_rebind_the_same_original(fixture):
    store=fixture.build();raw=fixture.request();store.reserve(raw)
    for updates in ({'candidate_id':'candidate1'},{'request_sha256':'0'*64},{'batch_id':'batch2'},{'language':'en'}):
        changed=decode(raw);changed.update(updates)
        with pytest.raises(Invalid,match='ORIGINAL_USE_CHANGED'):store.reserve(encode(changed))
    assert len(list(fixture.directory.iterdir()))==1


def test_limit_counts_reserved_and_unknown_uses_without_refund(fixture):
    store=fixture.build()
    first=store.reserve(fixture.request())
    fixture.state['source_allowed']=False
    with pytest.raises(Unavailable):store.read(fixture.request())
    fixture.state['source_allowed']=True
    assert store.reserve(fixture.request())==first
    assert store.reserve(fixture.request('attempt2'))['ordinal']==2
    with pytest.raises(Unavailable,match='LIMIT_REACHED'):store.reserve(fixture.request('attempt3'))
    assert fixture.build().read(fixture.request())==first


def test_fsync_ack_unknown_keeps_the_original_slot(fixture):
    store=fixture.build();raw=fixture.request()
    with patch('cj_api.runtime_fixture_registry.os.fsync',side_effect=OSError('synthetic ACK loss')):
        with pytest.raises(OSError):store.reserve(raw)
    # A complete durable original can be queried, not discarded/replaced.
    assert fixture.build().read(raw)['ordinal']==1
    assert fixture.build().reserve(raw)['ordinal']==1


def test_partial_original_stops_all_new_reservations(fixture):
    store=fixture.build();store.reserve(fixture.request())
    path,=fixture.directory.iterdir();path.write_bytes(b'{')
    with pytest.raises(Unavailable,match='UNRESOLVED'):store.reserve(fixture.request('attempt2'))
    assert len(list(fixture.directory.iterdir()))==1


def test_same_original_does_not_get_new_slot_after_policy_or_session_change(fixture):
    store=fixture.build();raw=fixture.request();store.reserve(raw)
    new_consumer=replace(fixture.consumer,auth_session_id='new-E-session')
    data={**fixture.policy,'fixture_revision':2,'consumer_binding_sha256':new_consumer.key}
    fixture.policy_file.write_bytes(encode(data))
    with pytest.raises(Unavailable,match='POLICY_CHANGED'):store.read(raw)
    rebuilt=fixture.build(bound=new_consumer)
    request=decode(raw);request['binding_sha256']=new_consumer.key
    with pytest.raises(Unavailable,match='POLICY_CHANGED'):rebuilt.reserve(encode(request))
    request['attempt_id']='new-original-attempt'
    assert rebuilt.reserve(encode(request))['ordinal']==1
    assert len(list(fixture.directory.iterdir()))==2


@pytest.mark.parametrize('field',['source_allowed','consumer_allowed'])
def test_revocation_after_storage_withholds_record_without_removing_it(fixture,field):
    store=fixture.build();original=store._current
    calls=0
    def revoke(read_only):
        nonlocal calls
        calls+=1
        if calls==2:fixture.state[field]=False
        original(read_only)
    store._current=revoke
    with pytest.raises(Unavailable):store.reserve(fixture.request())
    assert len(list(fixture.directory.iterdir()))==1
    with pytest.raises(Unavailable):fixture.build().read(fixture.request())


def test_expired_naive_or_changed_policy_never_returns_cached_allowance(fixture):
    store=fixture.build();store.reserve(fixture.request())
    for now in (datetime(2026,11,14,3,tzinfo=timezone.utc),datetime(2026,11,14,1)):
        fixture.state['now']=now
        with pytest.raises(Unavailable):store.read(fixture.request())
    fixture.state['now']=datetime(2026,11,14,1,tzinfo=timezone.utc)
    fixture.policy_file.write_bytes(encode({**fixture.policy,'maximum_uses':3}))
    with pytest.raises(Unavailable,match='POLICY_CHANGED'):store.reserve(fixture.request('attempt2'))


def test_concurrent_distinct_consumers_share_the_native_admission_fence(fixture):
    stores=[fixture.build(),fixture.build()]
    with ThreadPoolExecutor(max_workers=2)as executor:
        result=list(executor.map(lambda args:args[0].reserve(fixture.request(args[1])),zip(stores,['a','b'])))
    assert sorted(x['ordinal']for x in result)==[1,2]
    with pytest.raises(Unavailable):fixture.build().reserve(fixture.request('c'))


def test_observer_must_match_full_producer_binding_and_owners_must_differ(fixture):
    with pytest.raises(Invalid,match='ORIGINAL_BINDINGS'):
        fixture.build(observer=replace(fixture.producer,auth_session_id='another-C-session'))
    fake_consumer=replace(fixture.consumer,scope=fixture.producer.scope)
    fixture.policy_file.write_bytes(encode({**fixture.policy,'consumer_binding_sha256':fake_consumer.key}))
    with pytest.raises(Invalid,match='ORIGINAL_BINDINGS'):fixture.build(bound=fake_consumer)


def test_unsafe_files_directory_replacement_and_unknown_fields_stop(fixture,tmp_path):
    fixture.policy_file.chmod(0o644)
    with pytest.raises(ValueError):fixture.build()
    fixture.policy_file.chmod(0o600);store=fixture.build()
    fixture.directory.rename(tmp_path/'retained');fixture.directory.mkdir(mode=0o700)
    with pytest.raises(Unavailable,match='DIRECTORY_CHANGED'):store.reserve(fixture.request())


def test_unregistered_use_rejected_before_any_durable_record(fixture):
    store=fixture.build();raw=decode(fixture.request())
    for changes in ({'task_id':'other-task'},{'language':'fr'},{'candidate_id':'not-approved'},
                    {'pins_sha256':'0'*64},{'binding_sha256':'0'*64},{'extra':'opaque'}):
        with pytest.raises(Invalid):store.reserve(encode({**raw,**changes}))
    assert not list(fixture.directory.iterdir())


def test_definition_source_is_pinned_in_reservation_not_registry_header(fixture):
    store=fixture.build();original=store.reserve(fixture.request())
    assert original['definition_ref']==fixture.state['definition_ref']
    fixture.state['definition_ref']={'ref':'original-'+'1'*64,'sha256':'2'*64}
    with pytest.raises(Unavailable,match='DEFINITION_CHANGED'):store.read(fixture.request())
    with pytest.raises(Unavailable,match='DEFINITION_CHANGED'):store.reserve(fixture.request())
    assert len(list(fixture.directory.iterdir()))==1


def test_source_change_during_publication_withholds_but_does_not_free_slot(fixture):
    store=fixture.build();check=store.source_guard;calls=0
    def source():
        nonlocal calls
        calls+=1
        if calls==2:fixture.state['definition_ref']={'ref':'original-'+'1'*64,'sha256':'2'*64}
        return check()
    store.source_guard=source
    with pytest.raises(Unavailable,match='DEFINITION_CHANGED'):store.reserve(fixture.request())
    assert len(list(fixture.directory.iterdir()))==1
    with pytest.raises(Unavailable):fixture.build().read(fixture.request())


def test_source_reference_mutated_in_place_does_not_change_the_prior_snapshot(fixture):
    store=fixture.build();check=store.source_guard;calls=0
    def source():
        nonlocal calls
        calls+=1
        if calls==2:fixture.state['definition_ref']['sha256']='2'*64
        return check()
    store.source_guard=source
    with pytest.raises(Unavailable,match='DEFINITION_CHANGED'):store.reserve(fixture.request())
    record=decode(next(fixture.directory.iterdir()).read_bytes())
    assert record['definition_ref']['sha256']=='c'*64
