"""Frozen lifecycle children get independent native checkpoint identities."""
from copy import deepcopy

import pytest

from deploy.hk.app_smoke_read import frozen_action
from runtime_adapter.contract import Unavailable


def plan():
    return dict(steps=[dict(gate_id='SM02',locale='zh',text='frozen question',nonce='a'*32),
        dict(gate_id='SM04',locale='zh',text=None,nonce='b'*32,read_actions=[
            dict(action='background_return',nonce='c'*32),dict(action='lock_return',nonce='d'*32)])])


def test_two_transitions_resolve_distinct_readonly_native_checkpoints():
    value=plan()
    first=frozen_action(value,'c'*32,'checkpoint');second=frozen_action(value,'d'*32,'checkpoint')
    assert first['nonce']!=second['nonce']and first['parent_nonce']==second['parent_nonce']=='b'*32
    assert first['read_action']=='background_return'and second['read_action']=='lock_return'
    assert first['locale']==second['locale']=='zh'and first['text']is second['text']is None
    assert frozen_action(value,'c'*32,'observe_read')['nonce']=='c'*32
    assert frozen_action(value,'a'*32,'observe')['text']=='frozen question'


@pytest.mark.parametrize('kind',['observe','inventory','input','artifact','wire_input','meter','fee'])
def test_read_child_never_selects_a_send_slot_or_paid_operation(kind):
    with pytest.raises(Unavailable,match='CANNOT_SEND'):frozen_action(plan(),'c'*32,kind)


def test_parent_checkpoint_cannot_stand_in_for_both_transitions():
    for kind in('checkpoint','observe_read'):
        with pytest.raises(Unavailable,match='CHILD_CHECKPOINT'):frozen_action(plan(),'b'*32,kind)
    assert frozen_action(plan(),'b'*32,'stop_new')['nonce']=='b'*32


@pytest.mark.parametrize('change',['duplicate_child','duplicate_parent','wrong_gate','missing_action','bad_nonce'])
def test_malformed_or_reused_plan_nonces_refuse_all_actions(change):
    value=plan();parent=value['steps'][1]
    if change=='duplicate_child':parent['read_actions'][1]['nonce']='c'*32
    elif change=='duplicate_parent':parent['read_actions'][0]['nonce']='a'*32
    elif change=='wrong_gate':parent['gate_id']='SM03'
    elif change=='missing_action':parent['read_actions'].pop()
    else:parent['read_actions'][0]['nonce']='bad'
    with pytest.raises(Unavailable):frozen_action(value,'a'*32,'checkpoint')
