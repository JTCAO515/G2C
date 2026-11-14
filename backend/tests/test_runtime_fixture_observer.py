"""Controlled observation boundaries; native PG coverage is a separate suite."""
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cj_api.local_app import ISSUER,scope_for
from cj_api.runtime_fixture_observer import FixtureTripObserver
from runtime_adapter import Binding,Unavailable


@pytest.fixture
def fixture():
    token='local-fixed-token';binding=Binding(scope_for(ISSUER,'C-fixture'),
        sha256(token.encode()).hexdigest(),'local-ledger','local-producer')
    pins=SimpleNamespace(key='a'*64,raw=b'fixed-pins')
    receipt=SimpleNamespace(conversation_id='native-chat',generation='native-generation',
        message_id='native-plan',run_id='native-run',sequence=1,input_sha256='b'*64)
    original=SimpleNamespace(receipt=receipt)
    current=SimpleNamespace(version=3,content=b'private Trip payload')
    head=SimpleNamespace(trip_id='private-trip',version=3,
        content_sha256=sha256(current.content).hexdigest())
    state=dict(pins=pins.raw,allowed=True,token=token,original=original,head=head,accepted=True)
    def guard(**kwargs):
        assert kwargs==dict(binding=binding,pins_sha256=pins.key,purpose='query',deadline=100,read_only=True)
        if not state['allowed']:raise Unavailable('ORIGINAL_AUTH_WITHHELD')
    authority=SimpleNamespace(require=guard,pins=lambda:state['pins'])
    message=SimpleNamespace(scope=binding.scope,query_lio_message=lambda mid:state['original'])
    messages=SimpleNamespace(with_history_context=lambda supplied,fn:fn(message))
    trip=SimpleNamespace(metadata=SimpleNamespace(principal=SimpleNamespace(issuer=ISSUER,subject='C-fixture')),
        lio_plan_receipt=lambda native:SimpleNamespace(trip_id=head.trip_id)if state['accepted']else None,
        lio_revisions=lambda tid,limit:(current,))
    def native_operation(supplied,fn):
        encoded=fn(trip)
        assert type(encoded)is bytes
        return encoded
    trips=SimpleNamespace(with_operation=native_operation)
    observer=FixtureTripObserver(authority,binding,pins,messages,trips,lambda:state['token'],'native-plan')
    with patch('cj_api.runtime_fixture_observer._head',side_effect=lambda *args:state['head']):
        yield SimpleNamespace(observer=observer,state=state,original=original,receipt=receipt,
            trip=trip,trips=trips,current=current,binding=binding,head=head)


def test_actual_current_baseline_contains_no_private_payload_or_pass_claim(fixture):
    result=fixture.observer.observe(deadline=100)
    assert result==dict(producer_binding_sha256=fixture.binding.key,
        preparation_message_id='native-plan',preparation_run_id='native-run',
        preparation_input_sha256='b'*64,baseline=dict(trip_id_sha256=sha256(b'private-trip').hexdigest(),
            trip_version=3,content_sha256=sha256(b'private Trip payload').hexdigest()))
    assert fixture.observer.observe(deadline=100)==result
    assert 'PASS'not in str(result)and 'private Trip payload'not in str(result)


@pytest.mark.parametrize('change',[{'allowed':False},{'token':'replacement'},{'pins':b'new-source'},
    {'original':None},{'accepted':False},{'head':None}])
def test_missing_or_withdrawn_current_sources_withhold(fixture,change):
    fixture.state.update(change)
    with pytest.raises(Unavailable):fixture.observer.observe(deadline=100)


def test_same_historical_trip_is_not_a_current_head(fixture):
    fixture.state['head']=SimpleNamespace(trip_id='private-trip',version=4,
        content_sha256=fixture.head.content_sha256)
    with pytest.raises(Unavailable,match='CURRENT_TRIP_CHANGED'):
        fixture.observer.observe(deadline=100)


def test_concurrent_head_change_during_native_read_is_not_published(fixture):
    def revisions(tid,limit):
        fixture.state['head']=None
        return(fixture.current,)
    fixture.trip.lio_revisions=revisions
    with pytest.raises(Unavailable,match='CURRENT_TRIP_CHANGED'):
        fixture.observer.observe(deadline=100)


def test_original_message_changes_after_trip_read_withholds_observation(fixture):
    original=fixture.trips.with_operation
    def change(token,fn):
        result=original(token,fn)
        fixture.state['original']=SimpleNamespace(receipt=SimpleNamespace(run_id='different'))
        return result
    fixture.trips.with_operation=change
    with pytest.raises(Unavailable,match='PREPARATION_SOURCE_CHANGED'):
        fixture.observer.observe(deadline=100)


@pytest.mark.parametrize('field,value',[('allowed',False),('pins',b'replaced-after-read')])
def test_final_current_qualification_is_rechecked(fixture,field,value):
    original=fixture.trips.with_operation
    def withdraw(token,fn):
        result=original(token,fn);fixture.state[field]=value
        return result
    fixture.trips.with_operation=withdraw
    with pytest.raises(Unavailable):fixture.observer.observe(deadline=100)


def test_native_trip_owner_must_match_original_message_owner(fixture):
    fixture.trip.metadata.principal=SimpleNamespace(issuer=ISSUER,subject='E-fixture')
    with pytest.raises(Unavailable,match='OBSERVER_OWNER_CHANGED'):
        fixture.observer.observe(deadline=100)
