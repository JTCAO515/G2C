"""Actual filesystem identities in a new private packet; no cloud/activation."""
import hashlib
import json
import os

import pytest

from deploy.hk import app_smoke_stage as stage
from deploy.hk.app_smoke_install import fresh


def packet():
    plan=dict(version='LIO-basic-chain-plan.2',run_id='fresh-window',planned_message_count=8)
    evidence=dict(version='G2C-runtime-evidence-window.4',directory='/old/evidence',subjects=['C-zh','C-en'],source_commit='a'*40)
    policy=dict(version='G2C-App-smoke-capture.1',window_id=plan['run_id'],source_commit='a'*40,
        plan_sha256=stage.digest(plan),evidence_sha256=stage.digest(evidence),slots=[dict(locale=loc,subject='C-'+loc)for loc in('zh','en')for _ in range(4)])
    api=dict(version='G2C-App-smoke-outer-window.1',policy_sha256=stage.digest(policy))
    values={'plan.json':plan,'evidence.json':evidence,'policy.json':policy,'api.json':api}
    return dict(version='G2C-App-smoke-stage-request.1',files=values,sha256={n:stage.digest(v)for n,v in values.items()})


def test_staged_hashes_paths_inodes_are_actual_and_not_a_live_qualification(tmp_path,monkeypatch):
    from deploy.hk import app_smoke_install
    monkeypatch.setattr(stage,'CAPTURE_UID',os.getuid());monkeypatch.setattr(stage,'CAPTURE_GID',os.getgid())
    monkeypatch.setattr(app_smoke_install,'CAPTURE_UID',os.getuid())
    request=packet();result=stage.stage(tmp_path,request);directory=tmp_path/'fresh-window'
    assert result['state']=='STAGED_NOT_ACTIVE'and result['new_accounts']==result['new_money']==result['new_message_ids']==0
    assert result['services_changed']is False
    assert result['input_sha256']==request['sha256']
    for name,digest in result['files'].items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest
        assert(directory/name).stat().st_mode&0o777==0o600
    policy=fresh(directory,dict(source='a'*40,files=result['files']))
    assert policy['directory']=='/app-smoke-claims'
    assert policy['directory_inode']==(directory/'claims').stat().st_ino
    assert json.loads((directory/'claims/claims.json').read_bytes())['claims']==[]
    with pytest.raises(FileExistsError):stage.stage(tmp_path,request)


@pytest.mark.parametrize('change',['hash','legacy','traversal','binding'])
def test_invalid_input_is_refused_before_creating_packet(tmp_path,change):
    request=packet()
    if change=='hash':request['sha256']['policy.json']='f'*64
    elif change=='legacy':
        request['files']['plan.json']['version']='LIO-basic-chain-plan.1'
        request['sha256']['plan.json']=stage.digest(request['files']['plan.json'])
    elif change=='traversal':
        request['files']['plan.json']['run_id']='../escape'
        request['sha256']['plan.json']=stage.digest(request['files']['plan.json'])
    else:
        request['files']['api.json']['policy_sha256']='f'*64
        request['sha256']['api.json']=stage.digest(request['files']['api.json'])
    with pytest.raises(ValueError):stage.stage(tmp_path,request)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('index',[0,1,2,4,5,6])
def test_early_third_subject_cannot_be_hidden_by_later_locale_slot(tmp_path,index):
    request=packet();values=request['files'];policy=values['policy.json']
    policy['slots'][index]['subject']='third-subject'
    values['api.json']['policy_sha256']=stage.digest(policy)
    request['sha256']={name:stage.digest(value)for name,value in values.items()}
    with pytest.raises(ValueError,match='two original C subjects'):
        stage.stage(tmp_path,request)
    assert not list(tmp_path.iterdir())
