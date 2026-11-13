from datetime import datetime,timezone
import json
import os

import pytest

from cj_api.local_app import ISSUER,scope_for
from cj_usage.authorization_budget import AuthorizationBudget,journal_state
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.sublimits import activate,scope_hash
from deploy.hk.manual_test_allocations import allocate_manual_tests
from deploy.hk import manual_test_allocations
from scripts.hk_sublimits import grants
from scripts import m4_budget_transfer as transfer
from cj_usage import authorization_budget as parent
from cj_usage.sublimits import snapshot,operation_id

OLD='m4-synthetic-demo-'+'a'*12
NEW='m4-synthetic-demo-'+'b'*12
EXPERIMENT='m4-synthetic-demo-'+'e'*12


def prepared(tmp_path):
    budget=AuthorizationBudget(tmp_path/'original',clock=lambda:datetime(2026,11,13,tzinfo=timezone.utc))
    budget.begin('retained-original','model',b'original unknown hold')
    activate(budget,grants(),{scope_hash(scope_for(ISSUER,OLD)):'A',scope_hash(scope_for(ISSUER,EXPERIMENT)):'E'})
    return budget


def state(budget):
    with budget.connect()as db:
        return (journal_state(db),db.execute('SELECT * FROM sublimit ORDER BY line').fetchall(),
            db.execute('SELECT * FROM scope_sublimit ORDER BY scope_hash').fetchall())


def test_append_uses_existing_parent_and_preserves_all_limits_and_holds(tmp_path):
    budget=prepared(tmp_path);before=state(budget);invited={OLD,NEW,EXPERIMENT}
    preview=allocate_manual_tests(budget,[OLD,NEW],invited)
    assert preview['unbound_before']==1 and not preview['applied'] and state(budget)==before
    result=allocate_manual_tests(budget,[OLD,NEW],invited,apply=True)
    after=state(budget)
    assert result['added']==1 and after[:2]==before[:2]
    assert (scope_hash(scope_for(ISSUER,NEW)),'A')in after[2]
    assert allocate_manual_tests(budget,[OLD,NEW],invited,apply=True)['added']==0
    assert state(budget)==after


def test_cannot_move_experiment_scope_or_partially_append_a_mixed_batch(tmp_path):
    budget=prepared(tmp_path);before=state(budget)
    with pytest.raises(BudgetUnknown,match='cannot_be_reassigned'):
        allocate_manual_tests(budget,[NEW,EXPERIMENT],{OLD,NEW,EXPERIMENT},apply=True)
    assert state(budget)==before


@pytest.mark.parametrize('subjects,invited',[([],set()),([NEW,NEW],{NEW}),([NEW],set()),
    (['untrusted-owner'],{'untrusted-owner'}),([NEW]*199,{NEW})])
def test_unqualified_or_duplicate_batch_is_rejected_before_any_allocation(tmp_path,subjects,invited):
    budget=prepared(tmp_path);before=state(budget)
    with pytest.raises(ValueError):allocate_manual_tests(budget,subjects,invited,apply=True)
    assert state(budget)==before


def test_hk_nonrestored_anchor_tracks_append_without_resetting_original_journal(tmp_path,monkeypatch):
    monkeypatch.delenv('CJ_M4_BUDGET_PRODUCER',raising=False)
    clock=lambda:datetime(2026,11,13,tzinfo=timezone.utc)
    original=AuthorizationBudget(tmp_path/'mac',clock=clock)
    original.begin('retained-original','model',b'original held operation')
    monkeypatch.setattr(transfer,'MAC_ROOT',original.root)
    monkeypatch.setattr(transfer,'HK_ROOT',tmp_path/'hk')
    monkeypatch.setattr(parent,'HK_JOURNAL_ROOT',tmp_path/'hk')
    monkeypatch.setattr(parent,'HK_ANCHOR',tmp_path/'control/adoption.json')
    package=tmp_path/'package.sqlite';digest=transfer.seal(original.path,package)
    monkeypatch.setenv('CJ_M4_BUDGET_PRODUCER',parent.HK_PRODUCER)
    monkeypatch.setenv('CJ_DEPLOY_TARGET','hk-beta')
    transfer.adopt(package,digest)
    budget=AuthorizationBudget(tmp_path/'hk',clock=clock,authorization_guard=lambda:None,demo=True)
    activate(budget,grants(),{scope_hash(scope_for(ISSUER,OLD)):'A'})
    before=state(budget)
    allocate_manual_tests(budget,[NEW],{OLD,NEW},apply=True)
    assert state(budget)[:2]==before[:2] and budget.ledger_id==original.ledger_id
    with budget.connect()as db:
        anchor=budget.require_producer(db)
        assert anchor['state']=='ADOPTED_SUBLIMITS_1' and anchor['sublimits_sha256']==snapshot(db)
    # A subsequent synthetic financial admission uses the same original A
    # attribution. No provider or supplier request is made by this test.
    attempt=operation_id(scope_for(ISSUER,NEW));budget.begin(attempt,'model',b'new synthetic native admission')
    with budget.connect()as db:
        assert db.execute('SELECT line FROM attempt_sublimit WHERE attempt_id=?',(attempt,)).fetchone()==('A',)


@pytest.mark.parametrize('kind',['mode','symlink','fifo','oversize','duplicate','extra-field'])
def test_unsafe_operator_manifest_stops_before_secret_or_budget_access(tmp_path,monkeypatch,kind):
    path=tmp_path/'manifest.json'
    value=json.dumps(dict(version='G2C-manual-test-allocation.1',subjects=[NEW]))
    if kind=='fifo':os.mkfifo(path,0o600)
    else:
        path.write_text(value);path.chmod(0o600)
        if kind=='mode':path.chmod(0o644)
        elif kind=='symlink':
            alias=tmp_path/'alias.json';alias.symlink_to(path);path=alias
        elif kind=='oversize':path.write_bytes(b'X'*65537)
        elif kind=='duplicate':path.write_text(value[:-1]+',"subjects":[]}')
        elif kind=='extra-field':path.write_text(value[:-1]+',"line":"E"}')
    def forbidden(*args,**kwargs):raise AssertionError('unsafe manifest reached secret loader')
    monkeypatch.setattr(manual_test_allocations,'load_secret_environment',forbidden)
    monkeypatch.setattr('sys.argv',['operator',str(path)])
    with pytest.raises((ValueError,OSError)):manual_test_allocations.main()
