"""Real local financial journal + controlled protected accounting readers."""
from datetime import datetime,timezone
from hashlib import sha256
from types import SimpleNamespace

import pytest

from cj_api.runtime_preparation_cost import PreparationCostInventory
from cj_usage.authorization_budget import AuthorizationBudget,CNY_SCALE
from runtime_adapter import Binding,Invalid,Unavailable
from runtime_adapter.contract import decode,encode


@pytest.fixture
def context(tmp_path,monkeypatch):
    monkeypatch.setenv('CJ_M4_BUDGET_PRODUCER','codex-mac')
    budget=AuthorizationBudget(tmp_path/'original-fees',clock=lambda:datetime(2026,11,14,tzinfo=timezone.utc))
    def supplier_receipt(marker):
        return dict(model_id='qwen3.8-flash',region='cn-beijing',
            endpoint='https://dashscope.aliyuncs.com/compatible-mode/v1',receipt_sha256=marker*64,
            usage=dict(prompt_tokens=10,completion_tokens=2,total_tokens=12))
    budget.begin('attempt0','model',b'first original input');budget.finish('attempt0',supplier_receipt('a'))
    budget.begin('attempt1','model',b'second original input')
    token='local-producer-original-token';binding=Binding('producer-C-owner',sha256(token.encode()).hexdigest(),budget.ledger_id,budget.producer)
    pins=SimpleNamespace(key='b'*64)
    state=dict(allowed=True,missing_fee=set(),missing_meter=set(),failure=None,after_fee=None,after_fee_read_at=1,reads=0)
    def guard(**kwargs):
        assert kwargs==dict(binding=binding,pins_sha256=pins.key,purpose='query',deadline=100,read_only=True)
        if not state['allowed']:raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE')
    messages=('m-completed','m-failed')
    def inventory(credential,mid):
        assert credential==token
        i=messages.index(mid)
        return encode(dict(message_id=mid,run_id='run'+str(i),status='completed'if i==0 else'failed',
            operations=[dict(operation_id='op'+str(i),attempt_id='attempt'+str(i),
                registration_id='model.answer',kind='model')]))
    def fee(credential,mid,op):
        if state['failure']is not None:raise state['failure']
        if op in state['missing_fee']:raise Unavailable('ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE')
        state['reads']+=1
        with budget.connect()as db:
            row=db.execute('SELECT kind,input_sha,state,receipt FROM attempt WHERE id=?',('attempt'+op[-1],)).fetchone()
        raw=encode(dict(attempt_id='attempt'+op[-1],ledger_id=budget.ledger_id,kind=row[0],
            actual_wire_input_sha256=row[1],state=row[2],receipt_utf8=row[3]))
        if state['reads']==state['after_fee_read_at']and state['after_fee']is not None:state['after_fee']()
        return raw
    def meter(credential,mid,op):
        if op in state['missing_meter']:raise Unavailable('ORIGINAL_METER_UNAVAILABLE')
        return encode(dict(state='settled'if op=='op0'else'unknown',receipt={'actual':1}if op=='op0'else None))
    originals=SimpleNamespace(budget=budget,inventory=inventory,fee=fee,meter=meter)
    def build(mids=messages,bound=binding,supplier=lambda:token):
        return PreparationCostInventory(originals,SimpleNamespace(require=guard),bound,pins,supplier,mids)
    return SimpleNamespace(budget=budget,binding=binding,originals=originals,state=state,
        build=build,receipt=supplier_receipt)


def test_failed_and_unknown_attempt_cost_is_retained_and_never_recharged(context):
    before=context.budget.inspect();raw=context.build().collect(deadline=100);report=decode(raw)
    assert len(report['attempts'])==2 and report['messages'][1]['status']=='failed'
    assert report['accounting_status']=='UNKNOWN'and report['totals']==dict(attempts=2,settled=1,
        known_estimated_cny_1e7=134,unpriced_attempts=1,known_parent_conservative_hold_cny_1e7=CNY_SCALE,unknown_hold_attempts=0)
    assert report['actual_supplier_paid']=='UNKNOWN'and report['new_charge_attempts']==0
    assert report['observed_ledger_before']==report['observed_ledger_after']
    assert context.build().collect(deadline=100)==raw and context.budget.inspect()==before
    assert b'original input'not in raw and b'receipt_utf8'not in raw


@pytest.mark.parametrize('field',['missing_fee','missing_meter'])
def test_missing_first_component_does_not_hide_other_attempts(context,field):
    context.state[field].add('op0')
    report=decode(context.build().collect(deadline=100))
    assert len(report['attempts'])==2 and report['accounting_status']=='UNKNOWN'
    assert report['attempts'][1]['financial_state']=='INTENT'
    assert report['attempts'][1]['parent_conservative_hold_cny_1e7']==CNY_SCALE
    assert report['missing'][0]['attempt_id']=='attempt0'
    if field=='missing_fee':assert report['totals']['unknown_hold_attempts']==1


@pytest.mark.parametrize('error',[Unavailable('ORIGINAL_AUTH_UNAVAILABLE'),ValueError('controlled programming error')])
def test_auth_and_unexpected_errors_are_not_missing_or_zero_cost(context,error):
    context.state['failure']=error
    with pytest.raises(type(error)):context.build().collect(deadline=100)


def test_current_source_and_exact_session_are_required(context):
    context.state['allowed']=False
    with pytest.raises(Unavailable):context.build().collect(deadline=100)
    context.state['allowed']=True
    with pytest.raises(Unavailable,match='SESSION_CHANGED'):
        context.build(supplier=lambda:'another-token').collect(deadline=100)


def test_late_original_fee_transition_withholds_inconsistent_point_read(context):
    context.state['after_fee_read_at']=2
    context.state['after_fee']=lambda:context.budget.finish('attempt1',context.receipt('c'))
    with pytest.raises(Unavailable,match='SOURCE_CHANGED'):context.build().collect(deadline=100)
    assert len(context.budget.inspect())==2
    assert context.budget.inspect()[1]['state']=='RECEIVED'


def test_unrelated_parent_activity_is_observed_not_relabelled_as_preparation_cost(context):
    context.state['after_fee']=lambda:context.budget.begin('unrelated','model',b'other original scope')
    report=decode(context.build().collect(deadline=100))
    assert report['observed_ledger_before']!=report['observed_ledger_after']
    assert len(report['attempts'])==2 and report['totals']['known_estimated_cny_1e7']==134


@pytest.mark.parametrize('mids',[(),('same','same'),('ok',[])])
def test_declared_configuration_requires_bounded_unique_message_ids(context,mids):
    with pytest.raises(Invalid):context.build(mids=mids)


def test_frozen_cost_survives_unrelated_fees_without_recharging(context):
    reader=context.build();raw=reader.collect(deadline=100)
    context.budget.begin('consumer-new','model',b'independent consumer request')
    context.budget.finish('consumer-new',context.receipt('d'))
    before=context.budget.inspect()
    assert reader.collect(deadline=100)!=raw
    assert reader.verify_frozen(raw,deadline=100)==raw
    assert context.build().verify_frozen(raw,deadline=100)==raw
    assert context.budget.inspect()==before


def test_frozen_cost_requires_explicit_reconciliation_of_selected_unknown(context):
    reader=context.build();raw=reader.collect(deadline=100)
    context.budget.finish('attempt1',context.receipt('c'))
    with pytest.raises(Unavailable,match='RECONCILE_ORIGINAL'):
        reader.verify_frozen(raw,deadline=100)
    assert decode(raw)['accounting_status']=='UNKNOWN'
    assert len(context.budget.inspect())==2


def test_frozen_cost_rechecks_current_authority_session_and_original_hashes(context):
    raw=context.build().collect(deadline=100)
    context.state['allowed']=False
    with pytest.raises(Unavailable):context.build().verify_frozen(raw,deadline=100)
    context.state['allowed']=True
    with pytest.raises(Unavailable,match='SESSION_CHANGED'):
        context.build(supplier=lambda:'changed').verify_frozen(raw,deadline=100)
    changed=decode(raw);changed['totals']['attempts']=0
    with pytest.raises(Unavailable,match='RECONCILE_ORIGINAL'):
        context.build().verify_frozen(encode(changed),deadline=100)
    changed=decode(raw);changed['binding_sha256']='c'*64
    with pytest.raises(Invalid,match='FROZEN_BINDING'):
        context.build().verify_frozen(encode(changed),deadline=100)


def test_retained_cost_restarts_and_unknown_ack_is_read_only(context,tmp_path):
    from cj_api.runtime_preparation_cost import FrozenPreparationCost
    from unittest.mock import patch
    directory=tmp_path/'frozen';directory.mkdir(mode=0o700)
    store=FrozenPreparationCost(directory,context.build())
    with patch('cj_api.runtime_preparation_cost.os.fsync',side_effect=OSError('ACK unknown')):
        with pytest.raises(OSError):store.freeze(deadline=100)
    path=directory/'cost.json';raw=path.read_bytes()
    assert path.stat().st_mode&0o777==0o600
    context.budget.begin('independent-E','model',b'actual other request')
    before=context.budget.inspect()
    restarted=FrozenPreparationCost(directory,context.build())
    assert restarted.read(deadline=100)==raw
    assert restarted.freeze(deadline=100)==raw
    assert path.read_bytes()==raw and context.budget.inspect()==before
    path.write_bytes(b'{')
    with pytest.raises(ValueError):restarted.freeze(deadline=100)
    assert path.read_bytes()==b'{' and context.budget.inspect()==before


def test_cost_directory_replacement_withholds_original(context,tmp_path):
    from cj_api.runtime_preparation_cost import FrozenPreparationCost
    directory=tmp_path/'frozen';directory.mkdir(mode=0o700)
    store=FrozenPreparationCost(directory,context.build());store.freeze(deadline=100)
    directory.rename(tmp_path/'retained');directory.mkdir(mode=0o700)
    with pytest.raises(Unavailable,match='DIRECTORY_CHANGED'):store.read(deadline=100)
