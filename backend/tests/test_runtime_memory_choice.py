"""Native choice orchestration; the actual service/owner checks remain native."""
from types import SimpleNamespace

import pytest

from cj_api.runtime_memory_choice import NativeMemoryChoice


def test_lost_remember_ack_reads_same_target_without_second_apply():
    calls=[];stored={};committed=set()
    def record(request,native,*,deadline,label):
        if label in stored:raise FileExistsError()
        stored[label]=native
    def decide(token,native,*,read_only=False):
        calls.append((native,read_only))
        if not read_only:
            committed.add(native['action_id'])
            raise OSError('controlled lost native ACK')
        return dict(action_id=native['action_id'],status='remembered' if native['action_id'] in committed else 'pending')
    choice=NativeMemoryChoice(SimpleNamespace(),SimpleNamespace(decide=decide),lambda:'fixture-token')
    choice.inputs=SimpleNamespace(record=record,read=lambda request,**kwargs:stored[kwargs['label']])
    request={'step_id':'original-setup'}
    with pytest.raises(OSError):choice.remember(request,'deleted-positive','original-opaque-target',deadline=30)
    assert choice.proof(request,'deleted-positive',deadline=30)['status']=='remembered'
    assert len(calls)==2 and calls[1][1] and calls[0][0] is calls[1][0]
    with pytest.raises(FileExistsError):choice.remember(request,'deleted-positive','different-target',deadline=30)
    assert len(calls)==2
