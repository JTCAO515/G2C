"""One-shot real-composition transition boundaries, no host/cloud commands."""
import json
from pathlib import Path

import pytest

from deploy.hk import app_smoke_install as install


def point(**changes):
    value=dict(global_pending=0,global_active=0,background_states={},memory_states={'unknown':2},
               ledger=dict(count=1232,sha256='a'*64))
    value.update(changes);return value


def run(tmp_path,*,drained=None,after=None,failure=None):
    calls=[];proofs=iter([drained or point(),after or point()])
    def mark(name):
        def action(*args):
            calls.append((name,args))
            if failure==name:raise ValueError('fixture '+name)
        return action
    result=install.transition(tmp_path,point(),lambda:next(proofs),mark('check'),mark('stop'),
        mark('start'),mark('ready'),mark('window'),mark('unchanged'))
    return result,calls


def test_same_image_install_closes_ingress_drains_then_starts_both_roles(tmp_path):
    result,calls=run(tmp_path)
    assert result==point()
    assert [args[0]for name,args in calls if name=='stop']==[['api'],['worker']]
    names=[name for name,args in calls]
    assert names.index('stop')<names.index('start')<names.index('ready')
    assert json.loads((tmp_path/'install.result.json').read_bytes())['state']=='CAPTURE_INSTALLED_NOT_DISPATCH'
    assert(tmp_path/'install.intent.json').stat().st_mode&0o777==0o600


@pytest.mark.parametrize('change',[
    dict(global_pending=1),dict(global_active=1),dict(background_states={'queued':1}),
    dict(memory_states={'inflight':1}),dict(ledger=dict(count=1233,sha256='b'*64))])
def test_original_work_arrival_stops_both_without_starting_replacement(tmp_path,change):
    calls=[]
    with pytest.raises(ValueError,match='original work arrived'):
        install.transition(tmp_path,point(),lambda:point(**change),lambda installed:None,
            lambda roles:calls.append(('stop',roles)),lambda:calls.append(('start',)),
            lambda:None,lambda:None,lambda:None)
    assert calls==[('stop',['api']),('stop',['api','worker'])]
    assert(tmp_path/'install.intent.json').exists()and not(tmp_path/'install.result.json').exists()


@pytest.mark.parametrize('failure',['start','ready'])
def test_startup_unknown_retains_intent_and_stops_both(tmp_path,failure):
    calls=[]
    def start():
        calls.append('start')
        if failure=='start':raise ValueError('startup UNKNOWN')
    def ready():raise ValueError('readiness UNKNOWN')
    with pytest.raises(ValueError,match='UNKNOWN'):
        install.transition(tmp_path,point(),lambda:point(),lambda installed:None,
            lambda roles:calls.append(roles),start,ready,lambda:None,lambda:None)
    assert calls[-1]==['api','worker']and(tmp_path/'install.intent.json').exists()
    assert not(tmp_path/'install.result.json').exists()


def test_prior_intent_blocks_second_apply_before_ingress_stop(tmp_path):
    calls=[];(tmp_path/'install.intent.json').write_bytes(b'old unknown; reconcile first')
    with pytest.raises(FileExistsError):
        install.transition(tmp_path,point(),lambda:point(),lambda installed:None,
            lambda roles:calls.append(roles),lambda:None,lambda:None,lambda:None,lambda:None)
    assert calls==[]and(tmp_path/'install.intent.json').read_bytes()==b'old unknown; reconcile first'


def test_role_separation_never_mounts_worker_raw_into_api():
    services=install.override(Path('/private/operator-window'))['services']
    api={v['target']:v for v in services['api']['volumes']}
    worker={v['target']:v for v in services['worker']['volumes']}
    assert '/app-smoke-evidence'not in api and '/rejected-intakes'not in api
    assert api['/app-smoke-claims']['read_only']is True
    assert api['/app-smoke-outer']['read_only']is False
    assert worker['/app-smoke-claims']['read_only']is False
    assert worker['/app-smoke-outer']['read_only']is True
    assert worker['/app-smoke-evidence'].get('read_only',False)is False
    assert all(v['read_only']is True for v in api.values()if v['target'].startswith('/run/'))


def packet(tmp_path,monkeypatch):
    import os,hashlib
    monkeypatch.setattr(install,'CAPTURE_UID',os.getuid())
    def write(path,value):
        path.write_text(json.dumps(value,sort_keys=True,separators=(',',':')));path.chmod(0o600)
        return install.sha(path)
    for name in('claims','evidence','outer'):(tmp_path/name).mkdir(mode=0o700)
    frozen=dict(run_id='frozen-window',steps=[])
    frozen_sha=write(tmp_path/'plan.json',frozen)
    evidence=dict(directory='/app-smoke-evidence');evidence_sha=write(tmp_path/'evidence.json',evidence)
    claims=(tmp_path/'claims').stat();artifacts=(tmp_path/'evidence').stat();outer=(tmp_path/'outer').stat()
    policy=dict(source_commit='a'*40,plan_sha256=frozen_sha,window_id='frozen-window',directory='/app-smoke-claims',
        evidence_manifest='/run/app-smoke/evidence.json',evidence_sha256=evidence_sha,
        directory_device=claims.st_dev,directory_inode=claims.st_ino,artifact_device=artifacts.st_dev,artifact_inode=artifacts.st_ino)
    policy_sha=write(tmp_path/'policy.json',policy)
    write(tmp_path/'api.json',dict(policy_path='/run/app-smoke/policy.json',directory='/app-smoke-outer',
        policy_sha256=policy_sha,directory_device=outer.st_dev,directory_inode=outer.st_ino))
    write(tmp_path/'proof-plan.json',dict(cases=[],source_commit='a'*40))
    write(tmp_path/'claims/claims.lock',{})
    write(tmp_path/'claims/claims.json',dict(version='G2C-App-smoke-claims.1',policy_sha256=policy_sha,state='ACTIVE',claims=[]))
    write(tmp_path/'compose.capture.json',install.override(tmp_path))
    plan=dict(source='a'*40,files={name:install.sha(tmp_path/name)for name in install.FILES})
    return plan


def test_actual_private_packet_must_match_container_paths_and_current_directory_inodes(tmp_path,monkeypatch):
    plan=packet(tmp_path,monkeypatch)
    assert install.fresh(tmp_path,plan)['window_id']=='frozen-window'
    (tmp_path/'outer').rename(tmp_path/'old-outer');(tmp_path/'outer').mkdir(mode=0o700)
    with pytest.raises(ValueError,match='Hong Kong directory inode'):install.fresh(tmp_path,plan)


def test_changed_packet_or_existing_claims_cannot_be_reissued_as_fresh(tmp_path,monkeypatch):
    plan=packet(tmp_path,monkeypatch)
    (tmp_path/'claims/claims.json').write_text(json.dumps(dict(claims=[{'message_id':'old'}])))
    with pytest.raises(ValueError,match='unconsumed'):install.fresh(tmp_path,plan)
    (tmp_path/'plan.json').write_bytes(b'changed frozen plan')
    with pytest.raises(ValueError,match='packet changed'):install.fresh(tmp_path,plan)
