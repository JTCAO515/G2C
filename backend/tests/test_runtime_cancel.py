"""Native cancel ACK handling; controlled native handler, no dispatch/fees."""
from types import SimpleNamespace

import pytest

from cj_api.runtime_cancel import NativeCancellation
from cj_run.cancellation import CancellationUnknown
from runtime_adapter.contract import encode,decode


def test_uncertain_cancel_never_replays_or_releases_unconfirmed_worker():
    state=dict(status='running',calls=0,releases=[])
    claims=SimpleNamespace(read=lambda *args,**kwargs:encode(dict(kind='start_controlled_generation',step_id='original-start')))
    controls=SimpleNamespace(release=lambda mid:state['releases'].append(mid))
    originals=SimpleNamespace(inventory=lambda token,mid:encode(dict(status=state['status'],run_id='original-run',events=[])))
    cancel=NativeCancellation(claims,object(),object(),lambda:'fixture-token',controls,originals)
    def uncertain(*args):state['calls']+=1;raise CancellationUnknown()
    cancel.handler=SimpleNamespace(cancel_travel_projected=uncertain)
    request=dict(kind='cancel_original_run',step_id='original-cancel',prior_step_ids=['setup','original-start'])
    with pytest.raises(CancellationUnknown):cancel.dispatch(request,deadline=30)
    assert state['calls']==1 and state['releases']==[]
    assert decode(cancel.proof(request,deadline=30))['status']=='UNKNOWN'
    state['status']='cancelled'
    assert decode(cancel.proof(request,deadline=30))['status']=='CANCELLED'
    assert state['calls']==1 and state['releases']==[]  # query stays read-only


def test_cancel_commit_before_lost_ack_may_release_only_after_original_confirmation():
    state=dict(status='running',calls=0,releases=[])
    claims=SimpleNamespace(read=lambda *args,**kwargs:encode(dict(kind='start_controlled_generation',step_id='original-start')))
    controls=SimpleNamespace(release=lambda mid:state['releases'].append(mid))
    originals=SimpleNamespace(inventory=lambda token,mid:encode(dict(status=state['status'],run_id='original-run',events=[])))
    cancel=NativeCancellation(claims,object(),object(),lambda:'fixture-token',controls,originals)
    def committed_unknown(*args):state.update(calls=state['calls']+1,status='cancelled');raise CancellationUnknown()
    cancel.handler=SimpleNamespace(cancel_travel_projected=committed_unknown)
    request=dict(kind='cancel_original_run',step_id='original-cancel',prior_step_ids=['setup','original-start'])
    with pytest.raises(CancellationUnknown):cancel.dispatch(request,deadline=30)
    assert state['calls']==1 and state['releases']==['original-start']
