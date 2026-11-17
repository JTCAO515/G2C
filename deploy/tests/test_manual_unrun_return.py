"""JT's stopped, zero-message window returns C100 without inventing failure."""
from copy import deepcopy

import pytest

from backend.usage.tests.test_sublimits import allocated
from cj_usage import sublimits
from deploy.hk import manual_smoke_return as host
from deploy.hk.app_smoke_ceiling import BASELINE
from deploy.tests.test_app_smoke_ceiling import state
from deploy.tests.test_manual_business_return import fixture,perform


def unrun_fixture(budget):
    data=list(fixture(budget,verdict='FAIL',count=0))
    plan,closed,stopped,restriction,values,proof,before,after=data
    plan.update(version=host.UNRUN_VERSION,source=plan['tested_source'],
        image=plan['tested_image'],unrun_decision=host.UNRUN_DECISION)
    closed.update(version='B-manual14-close.3',state='CLOSED_UNRUN_KEPT_SOURCE',
        verdict='UNRUN',rollback=None,unrun_decision=host.UNRUN_DECISION)
    stopped['verdict']='UNRUN'
    for value in values.values():
        value['Image']=plan['image'];value['Config']['Labels']['org.opencontainers.image.revision']=plan['source']
    return data


def test_true_unrun_close_keeps_source_and_all_original_and_foreign_holds(allocated,tmp_path):
    budget,_=allocated;data=unrun_fixture(budget)
    budget.begin(sublimits.operation_id('owner-A'),'model',b'other approved user activity')
    data[1]['ledger_after']=data[5]()['ledger']
    before=state(budget);attempts=budget.inspect();roles=deepcopy(data[4])
    assert perform(tmp_path,budget,data,apply=False)['state']=='READONLY_NOT_RESTORED'
    result=perform(tmp_path,budget,data)
    assert result['state']=='C_ORIGINAL_STANDING_RESTORED_ACKED'
    assert sublimits.read(budget)['C']['policy']==BASELINE
    assert state(budget)==before and budget.inspect()==attempts and data[4]==roles
    assert result['attempts_refunded_or_deleted']==0 and result['ended_window']=='REMAINS_CLOSED'


@pytest.mark.parametrize('target,change',[
    ('closed',dict(verdict='FAIL')),('closed',dict(verdict='UNKNOWN')),
    ('closed',dict(state='CLOSED_PASS')),('closed',dict(version='B-manual14-close.2')),
    ('closed',dict(message_delta=1,message_ids=['unrun-cannot-hide-a-message'])),
    ('closed',dict(rollback={'state':'invented'})),
    ('closed',dict(unrun_decision='other')),
    ('plan',dict(unrun_decision='other')),('plan',dict(source='f'*40)),
    ('plan',dict(image='sha256:'+'f'*64)),
])
def test_new_exception_never_accepts_failure_new_business_or_different_source(allocated,tmp_path,target,change):
    budget,_=allocated;data=unrun_fixture(budget);index=0 if target=='plan'else 1
    data[index].update(change);calls=[];old=state(budget)
    with pytest.raises(ValueError):perform(tmp_path,budget,data,native=lambda request:calls.append(request))
    assert calls==[]and state(budget)==old


def test_actual_new_message_cannot_be_called_unrun(allocated,tmp_path):
    budget,_=allocated;data=unrun_fixture(budget)
    data[-1]['messages'].append(dict(message_id='actually-posted',locale='zh'))
    data[1].update(message_delta=1,message_ids=['actually-posted']);calls=[]
    with pytest.raises(ValueError):perform(tmp_path,budget,data,native=lambda request:calls.append(request))
    assert calls==[]


@pytest.mark.parametrize('version',[host.VERSION,host.BUSINESS_VERSION])
def test_original_versions_do_not_inherit_unrun_source_exception(allocated,tmp_path,version):
    budget,_=allocated;data=unrun_fixture(budget);data[0]['version']=version;calls=[]
    with pytest.raises(ValueError):perform(tmp_path,budget,data,native=lambda request:calls.append(request))
    assert calls==[]
