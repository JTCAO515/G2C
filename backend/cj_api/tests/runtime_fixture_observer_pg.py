"""Native selected Trip and original preparation lineage, local/Fake only."""
from hashlib import sha256
import json
import time
from types import SimpleNamespace

from cj_api.runtime_fixture_observer import FixtureTripObserver
from cj_api.local_app import ISSUER,scope_for
from cj_auth.interfaces import AdmissionStatus
from runtime_adapter import Binding,Unavailable
import local_history_pg as harness
import runtime_native_dialogue_pg as native


def exercise(auth,conninfo):
    fixture=native.exercise(auth.parent/'fixture-observer-native',conninfo)
    binding=Binding(fixture.scope,sha256(fixture.token.encode()).hexdigest(),
        'local-fixture-ledger','local-fixture-producer')
    pins=SimpleNamespace(key='a'*64,raw=b'local-fixture-pins')
    state=dict(token=fixture.token,pins=pins.raw)

    # Financial/source policy are fixtures, not real original-ledger admission.
    # Native JWT + MESSAGE/Trip/source-lineage checks below are real local PG.
    class Authority:
        def __init__(self,bound):self.bound=bound
        def require(self,**kwargs):
            assert kwargs['binding']==self.bound and kwargs['pins_sha256']==pins.key
            assert kwargs['read_only']is True and kwargs['purpose']=='query'
            assert time.monotonic()<kwargs['deadline']
            decision=fixture.checker.check(state['token'])
            if decision.status is not AdmissionStatus.ALLOWED:
                raise Unavailable('LOCAL_CURRENT_AUTH_WITHHELD')
        def pins(self):return state['pins']

    def observer(mid='native-undo-plan',bound=binding):
        return FixtureTripObserver(Authority(bound),bound,pins,fixture.messages,fixture.trips,
            lambda:state['token'],mid)

    before=fixture.model.calls
    first=observer().observe(deadline=time.monotonic()+30)
    assert first['baseline']['trip_version']==3
    assert first['preparation_message_id']=='native-undo-plan'
    assert 'content'not in first and 'conversation_id'not in first
    assert observer().observe(deadline=time.monotonic()+30)==first
    assert fixture.model.calls==before
    state['pins']=b'changed-source'
    try:observer().observe(deadline=time.monotonic()+30)
    except Unavailable:pass
    else:raise AssertionError('old-source fixture observation escaped')
    state['pins']=pins.raw
    for mid in ('missing-preparation','native-undo-edit'):
        try:observer(mid).observe(deadline=time.monotonic()+30)
        except Unavailable:pass
        else:raise AssertionError('non-plan preparation became a source')
    state['token']=fixture.foreign_token
    try:observer().observe(deadline=time.monotonic()+30)
    except Unavailable:pass
    else:raise AssertionError('different session read fixture')
    foreign=Binding(scope_for(ISSUER,'runtime-native-undo-foreign'),
        sha256(fixture.foreign_token.encode()).hexdigest(),binding.ledger_id,binding.producer_id)
    try:observer(bound=foreign).observe(deadline=time.monotonic()+30)
    except Unavailable:pass
    else:raise AssertionError('valid foreign AUTH read original C preparation')
    state['token']=fixture.token
    (fixture.auth/'invited.json').write_text(json.dumps(['runtime-native-undo-foreign']))
    try:observer().observe(deadline=time.monotonic()+30)
    except Unavailable:pass
    else:raise AssertionError('revoked source returned cached observation')
    assert fixture.model.calls==before
    print('PASS native current selected Trip v3 and accepted preparation lineage, zero extra models, '
        'wrong preparation/source/session and revoked JWT withheld; financial/isolation/publication UNRUN')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
