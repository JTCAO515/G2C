"""Standing restore after actual return: original journal/control integration."""
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from backend.usage.tests.test_sublimits import allocated,received
from deploy.tests.test_app_smoke_ceiling import setup,state
from deploy.hk.app_smoke_ceiling import restrict,BASELINE
from deploy.hk import app_smoke_restore_worker as worker
from deploy.hk import app_smoke_restore as host
from cj_usage import sublimits
from cj_usage.metered_exit import BudgetUnknown


def request_for(budget):
    limited=restrict(budget,dict(setup(budget),apply=True))
    return dict(version=worker.VERSION,restriction=limited,ledger_id=budget.ledger_id,
        producer_id=budget.producer,expected_policy_sha256=sha256(sublimits.policy(limited['restricted_policy']).encode()).hexdigest(),
        closed_capture_sha256='a'*64,apply=False)


def test_restore_exact_original_C100_retains_all_old_and_window_unknown_holds(allocated):
    budget,anchor=allocated;r=request_for(budget)
    budget.begin(sublimits.operation_id('owner-C'),'model',b'ended window unknown')
    before=state(budget);restricted=sublimits.read(budget)['C']['policy']
    assert worker.restore(budget,r)['state']=='READONLY_NOT_RESTORED'
    assert sublimits.read(budget)['C']['policy']==restricted and state(budget)==before
    result=worker.restore(budget,dict(r,apply=True))
    assert result['state']=='C_ORIGINAL_STANDING_RESTORED_ACKED'and result['attempts_refunded_or_deleted']==0
    assert sublimits.read(budget)['C']['policy']==BASELINE and state(budget)==before
    with pytest.raises(ValueError,match='policy changed'):worker.restore(budget,dict(r,apply=True))


@pytest.mark.parametrize('change',[dict(expected_policy_sha256='f'*64),dict(ledger_id='different'),dict(producer_id='different')])
def test_wrong_original_reference_cannot_restore_any_policy(allocated,change):
    budget,_=allocated;r=request_for(budget);before=sublimits.read(budget)
    with pytest.raises(ValueError):worker.restore(budget,dict(r,**change,apply=True))
    assert sublimits.read(budget)==before


def test_lost_native_control_ACK_is_not_a_restore_permission_to_repeat(allocated,monkeypatch):
    from cj_usage import authorization_budget as parent
    budget,anchor=allocated;r=request_for(budget);original=parent.save_anchor
    def fail(value):
        if value['state']==sublimits.ADOPTED:raise OSError('lost restore ACK')
        original(value)
    monkeypatch.setattr(parent,'save_anchor',fail)
    with pytest.raises(OSError):worker.restore(budget,dict(r,apply=True))
    assert json.loads(anchor.read_text())['state']=='WRITE_INTENT'
    with pytest.raises(BudgetUnknown):worker.restore(budget,dict(r,apply=True))


def fixture():
    plan=dict(source='a'*40,image='sha256:'+'b'*64,restricted_policy_sha256='c'*64,close_sha256='d'*64,
        ledger_id='original',producer_id='producer',mounts={'api':{},'worker':{}})
    values={role:dict(Id=role,Image=plan['image'],Config=dict(Cmd=[role],Labels={'org.opencontainers.image.revision':plan['source']}),
        State=dict(Running=True,Health=dict(Status='healthy')),Mounts=[])for role in('api','worker')}
    closed=dict(version='G2C-App-smoke-close.1',state='DEFAULT_ROLES_RESTORED',ledger_before={'count':1232},
        ledger_after={'count':1232},budget_restored=False)
    return plan,values,closed


def test_host_actual_collector_blocks_native_restore_even_with_closed_metadata(tmp_path):
    plan,values,closed=fixture();values['worker']['Config']['Cmd']=['worker','--app-smoke-manifest','/policy']
    calls=[]
    with pytest.raises(ValueError,match='default roles'):
        host.perform(tmp_path,plan,{},closed,lambda role:values[role],lambda *args:calls.append(args),apply=True)
    assert calls==[]and not(tmp_path/'standing-restore.intent.json').exists()


def test_host_complete_mount_drift_cannot_be_whitelisted_by_close_receipt(tmp_path):
    plan,values,closed=fixture();values['api']['Mounts']=[dict(Destination='/unexpected',Source='/private',RW=True)]
    with pytest.raises(ValueError,match='mounts'):
        host.perform(tmp_path,plan,{},closed,lambda role:values[role],lambda *args:None,apply=True)


def test_host_unknown_native_restore_keeps_one_intent_and_never_retries(tmp_path):
    plan,values,closed=fixture();calls=[]
    def fail(worker_id,request):calls.append(request);raise TimeoutError('original native restore unknown')
    for _ in range(2):
        with pytest.raises((TimeoutError,FileExistsError)):
            host.perform(tmp_path,plan,{},closed,lambda role:values[role],fail,apply=True)
    assert len(calls)==1 and(tmp_path/'standing-restore.intent.json').exists()
    assert not(tmp_path/'standing-restore.result.json').exists()


def test_host_restore_success_only_after_closed_receipt_and_stable_defaults(tmp_path):
    plan,values,closed=fixture();calls=[]
    def native(worker_id,request):
        calls.append(request)
        assert worker_id=='worker'and request['closed_capture_sha256']==plan['close_sha256']
        return dict(state='C_ORIGINAL_STANDING_RESTORED_ACKED',attempts_refunded_or_deleted=0)
    result=host.perform(tmp_path,plan,{},closed,lambda role:values[role],native,apply=True)
    assert len(calls)==1 and calls[0]['apply']is True
    assert json.loads((tmp_path/'standing-restore.result.json').read_bytes())==result


def test_host_cannot_restore_with_unconfirmed_close_or_changed_role_after_mutation(tmp_path):
    plan,values,closed=fixture();calls=[]
    with pytest.raises(ValueError,match='formal close'):
        host.perform(tmp_path,plan,{},dict(closed,state='CLOSING'),lambda role:values[role],lambda *args:calls.append(args),apply=True)
    assert calls==[]
    def native(worker_id,request):
        values['worker']['Id']='different-worker'
        return dict(state='C_ORIGINAL_STANDING_RESTORED_ACKED')
    with pytest.raises(ValueError,match='roles changed'):
        host.perform(tmp_path,plan,{},closed,lambda role:values[role],native,apply=True)
    assert(tmp_path/'standing-restore.intent.json').exists()and not(tmp_path/'standing-restore.result.json').exists()
