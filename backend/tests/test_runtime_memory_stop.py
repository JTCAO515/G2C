"""Typed STOP-USE forwarding/control, no native data or provider is altered."""
from types import SimpleNamespace

import pytest

from cj_api.runtime_memory_stop import NativeMemoryStop


def test_stop_use_retains_exact_current_source_versions_and_queries_without_apply(monkeypatch):
    saved={};calls=[]
    def execute(repository,policy,guard,authority,raw,project):
        from cj_memory_management.typed import TypedStopUse
        action=TypedStopUse.parse(raw);calls.append(('apply',action))
        receipt=SimpleNamespace(operation_id=action.action_id,item_id=action.item_id,version=2,status='withdrawn',input_sha256='a'*64)
        return project(receipt)
    def query(repository,policy,guard,action_id,project):
        calls.append(('query',action_id))
        return project(SimpleNamespace(operation_id=action_id,item_id='actual-item',version=2,status='withdrawn',input_sha256='a'*64))
    monkeypatch.setattr('cj_api.runtime_memory_stop.execute',execute)
    monkeypatch.setattr('cj_api.runtime_memory_stop.query',query)
    stop=NativeMemoryStop(SimpleNamespace(),object(),object(),object(),object())
    def record(request,native,**kwargs):
        if saved:raise FileExistsError()
        saved.update(native)
    stop.inputs=SimpleNamespace(record=record,read=lambda *args,**kwargs:dict(saved))
    request={'step_id':'original-root-setup'}
    item=SimpleNamespace(version=7,command=SimpleNamespace(item_id='actual-item',source_id='actual-source',source_version=4))
    assert stop.stop(request,'deleted',item,deadline=30)['status']=='withdrawn'
    assert saved['expected_version']==7 and saved['expected_source_version']==4 and saved['source_id']=='actual-source'
    assert stop.proof(request,'deleted',deadline=30)['status']=='withdrawn'
    assert [kind for kind,_ in calls]==['apply','query']
    with pytest.raises(FileExistsError):stop.stop(request,'deleted',item,deadline=30)
    assert len(calls)==2
