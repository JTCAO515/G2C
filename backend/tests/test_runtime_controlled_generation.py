"""Pause ordering around the unchanged original exit; no provider/fee calls."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from time import monotonic

import pytest

from cj_api.runtime_controlled_generation import ControlledGeneration,ControlledRegisteredExit
from cj_usage.core import Config
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.registered_exit import RegisteredExit
from runtime_adapter import Unavailable


def test_control_waits_after_original_completion_then_releases_once(monkeypatch):
    control=ControlledGeneration();binding=SimpleNamespace(message_id='original-message')
    operation=SimpleNamespace(binding=binding,command=SimpleNamespace(kind='model'))
    prepared=SimpleNamespace(step=operation)
    calls=[]
    def original(self,call):
        assert call is prepared
        yield 'actual original chunk'
        calls.append('original completed/settled')
    monkeypatch.setattr(RegisteredExit,'stream',original)
    config=Config('provider_call',20,0,1000,8,8,20000,90)
    exit=ControlledRegisteredExit(config,lambda *args:None,clock=lambda:10,
        output_limits={'model':1000,'tool':1000,'memory':1000},environment='local',registrations={},observer=control)
    deadline=monotonic()+5;control.prepare(binding.message_id,deadline)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result=pool.submit(lambda:''.join(exit.stream(prepared)))
        assert control.wait_started(binding.message_id,deadline) is binding
        assert calls==['original completed/settled'] and not result.done()
        control.release(binding.message_id)
        assert result.result(timeout=2)=='actual original chunk'
    with pytest.raises(Unavailable,match='ALREADY_EXISTS'):control.prepare(binding.message_id,deadline)


def test_original_failure_never_arms_a_completed_control(monkeypatch):
    control=ControlledGeneration();binding=SimpleNamespace(message_id='original-message')
    control.prepare(binding.message_id,monotonic()+1)
    def failed(self,call):
        raise BudgetUnknown('actual original uncertainty')
        yield
    monkeypatch.setattr(RegisteredExit,'stream',failed)
    config=Config('provider_call',20,0,1000,8,8,20000,90)
    exit=ControlledRegisteredExit(config,lambda *args:None,clock=lambda:10,
        output_limits={'model':1000,'tool':1000,'memory':1000},environment='local',registrations={},observer=control)
    with pytest.raises(BudgetUnknown):list(exit.stream(SimpleNamespace(step=SimpleNamespace(binding=binding))))
    assert not control.pauses[binding.message_id].ready.is_set()
