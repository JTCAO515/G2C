"""Actual Meter state machine + SQLite, controlled native registration/AUTH source.

These are local component controls, not PG/HK or real vendor observations.
"""
from dataclasses import asdict
from datetime import date,datetime,timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.usage.tests.test_core import TransactionFake
from cj_api.runtime_weather_fault import NativeWeatherFault,read_artifact,artifact_name,PREFIX
from cj_usage.authorization_budget import AuthorizationBudget,journal_state
from cj_usage.core import Config,Command,Meter
from cj_usage.metered_exit import _PreparedCall,BudgetUnknown
from cj_usage.registered_exit import RegisteredExit,Registration,InvocationInput
from runtime_adapter.contract import decode,encode,Invalid,Unavailable


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);artifacts=tmp_path/'artifacts';artifacts.mkdir(mode=0o700)
    budget=AuthorizationBudget(tmp_path/'financial',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc))
    budget.begin('retained-original','model',b'original local fixture')
    binding=SimpleNamespace(scope='original-owner',message_id='original-message',run_id='original-run',
        conversation_id='original-chat',generation='original-generation',message_sequence=1)
    state={'vendor_calls':0,'bound':0,'day':'2026-11-13'}
    setup=dict(kind='task_setup',payload={'task_id':'dev-tool-failure'})
    message=dict(kind='message',prior_step_ids=['root-setup'])
    claims=SimpleNamespace(read=lambda mid,**kwargs:encode(setup if mid=='root-setup' else message))
    routing=SimpleNamespace(request=lambda source:message,selects=lambda source:True,clock=lambda:1.)
    monkeypatch.setattr('cj_api.runtime_weather_fault.original_for',lambda database,source:SimpleNamespace(question_day=date(2026,11,12)))
    control=NativeWeatherFault(claims,routing,None,budget,artifacts,SimpleNamespace(value={'code_sha':'a'*40}),lambda:'fixture-token')
    def prepare(argument):
        raw=encode(dict(name='weather',query=dict(fact_key='weather',region='beijing',
            dates=dict(start=argument,end=argument),conditions={'calendar_timezone':'Asia/Shanghai'})))
        def bind(operation,guard):
            state['bound']+=1
            def vendor():
                state['vendor_calls']+=1
                raise AssertionError('fault fixture must never call the vendor')
            return vendor
        return InvocationInput(raw,None,bind)
    native=Registration('tool',prepare)
    registration=control.wrap({'tool.weather':native},binding,routing.request(binding))['tool.weather']
    config=Config('provider_call',20,0,1000,8,4,20000,90)
    repo=TransactionFake();repo.scope='original-ledger-account'
    meter=Meter(repo,config,lambda:100.)
    exit=RegisteredExit(config,lambda source,account:meter,clock=lambda:100.,environment='local',
        output_limits=dict(model=5000,tool=5000,memory=5000),registrations={'tool.weather':registration})
    def prepared(day='2026-11-13'):
        value=registration.prepare_input(day)
        command=Command('original-attempt','original-operation','original-run','tool',sha256(value.original_bytes).hexdigest(),1,5000)
        step=SimpleNamespace(binding=binding,ledger_scope=repo.scope,command=command,
            operation_key='tool.weather-1',registration_id='tool.weather',original=SimpleNamespace(input_bytes=value.original_bytes))
        return value,step,_PreparedCall(step,None,'tool.weather',lambda:True,receipt=value.receipt,
            materialize_with_guard=lambda guard:value.bind_operation(step,guard))
    return control,state,budget,artifacts,exit,repo,prepared,binding


def test_one_original_dispatch_settles_meter_and_has_no_vendor_or_financial_attempt(fixture):
    control,state,budget,directory,exit,repo,prepared,binding=fixture
    value,step,call=prepared()
    with budget.connect() as db:before=journal_state(db)
    result=''.join(exit.stream(call));actual=repo.ledger.attempts[step.command.attempt_id]
    assert decode(result)['status']=='error' and actual.state=='settled'
    assert state=={'vendor_calls':0,'bound':1,'day':'2026-11-13'}
    with budget.connect() as db:
        assert journal_state(db)==before
        assert db.execute('SELECT 1 FROM attempt WHERE id=?',(step.command.attempt_id,)).fetchone() is None
    filename=directory/artifact_name(binding.scope,binding.run_id,step.operation_key,step.command.attempt_id)
    raw=filename.read_bytes();record=decode(raw)
    assert actual.receipt.receipt_id==PREFIX+sha256(raw).hexdigest()
    assert record['request_day']=='2026-11-12' and record['query_day']=='2026-11-13'
    assert record['original_dispatches']==1 and record['vendor_sends']==0
    assert filename.stat().st_mode&0o777==0o600
    stored=SimpleNamespace(receipt=SimpleNamespace(message_id=binding.message_id,run_id=binding.run_id,
        conversation_id=binding.conversation_id,generation=binding.generation,sequence=1))
    row=(step.operation_key,step.registration_id,'tool',step.command.attempt_id,step.command.operation_id)
    originals=SimpleNamespace(directory=directory,database=None,_meter=lambda *args:encode(asdict(actual)))
    usage=SimpleNamespace(command=step.command,input_bytes=value.original_bytes)
    assert read_artifact(originals,binding.scope,stored,None,row,usage)==raw
    tampered=dict(record,result_utf8='forged forecast');filename.write_bytes(encode(tampered))
    with pytest.raises(Unavailable,match='OUTPUT_HASH_CHANGED'):
        read_artifact(originals,binding.scope,stored,None,row,usage)
    with pytest.raises(BudgetUnknown):list(exit.stream(call))
    assert state['vendor_calls']==0


def test_wrong_calendar_day_stops_before_original_dispatch_or_meter(fixture):
    control,state,budget,directory,exit,repo,prepared,binding=fixture
    with pytest.raises(BudgetUnknown,match='original Beijing next-day'):prepared('2026-11-12')
    assert state['bound']==0 and state['vendor_calls']==0 and repo.ledger.attempts=={} and list(directory.iterdir())==[]


def test_fault_cannot_replace_an_existing_financial_original(fixture):
    control,state,budget,directory,exit,repo,prepared,binding=fixture
    value,step,call=prepared()
    budget.begin(step.command.attempt_id,'weather',value.original_bytes)
    with pytest.raises(BudgetUnknown,match='replace a financial original'):list(exit.stream(call))
    assert state['vendor_calls']==0 and list(directory.iterdir())==[]
    assert repo.ledger.attempts[step.command.attempt_id].state=='unknown'


def test_valid_preparation_alone_cannot_create_a_dispatch_or_settlement(fixture):
    control,state,budget,directory,exit,repo,prepared,binding=fixture
    value,step,call=prepared()
    assert state['bound']==state['vendor_calls']==0
    assert list(directory.iterdir())==[] and repo.ledger.attempts=={}
    with pytest.raises(KeyError):value.receipt(step.command.attempt_id,'provider_call',0)
