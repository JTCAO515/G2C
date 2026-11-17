"""Real local accounting after a stopped manual business window; no cloud calls."""
from copy import deepcopy
from hashlib import sha256

import pytest

from backend.usage.tests.test_sublimits import allocated,received
from cj_usage import sublimits
from cj_usage.authorization_budget import journal_state
from deploy.hk import manual_smoke_return as host
from deploy.hk import app_smoke_restore_worker as worker
from deploy.hk.app_smoke_ceiling import restrict,BASELINE
from deploy.tests.test_app_smoke_ceiling import setup,state


def fixture(budget,*,verdict='PASS',count=8):
    restriction=restrict(budget,dict(setup(budget),profile='standard',apply=True))
    plan=dict(version=host.BUSINESS_VERSION,window_id='new-manual14',subject='owner-C',
        tested_source='a'*40,tested_image='sha256:'+'b'*64,
        source='a'*40 if verdict=='PASS'else'f'*40,
        image='sha256:'+('b'if verdict=='PASS'else'f')*64,
        tool_image='sha256:'+'c'*64,close_sha256='d'*64,
        restricted_policy_sha256=sha256(sublimits.policy(restriction['restricted_policy']).encode()).hexdigest(),
        ledger_id=budget.ledger_id,producer_id=budget.producer,mounts={'api':{},'worker':{}})
    before=dict(subject=plan['subject'],messages=[dict(message_id='retained-original',locale='zh')])
    after=deepcopy(before)
    for index in range(count):
        attempt=sublimits.operation_id('owner-C');budget.begin(attempt,'model',b'original manual operation')
        if verdict!='UNKNOWN'or index<count-1:budget.finish(attempt,received('manual-'+str(index)))
        after['messages'].append(dict(message_id='actual-'+str(index),locale='zh'if index<4 else'en'))
    def proof():
        with budget.connect()as db:n,digest=journal_state(db)
        return dict(global_pending=0,global_active=0,background_states={},memory_states={'unknown':2},
            ledger=dict(count=n,sha256=digest))
    anchor=proof()['ledger']
    closed=dict(version='B-manual14-close.2',lease_id=plan['window_id'],verdict=verdict,
        state='CLOSED_PASS'if verdict=='PASS'else'CLOSED_FAIL_ROLLED_BACK',
        standing_budget_restored=False,tested_source=plan['tested_source'],tested_image=plan['tested_image'],
        ledger_before=restriction['original_ledger'],ledger_after=anchor,
        message_delta=count,message_ids=['actual-'+str(i)for i in range(count)],rollback=None)
    if verdict!='PASS':
        closed['rollback']=dict(state='ROLLBACK_VERIFIED',cutover=dict(stage='CUTOVER_PASS',
            source=plan['source'],image=plan['image'],ledger_unchanged=True,
            ledger_before=anchor,ledger_after=anchor,pending=0,active=0,
            background_states={},memory_states={'unknown':2}))
    values={role:dict(Id=role,Image=plan['image'],Config=dict(Cmd=[role],
        Labels={'org.opencontainers.image.revision':plan['source']}),
        State=dict(Running=True,Health=dict(Status='healthy')),Mounts=[])for role in('api','worker')}
    return plan,closed,dict(state='STOP_NEW',verdict=verdict),restriction,values,proof,before,after


def perform(directory,budget,data,*,apply=True,native=None):
    plan,closed,stopped,restriction,values,proof,before,after=data
    return host.perform(directory,plan,closed,stopped,restriction,values.__getitem__,proof,
        native or(lambda request:worker.restore(budget,request)),apply=apply,
        before_metadata=before,after_metadata=after)


@pytest.mark.parametrize('verdict,count',[('PASS',8),('FAIL',3),('UNKNOWN',2),('FAIL',0)])
def test_actual_business_close_returns_only_original_policy_and_keeps_every_fee(allocated,tmp_path,verdict,count):
    budget,_=allocated;data=fixture(budget,verdict=verdict,count=count);directory=tmp_path/'return';directory.mkdir()
    before=state(budget);attempts=budget.inspect();restricted=sublimits.read(budget)['C']['policy']
    assert perform(directory,budget,data,apply=False)['state']=='READONLY_NOT_RESTORED'
    assert state(budget)==before and sublimits.read(budget)['C']['policy']==restricted
    result=perform(directory,budget,data)
    assert result['state']=='C_ORIGINAL_STANDING_RESTORED_ACKED'
    assert sublimits.read(budget)['C']['policy']==BASELINE
    assert state(budget)==before and budget.inspect()==attempts
    assert result['attempts_refunded_or_deleted']==0 and result['ended_window']=='REMAINS_CLOSED'
    with pytest.raises((ValueError,FileExistsError)):perform(directory,budget,data)


@pytest.mark.parametrize('change',[dict(version='G2C-App-smoke-close.1'),dict(state='ACTIVE'),
    dict(lease_id='other'),dict(standing_budget_restored=True),dict(message_delta=True),
    dict(message_delta=7),dict(message_ids=['actual-0']*8),dict(message_ids=['other']),
    dict(ledger_before={'count':0,'sha256':'f'*64}),dict(ledger_after={'count':0,'sha256':'f'*64}),
    dict(ledger_after={'count':True,'sha256':'f'*64}),dict(ledger_after={'count':1,'sha256':'bad'}),
    dict(tested_source='f'*40),dict(tested_image='sha256:'+'f'*64),dict(verdict='UNKNOWN')])
def test_forged_or_incomplete_business_close_never_reaches_financial_writer(allocated,tmp_path,change):
    budget,_=allocated;data=list(fixture(budget));data[1]=dict(data[1],**change);calls=[];before=state(budget)
    with pytest.raises(ValueError):perform(tmp_path,budget,data,native=lambda request:calls.append(request))
    assert calls==[]and state(budget)==before


@pytest.mark.parametrize('kind',['foreign','duplicate','deleted','rewritten','unlisted','too_many','one_locale'])
def test_full_original_inventory_cannot_be_truncated_or_replaced(allocated,tmp_path,kind):
    budget,_=allocated;data=list(fixture(budget));after=data[-1]
    if kind=='foreign':after['subject']='other'
    elif kind=='duplicate':after['messages'].append(deepcopy(after['messages'][-1]))
    elif kind=='deleted':after['messages'].pop(0)
    elif kind=='rewritten':after['messages'][0]['locale']='en'
    elif kind=='unlisted':after['messages'].append(dict(message_id='not-in-close',locale='en'))
    elif kind=='too_many':after['messages']=[dict(message_id=str(i))for i in range(513)]
    elif kind=='one_locale':
        for row in after['messages']:row['locale']='zh'
    calls=[]
    with pytest.raises(ValueError):perform(tmp_path,budget,data,native=lambda request:calls.append(request))
    assert calls==[]


def test_failure_requires_actual_same_ledger_rollback_and_current_idle(allocated,tmp_path):
    budget,_=allocated;original=fixture(budget,verdict='UNKNOWN',count=2)
    for change in(dict(source='e'*40),dict(ledger_after={'count':2,'sha256':'f'*64}),dict(active=1)):
        data=deepcopy(original);data[1]['rollback']['cutover'].update(change);calls=[]
        with pytest.raises(ValueError):perform(tmp_path,budget,data,native=lambda request:calls.append(request))
        assert calls==[]
    data=list(original);proof=data[5];data[5]=lambda:dict(proof(),global_pending=1)
    with pytest.raises(ValueError):perform(tmp_path,budget,data)


def test_late_native_attempt_preserves_hold_and_refuses_the_stale_close(allocated,tmp_path):
    budget,_=allocated;data=fixture(budget);budget.begin(sublimits.operation_id('owner-C'),'model',b'late original')
    before=state(budget);policy=sublimits.read(budget)['C']['policy']
    with pytest.raises(ValueError):perform(tmp_path,budget,data)
    assert state(budget)==before and sublimits.read(budget)['C']['policy']==policy


def test_lost_native_ack_is_sticky_and_never_dispatches_again(allocated,tmp_path):
    budget,_=allocated;data=fixture(budget);calls=[]
    def unknown(request):calls.append(request);raise TimeoutError('ACK unknown')
    for _ in range(2):
        with pytest.raises((TimeoutError,FileExistsError)):perform(tmp_path,budget,data,native=unknown)
    assert len(calls)==1 and(tmp_path/'manual-standing-return.intent.json').exists()


def test_old_zero_business_protocol_does_not_accept_the_new_close(allocated,tmp_path):
    budget,_=allocated;data=list(fixture(budget));data[0]=dict(data[0],version=host.VERSION);calls=[]
    with pytest.raises(ValueError):perform(tmp_path,budget,data,native=lambda request:calls.append(request))
    assert calls==[]


@pytest.mark.parametrize('target,key,value',[
    ('plan','tested_source','not-a-source'),('plan','tested_image','not-an-image'),
    ('restriction','cash_ceiling_cny',80),('restriction','model_call_bound',80),
    ('restriction','tool_call_bound',64)])
def test_other_source_or_setup_purpose_cannot_use_ordinary_manual_close(allocated,tmp_path,target,key,value):
    budget,_=allocated;data=list(fixture(budget));index=0 if target=='plan'else 3
    data[index]=dict(data[index],**{key:value});calls=[]
    if target=='plan':data[1]=dict(data[1],**{key:value})
    with pytest.raises(ValueError):perform(tmp_path,budget,data,native=lambda request:calls.append(request))
    assert calls==[]
