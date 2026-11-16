"""Server-owned checkpoints cannot be replaced by caller accounting labels."""
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cj_usage.authorization_budget import canonical
from runtime_adapter.contract import Unavailable
from deploy.hk.app_smoke_read import perform
from deploy.tests.test_app_smoke_capture import fixture,write,SUBJECTS
from cj_api.local_app import scope_for,ISSUER


def prepared(tmp_path):
    f=fixture(tmp_path)
    plan={'version':'fixture-plan','steps':[{'nonce':f.policy['slots'][0]['nonce'],'locale':'zh'}]}
    write(tmp_path/'plan.json',plan)
    f.policy['plan_sha256']=sha256(canonical(plan)).hexdigest();write(f.path,f.policy)
    write(f.claims/'claims.json',dict(version='G2C-App-smoke-claims.1',state='ACTIVE',
        policy_sha256=sha256(f.path.read_bytes()).hexdigest(),claims=[]))
    capture=f.load();scope_hash=sha256(scope_for(ISSUER,SUBJECTS[0]).encode()).hexdigest()
    state_value={'scope_sha256':scope_hash,'message_ids':[],'background_rows':[],
                 'trip_sha256':'a'*64,'memory_sha256':'b'*64,'pending':0,'active':0}
    state=SimpleNamespace(read=lambda token:dict(state_value))
    financial={'ledger_id':'fixture-ledger','producer_id':'fixture','anchor':{'count':0,'sha256':'c'*64},'c_rows':[]}
    http={'log_utf8':'','log_sha256':sha256(b'').hexdigest(),'read_files':[]}
    originals=SimpleNamespace(checkpoint=lambda:financial,http_checkpoint=lambda token:http,verified_history=lambda token,state:[],
        default_history=lambda token,state:dict(version='LIO-readonly-history-anchor.1',conversation_id='lio-dialogue-'+'a'*32,generation=None,messages=[]),
        http_observed=lambda token,before:dict(post_count=0,post_exchanges=[],actual_reads=[],checkpoint=http))
    controls=SimpleNamespace(guard=lambda:None,window={'policy_path':str(f.path)},policy=f.policy)
    request=dict(version='G2C-App-smoke-read-request.1',kind='checkpoint',token='fixture-only',
        message_id=None,operation_id=None,expected_source=f.policy['source_commit'],
        plan_sha256=f.policy['plan_sha256'],nonce=plan['steps'][0]['nonce'])
    return f,controls,capture,originals,state,request


def test_checkpoint_is_created_once_on_server_and_caller_cannot_supply_its_before(tmp_path):
    f,controls,capture,originals,state,request=prepared(tmp_path)
    result=perform(request,controls,capture,originals,state)
    assert result['status']=='READ'and len(result['checkpoint_ref'])==64
    with pytest.raises(FileExistsError):perform(request,controls,capture,originals,state)
    forged=dict(request,kind='observe_read',before={'native_state':{},'financial':{}})
    with pytest.raises(Unavailable,match='ACTUAL_BEFORE_CHECKPOINT'):perform(forged,controls,capture,originals,state)
    unknown=dict(request,kind='observe_read',checkpoint_ref='0'*64)
    with pytest.raises(Unavailable,match='BEFORE_CHECKPOINT_CHANGED'):perform(unknown,controls,capture,originals,state)


def test_plan_nonce_and_current_owner_cannot_be_substituted(tmp_path):
    f,controls,capture,originals,state,request=prepared(tmp_path)
    with pytest.raises(Unavailable,match='UNKNOWN_STEP_NONCE'):
        perform(dict(request,nonce='f'*32),controls,capture,originals,state)
    with pytest.raises(Unavailable,match='READ_PLAN_CHANGED'):
        perform(dict(request,plan_sha256='0'*64),controls,capture,originals,state)
    other=SimpleNamespace(read=lambda token:dict(scope_sha256='0'*64,message_ids=[],background_rows=[]))
    with pytest.raises(Unavailable,match='STEP_OWNER_CHANGED'):
        perform(request,controls,capture,originals,other)


def test_background_and_lock_have_independent_immutable_native_checkpoints(tmp_path):
    f,controls,capture,originals,state,request=prepared(tmp_path)
    plan=dict(steps=[dict(gate_id='SM04',text=None,locale='zh',nonce='a'*32,
        read_actions=[dict(action='background_return',nonce='b'*32),dict(action='lock_return',nonce='c'*32)])])
    write(tmp_path/'plan.json',plan)
    f.policy['plan_sha256']=sha256(canonical(plan)).hexdigest();write(f.path,f.policy)
    write(f.claims/'claims.json',dict(version='G2C-App-smoke-claims.1',state='ACTIVE',
        policy_sha256=sha256(f.path.read_bytes()).hexdigest(),claims=[]))
    capture=f.load()
    request=dict(request,plan_sha256=f.policy['plan_sha256'])
    first=perform(dict(request,nonce='b'*32),controls,capture,originals,state)
    second=perform(dict(request,nonce='c'*32),controls,capture,originals,state)
    assert first['checkpoint_ref']!=second['checkpoint_ref']
    assert len(list(f.claims.glob('*.checkpoint.json')))==2
    with pytest.raises(FileExistsError):perform(dict(request,nonce='b'*32),controls,capture,originals,state)
    with pytest.raises(Unavailable,match='BEFORE_CHECKPOINT_CHANGED'):
        perform(dict(request,kind='observe_read',nonce='c'*32,checkpoint_ref=first['checkpoint_ref']),
            controls,capture,originals,state)
