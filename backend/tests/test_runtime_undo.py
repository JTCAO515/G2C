"""Native undo binding/reconciliation controls; no real write or provider."""
from hashlib import sha256
from types import SimpleNamespace

import pytest

from cj_api.local_app import ISSUER
from cj_api.runtime_undo import NativeUndo
from cj_trip.domain import Trip,Denied
from cj_trip.lio_history import TripHead
from runtime_adapter.contract import decode,encode


def test_undo_queries_original_action_after_current_target_changes_and_never_reapplies():
    cid='lio-dialogue-'+'a'*32
    before=Trip('owned-trip',1,encode(dict(title='Original',items=[])))
    edited=Trip('owned-trip',2,encode(dict(title='Edited',items=[])))
    restored=Trip('owned-trip',3,before.content)
    state=dict(current=edited,applied=0,original=None)
    setup=dict(kind='task_setup',payload={'task_id':'val-undo'})
    claims=SimpleNamespace(read=lambda *args,**kwargs:encode(setup),query=lambda context,mid:SimpleNamespace(
        receipt=SimpleNamespace(conversation_id=cid)))
    def revisions(trip_id,*,before=None,limit=10):
        values=[restored,edited,before_trip] if state['current'].version==3 else [edited,before_trip]
        return tuple(t for t in values if before is None or t.version<before)[:limit]
    before_trip=before
    def apply(action):
        assert action.expected_version==2 and action.original_hash==sha256(edited.content).hexdigest()
        state.update(current=restored,applied=state['applied']+1,original=action.raw)
        return SimpleNamespace(action_id=action.action_id)
    def original(action):
        assert action.raw==state['original'],'query must use the original target, not current v3 target'
        return SimpleNamespace(action_id=action.action_id)
    context=SimpleNamespace(metadata=SimpleNamespace(principal=SimpleNamespace(issuer=ISSUER,subject='synthetic-owner')),
        lio_current_trip=lambda *args:TripHead.from_trip(state['current']),lio_revisions=revisions,
        undo_lio=apply,query_action=lambda action_id:None if state['original'] is None else SimpleNamespace(
            trip_id='owned-trip',committed_version=3),lio_undo_receipt=original)
    trip_boundary=SimpleNamespace(with_operation=lambda token,project:project(context))
    messages=SimpleNamespace(with_history_context=lambda token,project:project(object()))
    undo=NativeUndo(claims,messages,trip_boundary,lambda:'fixture-token')
    request=dict(step_id='original-action',prior_step_ids=['setup','saved','edited'])
    assert decode(undo.proof(request,deadline=30))['status']=='UNKNOWN' and state['applied']==0
    assert decode(undo.dispatch(request,deadline=30))['committed'] and state['applied']==1
    proof=decode(undo.proof(request,deadline=30))
    assert proof['status']=='PASS' and proof['history']['current']['title']=='Original'
    assert len(proof['history']['history'])==2 and proof['history']['undo_target'] is not None
    assert decode(undo.proof(request,deadline=30))['committed'] and state['applied']==1
    state['current']=Trip('different-owned-trip',3,before.content)
    with pytest.raises(Denied):undo.proof(request,deadline=30)
