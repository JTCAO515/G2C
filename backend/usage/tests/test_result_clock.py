from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from cj_run.core import Binding
from cj_run.step_usage import ledger_scope_for
from cj_usage.core import Config
from cj_usage.registered_exit import RegisteredExit
from cj_usage.metered_exit import BudgetUnknown,BudgetExceeded


def guard(samples):
    binding=Binding('owner','chat','generation','message','run',1)
    config=Config('provider_call',10,0,1000,10,2,100,50)
    class Repository:
        scope=ledger_scope_for(binding.scope,config)
        @contextmanager
        def transaction(self):yield SimpleNamespace(last_clock=100)
    meter=SimpleNamespace(repo=Repository(),config=config)
    values=iter(samples)
    core=RegisteredExit(config,lambda binding,account:meter,clock=lambda:next(values),
        output_limits=dict(model=10,tool=10,memory=10),environment='local',registrations={})
    with patch('cj_run.operation_usage.OperationStore.bind_period_without_operation'):
        return core.prepare_result_publication(object(),binding)


def test_zero_model_clock_must_not_regress_after_first_sample():
    check=guard([200,150])
    with pytest.raises(BudgetUnknown):check()


def test_zero_model_clock_preserves_deadline_boundary():
    check=guard([200,250])
    with pytest.raises(BudgetExceeded):check()


def test_zero_model_clock_monotonic_before_deadline():guard([200,201])()
