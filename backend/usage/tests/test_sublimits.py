"""Original SQLite/producer-control integration; no real supplier or HK calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from hashlib import sha256
import json
from threading import Barrier
from types import SimpleNamespace

import pytest

from cj_usage import authorization_budget as parent
from cj_usage import sublimits
from cj_usage.metered_exit import BudgetUnknown

S=parent.CNY_SCALE


@pytest.fixture
def allocated(tmp_path,monkeypatch):
    # Explicit local seeded producer control, not a real adoption/transfer claim.
    now=lambda:datetime(2026,11,12,tzinfo=timezone.utc)
    old=parent.AuthorizationBudget(tmp_path/'journal',clock=now)
    old.begin('retained-legacy-unknown','model',b'old original')
    control=tmp_path/'control';control.mkdir();anchor=control/'adoption.json'
    with old.connect() as db:
        db.execute('UPDATE producer SET identity=?',(parent.HK_PRODUCER,))
        count,digest=parent.journal_state(db)
    anchor.write_text(json.dumps(dict(state='ADOPTED',ledger_id=old.ledger_id,attempt_count=count,attempts_sha256=digest)))
    monkeypatch.setattr(parent,'HK_JOURNAL_ROOT',old.root)
    monkeypatch.setattr(parent,'HK_ANCHOR',anchor)
    monkeypatch.setenv('CJ_M4_BUDGET_PRODUCER',parent.HK_PRODUCER)
    budget=parent.AuthorizationBudget(old.root,clock=now,authorization_guard=lambda:None,demo=True)
    def limit(cap,active=None,model=None,tools=None,calls=None):
        return dict(cap=cap,active_cap=cap if active is None else active,
                    model_cap=model,tool_cap=tools,max_calls=calls,model_calls=None,tool_calls=None)
    grants=dict(A=limit(None),B=limit(None),L=limit(11*S//10),C=limit(100*S),
                E=limit(50*S,tools=5*S,calls=2),F=limit(15*S,active=5*S,model=3*S,tools=2*S))
    bindings={sublimits.scope_hash('owner-'+line):line for line in grants}
    sublimits.activate(budget,grants,bindings)
    return budget,anchor


def received(tag):
    return dict(endpoint='https://dashscope.aliyuncs.com/compatible-mode/v1',region='cn-beijing',
        model_id='qwen3.8-flash',receipt_sha256=sha256(tag.encode()).hexdigest(),
        usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))


def test_original_rows_preserved_and_each_attempt_attributed_atomically(allocated):
    budget,anchor=allocated
    assert budget.inspect()[0]['attempt_id']=='retained-legacy-unknown'
    assert budget.inspect()[0]['state']=='INTENT'
    aid=sublimits.operation_id('owner-L');budget.begin(aid,'model',b'new original')
    view=sublimits.read(budget)
    assert view['L']['usage']==dict(calls=1,model_calls=1,tool_calls=0,model=S,tools=0,total=S)
    assert view['C']['usage']['total']==0
    assert json.loads(anchor.read_text())['state']==sublimits.ADOPTED
    with budget.connect() as db:
        assert db.execute('SELECT line FROM attempt_sublimit WHERE attempt_id=?',(aid,)).fetchone()==('L',)
        assert db.execute('SELECT state,receipt FROM attempt WHERE id=?',('retained-legacy-unknown',)).fetchone()==('INTENT',None)


def test_unknown_full_hold_blocks_line_without_charging_another_line(allocated):
    budget,_=allocated
    budget.begin(sublimits.operation_id('owner-L'),'model',b'one')
    with pytest.raises(BudgetUnknown,match='line authorization'):
        budget.begin(sublimits.operation_id('owner-L'),'model',b'two')
    budget.begin(sublimits.operation_id('owner-C'),'weather',b'own C')
    for aid in ('unregistered-id',sublimits.operation_id('unbound-owner')):
        with pytest.raises(BudgetUnknown):budget.begin(aid,'model',b'not assigned')
    assert len(budget.inspect())==3


def test_original_receipt_prices_usage_without_settling_invoice_or_resetting_hold(allocated):
    budget,_=allocated;first=sublimits.operation_id('owner-L')
    budget.begin(first,'model',b'one');budget.finish(first,received('one'))
    budget.begin(sublimits.operation_id('owner-L'),'model',b'two')
    assert sublimits.read(budget)['L']['usage']['total']==S+35
    with pytest.raises(BudgetUnknown):budget.begin(first,'model',b'replay')
    with pytest.raises(BudgetUnknown):budget.begin(sublimits.operation_id('owner-L'),'model',b'three')


def test_call_caps_and_first_f_stage_have_independent_hard_limits(allocated):
    budget,_=allocated
    for _ in range(2):budget.begin(sublimits.operation_id('owner-E'),'fact',b'public fact')
    with pytest.raises(BudgetUnknown,match='call allowance'):
        budget.begin(sublimits.operation_id('owner-E'),'fact',b'third')
    for _ in range(3):budget.begin(sublimits.operation_id('owner-F'),'model',b'original model')
    with pytest.raises(BudgetUnknown,match='category'):
        budget.begin(sublimits.operation_id('owner-F'),'model',b'fourth model')
    for _ in range(2):budget.begin(sublimits.operation_id('owner-F'),'weather',b'original tool')
    with pytest.raises(BudgetUnknown,match='line authorization'):
        budget.begin(sublimits.operation_id('owner-F'),'weather',b'third tool')
    assert sublimits.read(budget)['F']['policy']['cap']==15*S
    assert sublimits.read(budget)['F']['usage']['total']==5*S


def test_parallel_same_line_reservations_have_one_winner(allocated):
    budget,_=allocated;barrier=Barrier(2)
    def attempt(_):
        barrier.wait(timeout=5)
        try:budget.begin(sublimits.operation_id('owner-L'),'model',b'one original')
        except BudgetUnknown:return False
        return True
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(attempt,range(2)))==1
    assert sublimits.read(budget)['L']['usage']['calls']==1


def test_control_detects_cap_mapping_and_association_rollback(allocated):
    budget,anchor=allocated
    budget.begin(sublimits.operation_id('owner-L'),'model',b'original')
    with budget.connect() as db:db.execute('DELETE FROM attempt_sublimit')
    with pytest.raises(BudgetUnknown,match='non-restored sublimit'):
        budget.begin(sublimits.operation_id('owner-L'),'model',b'not a fresh budget')
    assert json.loads(anchor.read_text())['state']==sublimits.ADOPTED


def test_interrupted_control_commit_is_hold_not_a_fresh_attempt(allocated,monkeypatch):
    budget,anchor=allocated;original=parent.save_anchor
    def interrupt(value):
        if value['state']==sublimits.ADOPTED:raise OSError('synthetic lost final control ACK')
        original(value)
    monkeypatch.setattr(parent,'save_anchor',interrupt)
    with pytest.raises(OSError):budget.begin(sublimits.operation_id('owner-L'),'model',b'original')
    assert json.loads(anchor.read_text())['state']=='WRITE_INTENT'
    with pytest.raises(BudgetUnknown):budget.begin(sublimits.operation_id('owner-L'),'model',b'not replayed')


def test_parent_ceiling_still_applies_and_allocation_cannot_be_reactivated(allocated,monkeypatch):
    budget,_=allocated
    monkeypatch.setattr(parent,'MODEL_TOTAL_CNY',1)
    with pytest.raises(BudgetUnknown,match='M4 model authorization ceiling'):
        budget.begin(sublimits.operation_id('owner-C'),'model',b'not above parent')
    view=sublimits.read(budget)
    with pytest.raises(BudgetUnknown,match='first allocation'):
        sublimits.activate(budget,{k:v['policy'] for k,v in view.items()},
                           {sublimits.scope_hash('owner-'+line):line for line in view})


def test_registered_ids_derive_from_original_binding_not_client_text(monkeypatch):
    from cj_run.operation_usage import OperationStore,RegisteredOperation
    from cj_run.usage_binding import UsageBinding
    from cj_usage.core import Config,Command
    from cj_usage.registered_exit import RegisteredExit,Registration,InvocationInput
    monkeypatch.setenv('CJ_M4_BUDGET_PRODUCER',parent.HK_PRODUCER)
    binding=SimpleNamespace(scope='owner-L',run_id='original-run')
    def create(store,bound,key,registration,kind,raw,limit):
        command=Command(store.new_id(),store.new_id(),bound.run_id,kind,sha256(raw).hexdigest(),1,limit)
        return RegisteredOperation(bound,key,registration,'original-account',(0,1000),UsageBinding.from_command(command,raw))
    monkeypatch.setattr(OperationStore,'create',create)
    exit=RegisteredExit(Config('provider_call',10,0,1000,8,8,20000,90),None,clock=lambda:100,
        output_limits=dict(model=1000,tool=1000,memory=1000),environment='local',
        registrations={'model.original':Registration('model',lambda argument:InvocationInput(argument,None))})
    # A client string imitating C's ID is data; the server still mints L's ID.
    prepared=exit.prepare_operation(None,binding,'original','model.original',
        sublimits.operation_id('owner-C').encode(),stage='answer')
    assert prepared.step.command.attempt_id.startswith('g2c1-'+sublimits.scope_hash('owner-L')+'-')
    assert prepared.step.command.operation_id.startswith('g2c1-'+sublimits.scope_hash('owner-L')+'-')
