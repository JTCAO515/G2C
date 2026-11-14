"""Actual local original fee store; controlled native MESSAGE/Meter readers."""
from datetime import datetime,timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cj_api.runtime_preparation_cost import PreparationCostInventory
from cj_api.runtime_preparation_lifecycle import PreparationLifecycle
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.sublimits import scope_hash
from runtime_adapter import Binding,Unavailable
from runtime_adapter.contract import encode,decode


@pytest.fixture
def lifecycle(tmp_path,monkeypatch):
    monkeypatch.setenv('CJ_M4_BUDGET_PRODUCER','codex-mac')
    budget=AuthorizationBudget(tmp_path/'fees',clock=lambda:datetime(2026,11,14,tzinfo=timezone.utc))
    token='producer-C';scope='preparation-C-owner'
    binding=Binding(scope,sha256(token.encode()).hexdigest(),budget.ledger_id,budget.producer)
    prefix='g2c1-'+scope_hash(scope)+'-'
    ids=[prefix+str(i)*32 for i in range(4)]
    mids=('prep-1','prep-2');state=dict(allowed=True,ack=True,jobs=[],failure=False)
    def receipt(marker):
        return dict(model_id='qwen3.8-flash',region='cn-beijing',
            endpoint='https://dashscope.aliyuncs.com/compatible-mode/v1',receipt_sha256=marker*64,
            usage=dict(prompt_tokens=10,completion_tokens=2,total_tokens=12))
    def guard(**args):
        assert args['binding']==binding and args['read_only']
        if not state['allowed']:raise Unavailable('REVOKED')
    def inventory(credential,mid):
        assert credential==token;i=mids.index(mid)
        return encode(dict(message_id=mid,run_id='run-'+mid,status='failed'if state['failure']else'completed',
            operations=[dict(operation_id='op-'+str(i),attempt_id=ids[i],kind='model',registration_id='model.fixture')]))
    def fee(credential,mid,op):
        assert credential==token;i=mids.index(mid)
        with budget.connect()as db:
            row=db.execute('SELECT kind,input_sha,state,receipt FROM attempt WHERE id=?',(ids[i],)).fetchone()
        return encode(dict(attempt_id=ids[i],ledger_id=budget.ledger_id,kind=row[0],actual_wire_input_sha256=row[1],state=row[2],receipt_utf8=row[3]))
    def visible(credential,mid):
        assert credential==token
        return encode(dict(message_id=mid,status='failed'if state['failure']else'completed',
            tail=dict(delivery_acknowledged=state['ack'],associated_history_jobs=state['jobs'])))
    originals=SimpleNamespace(budget=budget,inventory=inventory,fee=fee,
        meter=lambda *args:encode(dict(state='settled',receipt={'native':'controlled'})),visible_original=visible)
    costs=PreparationCostInventory(originals,SimpleNamespace(require=guard),binding,
        SimpleNamespace(key='a'*64),lambda:token,mids)
    directory=tmp_path/'lifecycle';directory.mkdir(mode=0o700)
    def build():return PreparationLifecycle(directory,costs)
    def prepare():
        for i in range(2):budget.begin(ids[i],'model',('original '+mids[i]).encode());budget.finish(ids[i],receipt(str(i)))
    return SimpleNamespace(build=build,budget=budget,state=state,ids=ids,prepare=prepare,
        directory=directory,receipt=receipt,costs=costs)


def test_interval_counts_all_original_scope_fees_and_restarts_without_recharge(lifecycle):
    journal=lifecycle.build();start=journal.begin(deadline=100);lifecycle.prepare()
    before=lifecycle.budget.inspect();closed=journal.close(deadline=100);record=decode(closed)
    assert record['evidence_status']=='COMPLETE' and record['manual_trip_action_coverage']=='UNRUN'
    assert record['unmapped_original_attempt_ids']==record['selected_attempts_outside_interval']==[]
    assert journal.read(deadline=100)==lifecycle.build().read(deadline=100)==closed
    assert lifecycle.budget.inspect()==before
    with pytest.raises(FileExistsError):lifecycle.build().begin(deadline=100)
    assert (lifecycle.directory/'start.json').read_bytes()==start


def test_unmapped_failed_unknown_background_attempt_is_not_dropped(lifecycle):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare()
    lifecycle.budget.begin(lifecycle.ids[2],'model',b'unmapped history extraction')
    record=decode(journal.close(deadline=100))
    assert record['evidence_status']=='UNKNOWN'
    assert record['unmapped_original_attempt_ids']==[lifecycle.ids[2]]
    assert lifecycle.budget.inspect()[-1]['state']=='INTENT'
    assert len(lifecycle.budget.inspect())==3


def test_selection_cannot_borrow_a_preexisting_attempt(lifecycle):
    lifecycle.prepare();journal=lifecycle.build();journal.begin(deadline=100)
    record=decode(journal.close(deadline=100))
    assert record['evidence_status']=='UNKNOWN'
    assert record['selected_attempts_outside_interval']==lifecycle.ids[:2]


@pytest.mark.parametrize('field,value',[('ack',False),('jobs',[{'job_id':'late','state':'completed'}])])
def test_missing_ack_or_uncollected_associated_history_is_unknown(lifecycle,field,value):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare();lifecycle.state[field]=value
    assert decode(journal.close(deadline=100))['evidence_status']=='UNKNOWN'


def test_other_owner_activity_and_later_new_work_do_not_rewrite_closed_interval(lifecycle):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare()
    lifecycle.budget.begin('other-owner-attempt','model',b'other owner')
    raw=journal.close(deadline=100)
    lifecycle.budget.begin(lifecycle.ids[3],'model',b'later independent work')
    assert lifecycle.build().read(deadline=100)==raw


def test_old_unrelated_unknown_settlement_does_not_become_preparation_cost(lifecycle):
    lifecycle.budget.begin(lifecycle.ids[2],'model',b'old unrelated unknown')
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare();raw=journal.close(deadline=100)
    lifecycle.budget.finish(lifecycle.ids[2],lifecycle.receipt('c'))
    assert journal.read(deadline=100)==raw
    assert len(decode(raw)['cost_inventory']['attempts'])==2


def test_unknown_close_ack_is_query_only_and_revocation_withholds(lifecycle):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare()
    with patch('cj_api.runtime_preparation_lifecycle.os.fsync',side_effect=[None,None,OSError('ACK unknown')]):
        with pytest.raises(OSError):journal.close(deadline=100)
    assert decode(lifecycle.build().read(deadline=100))['evidence_status']=='COMPLETE'
    with pytest.raises(FileExistsError):lifecycle.build().close(deadline=100)
    lifecycle.state['allowed']=False
    with pytest.raises(Unavailable,match='REVOKED'):journal.read(deadline=100)


def test_failed_message_still_keeps_all_actual_attempts(lifecycle):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare();lifecycle.state['failure']=True
    record=decode(journal.close(deadline=100))
    assert len(record['cost_inventory']['attempts'])==2
    assert all(row['status']=='failed'for row in record['message_closure'])
    # COMPLETE means this explicitly named inventory coverage, never task PASS.
    assert record['manual_trip_action_coverage']=='UNRUN'


def test_unscoped_legacy_attempts_never_prove_scope_interval_coverage(lifecycle):
    lifecycle.ids[:2]=['legacy-0','legacy-1']
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare()
    record=decode(journal.close(deadline=100))
    assert record['evidence_status']=='UNKNOWN'
    assert record['selected_attempts_outside_interval']==['legacy-0','legacy-1']


@pytest.mark.parametrize('field,value',[('evidence_status','COMPLETE'),('unmapped_original_attempt_ids',[]),
    ('manual_trip_action_coverage','PASS'),('new_charge_attempts',False)])
def test_persisted_coverage_cannot_upgrade_unknown_or_hide_unmapped_attempts(lifecycle,field,value):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare()
    lifecycle.budget.begin(lifecycle.ids[2],'model',b'unknown original')
    record=decode(journal.close(deadline=100));record[field]=value
    (lifecycle.directory/'close.json').write_bytes(encode(record))
    with pytest.raises(ValueError):journal.read(deadline=100)


def test_deleted_unmapped_row_and_recomputed_status_cannot_upgrade_original_range(lifecycle):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare()
    lifecycle.budget.begin(lifecycle.ids[2],'model',b'unmapped unknown')
    original=decode(journal.close(deadline=100));assert original['evidence_status']=='UNKNOWN'
    forged=decode(encode(original))
    forged['snapshot']['attempts']=[r for r in forged['snapshot']['attempts']if r['attempt_id']!=lifecycle.ids[2]]
    forged['unmapped_original_attempt_ids']=[];forged['evidence_status']='COMPLETE'
    (lifecycle.directory/'close.json').write_bytes(encode(forged))
    with pytest.raises(ValueError,match='ORIGINAL_CUTOFF_CHANGED'):journal.read(deadline=100)
    assert len(lifecycle.budget.inspect())==3 and lifecycle.budget.inspect()[-1]['state']=='INTENT'


def test_even_changed_end_subset_is_checked_against_native_original_range(lifecycle):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare()
    lifecycle.budget.begin(lifecycle.ids[2],'model',b'unmapped unknown')
    record=decode(journal.close(deadline=100));end=decode((lifecycle.directory/'end.json').read_bytes())
    end['snapshot']['attempts']=[r for r in end['snapshot']['attempts']if r['attempt_id']!=lifecycle.ids[2]]
    record['snapshot']=end['snapshot'];record['end_sha256']=sha256(encode(end)).hexdigest()
    record['unmapped_original_attempt_ids']=[];record['evidence_status']='COMPLETE'
    (lifecycle.directory/'end.json').write_bytes(encode(end));(lifecycle.directory/'close.json').write_bytes(encode(record))
    with pytest.raises(Unavailable,match='ORIGINAL_RANGE_CHANGED'):journal.read(deadline=100)


def test_end_ack_unknown_retains_cutoff_and_never_recreates_interval(lifecycle):
    journal=lifecycle.build();journal.begin(deadline=100);lifecycle.prepare()
    with patch('cj_api.runtime_preparation_lifecycle.os.fsync',side_effect=OSError('end ACK unknown')):
        with pytest.raises(OSError):journal.close(deadline=100)
    assert (lifecycle.directory/'end.json').exists() and not (lifecycle.directory/'close.json').exists()
    with pytest.raises(Unavailable,match='NOT_RECORDED'):journal.read(deadline=100)
    with pytest.raises(FileExistsError):journal.close(deadline=100)
    assert len(lifecycle.budget.inspect())==2
