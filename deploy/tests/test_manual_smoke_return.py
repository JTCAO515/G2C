"""Manual startup-failure return uses original native accounting, not a fake close."""
from copy import deepcopy
import json

import pytest

from backend.usage.tests.test_sublimits import allocated
from deploy.tests.test_app_smoke_restore import request_for
from deploy.tests.test_app_smoke_ceiling import state
from deploy.hk import app_smoke_restore_worker as worker
from deploy.hk import manual_smoke_return as host
from deploy.hk.app_smoke_ceiling import BASELINE
from cj_usage import sublimits
from cj_usage.authorization_budget import journal_state


@pytest.fixture
def return_directory(tmp_path):
    directory=tmp_path/'return';directory.mkdir()
    return directory


def manual_request(budget):
    old=request_for(budget)
    with budget.connect()as db:
        count,digest=journal_state(db)
    old['version']=worker.MANUAL_VERSION
    old['closed_manual_sha256']=old.pop('closed_capture_sha256')
    old['expected_ledger']=dict(count=count,sha256=digest)
    return old


def fixture(budget):
    request=manual_request(budget);anchor=request['expected_ledger']
    plan=dict(window_id='manual14-original',source='a'*40,image='sha256:'+'b'*64,
        tool_image='sha256:'+'c'*64,restricted_policy_sha256=request['expected_policy_sha256'],
        close_sha256=request['closed_manual_sha256'],ledger_id=budget.ledger_id,
        producer_id=budget.producer,mounts={'api':{},'worker':{}})
    values={role:dict(Id=role,Image=plan['image'],Config=dict(Cmd=[role],
        Labels={'org.opencontainers.image.revision':plan['source']}),
        State=dict(Running=True,Health=dict(Status='healthy')),Mounts=[])for role in('api','worker')}
    cut=dict(stage='CUTOVER_PASS',source=plan['source'],image=plan['image'],ledger_unchanged=True,
        ledger_before=anchor,ledger_after=anchor,pending=0,active=0,background_states={},memory_states={'unknown':2})
    closed=dict(version='B-manual14-close.1',state='CLOSED_FAIL_ROLLED_BACK',lease_id=plan['window_id'],
        message_delta=0,standing_budget_restored=False,verdict='FAIL_LOGIN_UI',
        rollback=dict(state='ROLLBACK_VERIFIED',cutover=cut))
    stopped=dict(state='STOP_NEW',verdict='FAIL_LOGIN_UI')
    def proof():
        with budget.connect()as db:count,digest=journal_state(db)
        return dict(global_pending=0,global_active=0,background_states={},memory_states={'unknown':2},
            ledger=dict(count=count,sha256=digest))
    return plan,values,closed,stopped,request['restriction'],proof


def test_native_manual_return_retains_original_policy_usage_unknown_holds_and_old_version(allocated):
    budget,_=allocated;r=manual_request(budget);before=state(budget)
    result=worker.restore(budget,r)
    assert result['version']=='G2C-App-manual-smoke-closed-standing-result.1'
    assert result['closed_manual_sha256']==r['closed_manual_sha256']and 'closed_capture_sha256'not in result
    assert result['state']=='READONLY_NOT_RESTORED'and state(budget)==before
    result=worker.restore(budget,dict(r,apply=True))
    assert result['state']=='C_ORIGINAL_STANDING_RESTORED_ACKED'
    assert sublimits.read(budget)['C']['policy']==BASELINE
    assert state(budget)==before and result['attempts_refunded_or_deleted']==0
    with pytest.raises(ValueError,match='policy changed'):worker.restore(budget,dict(r,apply=True))


@pytest.mark.parametrize('anchor',[None,{},dict(count=True,sha256='a'*64),dict(count=-1,sha256='a'*64),
    dict(count=0,sha256='bad'),dict(count=0,sha256='A'*64),dict(count=0,sha256='a'*64,extra=1)])
def test_native_missing_or_invalid_manual_anchor_never_changes_C(allocated,anchor):
    budget,_=allocated;r=manual_request(budget);before=sublimits.read(budget)
    with pytest.raises(ValueError):worker.restore(budget,dict(r,expected_ledger=anchor,apply=True))
    assert sublimits.read(budget)==before


def test_native_late_original_attempt_refuses_manual_return_without_refunding_it(allocated):
    budget,_=allocated;r=manual_request(budget)
    budget.begin(sublimits.operation_id('owner-C'),'model',b'late original unknown')
    before=state(budget);policy=sublimits.read(budget)['C']['policy']
    with pytest.raises(ValueError,match='manual-close ledger changed'):
        worker.restore(budget,dict(r,apply=True))
    assert state(budget)==before and sublimits.read(budget)['C']['policy']==policy


def test_old_native_version_cannot_accept_new_manual_fields(allocated):
    budget,_=allocated;r=manual_request(budget);before=state(budget)
    with pytest.raises(ValueError):worker.restore(budget,dict(r,version=worker.VERSION,apply=True))
    assert state(budget)==before


def test_host_real_manual_close_and_native_sqlite_return_are_one_bounded_operation(allocated,return_directory):
    budget,_=allocated;plan,values,closed,stopped,restriction,proof=fixture(budget);before=state(budget)
    native=lambda request:worker.restore(budget,request)
    result=host.perform(return_directory,plan,closed,stopped,restriction,values.__getitem__,proof,native,apply=False)
    assert result['state']=='READONLY_NOT_RESTORED'and not list(return_directory.iterdir())
    result=host.perform(return_directory,plan,closed,stopped,restriction,values.__getitem__,proof,native,apply=True)
    assert result['state']=='C_ORIGINAL_STANDING_RESTORED_ACKED'and state(budget)==before
    assert json.loads((return_directory/'manual-standing-return.result.json').read_bytes())==result


@pytest.mark.parametrize('change',[dict(version='G2C-App-smoke-close.1'),dict(state='ACTIVE'),
    dict(lease_id='other-window'),dict(message_delta=1),dict(message_delta=False),
    dict(standing_budget_restored=True),dict(verdict='PASS')])
def test_manual_evidence_mismatch_cannot_reach_native_return(allocated,return_directory,change):
    budget,_=allocated;plan,values,closed,stopped,restriction,proof=fixture(budget);calls=[]
    with pytest.raises(ValueError):host.perform(return_directory,plan,dict(closed,**change),stopped,restriction,
        values.__getitem__,proof,lambda request:calls.append(request),apply=True)
    assert calls==[]and not list(return_directory.iterdir())


@pytest.mark.parametrize('change',[dict(source='f'*40),dict(image='sha256:'+'f'*64),dict(pending=1),
    dict(active=1),dict(background_states={'running':1}),dict(memory_states={'inflight':1}),
    dict(ledger_after={'count':1234,'sha256':'f'*64})])
def test_wrong_or_unsettled_rollback_is_not_a_manual_close(allocated,return_directory,change):
    budget,_=allocated;plan,values,closed,stopped,restriction,proof=fixture(budget);calls=[]
    closed=deepcopy(closed);closed['rollback']['cutover'].update(change)
    with pytest.raises(ValueError):host.perform(return_directory,plan,closed,stopped,restriction,
        values.__getitem__,proof,lambda request:calls.append(request),apply=True)
    assert calls==[]and not list(return_directory.iterdir())


def test_current_activity_or_attached_collector_blocks_manual_return(allocated,return_directory):
    budget,_=allocated;plan,values,closed,stopped,restriction,proof=fixture(budget);calls=[]
    def busy():return dict(proof(),global_active=1)
    with pytest.raises(ValueError,match='empty in-flight'):host.perform(return_directory,plan,closed,stopped,
        restriction,values.__getitem__,busy,lambda request:calls.append(request),apply=True)
    values['worker']['Config']['Cmd']=['worker','--app-smoke-manifest','/policy']
    with pytest.raises(ValueError,match='default roles'):host.perform(return_directory,plan,closed,stopped,
        restriction,values.__getitem__,proof,lambda request:calls.append(request),apply=True)
    assert calls==[]and not list(return_directory.iterdir())


def test_unknown_native_ack_preserves_intent_and_cannot_be_replayed(allocated,return_directory):
    budget,_=allocated;plan,values,closed,stopped,restriction,proof=fixture(budget);calls=[]
    def unknown(request):calls.append(request);raise TimeoutError('native ACK unknown')
    for _ in range(2):
        with pytest.raises((TimeoutError,FileExistsError)):host.perform(return_directory,plan,closed,stopped,
            restriction,values.__getitem__,proof,unknown,apply=True)
    assert len(calls)==1 and(return_directory/'manual-standing-return.intent.json').exists()
    assert not(return_directory/'manual-standing-return.result.json').exists()


def test_return_tool_is_pinned_networkless_and_never_executes_in_old_worker():
    command=host.tool_command(dict(tool_image='sha256:'+'a'*64))
    assert command[:2]==['docker','run']and '--network=none'in command and '--pull=never'in command
    assert command[-4:]==['sha256:'+'a'*64,'-B','-m','deploy.hk.app_smoke_restore_worker']
    assert all('api.env'not in part and 'operator.env'not in part for part in command)
    assert str(host.ROOT/'worker.env')+':/run/secrets/worker.env:ro'in command
