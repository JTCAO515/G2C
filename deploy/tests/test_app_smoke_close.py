"""Returned capture restores default roles, with original attempts untouched."""
import json

import pytest

from deploy.hk import app_smoke_close as close
from deploy.tests.test_app_smoke_install import point


@pytest.mark.parametrize('end',[
    '2026-11-16T09:00:00+00:00','2026-11-16T09:00:00.000000+00:00',
    '2026-11-16T17:00:00+08:00','2026-11-16T04:00:00-05:00'])
def test_host_expiry_aware_offsets_preserve_exact_boundary(end):
    epoch=1794819600
    assert close.expired(end,epoch)is True
    assert close.expired(end,epoch-.001)is False


def test_host_expiry_does_not_infer_timezone_from_naive_input():
    with pytest.raises(ValueError):close.expired('2026-11-16T09:00:00',1794819600)


def test_closed_capture_drains_and_restores_default_roles_without_fee_or_PASS_claim(tmp_path):
    calls=[]
    result=close.transition(tmp_path,point(),lambda:point(),lambda captured:calls.append(('check',captured)),
        lambda roles:calls.append(('stop',roles)),lambda:calls.append(('start_default',)),
        lambda:None,lambda:None,lambda:None)
    assert [c for c in calls if c[0]=='check']==[('check',True),('check',False)]
    assert [c for c in calls if c[0]=='stop']==[('stop',['api']),('stop',['worker'])]
    assert result['state']=='DEFAULT_ROLES_RESTORED'and result['ledger_before']==result['ledger_after']
    assert result['originals_deleted']==0 and result['budget_restored']is False
    assert result['smoke_status']==result['full_cost_coverage']=='NOT_ASSERTED'
    assert json.loads((tmp_path/'close.result.json').read_bytes())==result


@pytest.mark.parametrize('where',['drain','after'])
def test_late_original_work_prevents_closed_receipt_and_stops_both(tmp_path,where):
    calls=[];changed=point(ledger=dict(count=1233,sha256='b'*64))
    values=iter([changed,point()]if where=='drain'else[point(),changed])
    with pytest.raises(ValueError,match='original work'):
        close.transition(tmp_path,point(),lambda:next(values),lambda captured:None,
            lambda roles:calls.append(roles),lambda:None,lambda:None,lambda:None,lambda:None)
    assert calls[-1]==['api','worker']and(tmp_path/'close.intent.json').exists()
    assert not(tmp_path/'close.result.json').exists()


def test_existing_close_intent_blocks_repeat_before_stopping_api(tmp_path):
    (tmp_path/'close.intent.json').write_bytes(b'old unknown close')
    calls=[]
    with pytest.raises(FileExistsError):
        close.transition(tmp_path,point(),lambda:point(),lambda captured:None,
            lambda roles:calls.append(roles),lambda:None,lambda:None,lambda:None,lambda:None)
    assert calls==[]and(tmp_path/'close.intent.json').read_bytes()==b'old unknown close'


def test_unknown_default_role_start_keeps_originals_and_leaves_services_closed(tmp_path):
    artifact=tmp_path/'original-evidence.json';artifact.write_bytes(b'original')
    calls=[]
    def ready():raise ValueError('readiness UNKNOWN')
    with pytest.raises(ValueError,match='UNKNOWN'):
        close.transition(tmp_path,point(),lambda:point(),lambda captured:None,
            lambda roles:calls.append(roles),lambda:None,ready,lambda:None,lambda:None)
    assert calls[-1]==['api','worker']and artifact.read_bytes()==b'original'
    assert not(tmp_path/'close.result.json').exists()
