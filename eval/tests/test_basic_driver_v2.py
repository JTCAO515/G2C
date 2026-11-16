"""Real-action orchestration boundaries tested without UI/native transports."""
from datetime import datetime,timezone
from hashlib import sha256

import pytest

from eval.basic_chain.driver_v2 import execute
from eval.basic_chain.plan import Invalid,decode,make_plan
from eval.basic_chain.runner import save


def inputs(tmp_path):
    app=dict(build=46,source_sha='a'*40,artifact_sha256='b'*64,protocol='LIO-message.2',
             surface='simulator',renderer_source_sha256='c'*64)
    plan=make_plan(app=app,old_chats={'zh':'old-zh','en':'old-en'},run_id='OFFLINE-DRIVER-CONTROL')
    proof=tmp_path/'purpose.json'
    save(proof,dict(version='G2C-App-smoke-purpose-restriction-result.1',state='C_PURPOSE_RESTRICTED_ACKED_NOT_A_LEASE',
        new_money_cny=0,native_account_quota_changed=False,cash_ceiling_cny=60,model_call_bound=40,tool_call_bound=32,
        original_usage={'total':0,'calls':0,'model_calls':0,'tool_calls':0},
        restricted_policy={'cap':1_000_000_000,'active_cap':600_000_000,'model_calls':40,'tool_calls':32,'max_calls':72},
        baseline_policy={'cap':1_000_000_000,'active_cap':1_000_000_000}))
    config=dict(version='LIO-basic-chain-host.2',app=app,synthetic_only=True,
        purpose_receipt={'path':str(proof),'sha256':sha256(proof.read_bytes()).hexdigest()},
        pricing={'scale':10_000_000},subjects={'zh':'synthetic-zh','en':'synthetic-en'},
        candidate={'source':'d'*40,'image':'sha256:'+'e'*64,'qualification_sha256':'f'*64,'policy_sha256':'a'*64},
        ui_prepare_seconds=10,ui_action_seconds=90,original_collection_seconds=90)
    return plan,config


def test_wrong_purpose_is_refused_before_any_UI_or_native_action(tmp_path):
    plan,config=inputs(tmp_path);config['purpose_receipt']['sha256']='0'*64
    calls=[]
    with pytest.raises(Invalid):
        execute(plan,config,tmp_path/'not-created',call=lambda *args:calls.append(args))
    assert not calls and not(tmp_path/'not-created').exists()


def test_UI_preparation_precedes_server_checkpoint_and_guard_failure_admits_no_action(tmp_path):
    plan,config=inputs(tmp_path);root=tmp_path/'run';events=[];ticks=[0]
    artifact=tmp_path/'actual-control-AX.json';save(artifact,{'CONTROL_ONLY':True})
    def clock():ticks[0]+=.01;return ticks[0]
    def sleep(_):
        instruction=decode((root/'00-prepare.json').read_bytes())
        if not(root/'00-A-prepared.json').exists():
            events.append('UI_PREPARED')
            save(root/'00-A-prepared.json',dict(version='LIO-basic-app-prepared.2',run_id=plan['run_id'],
                nonce=instruction['step']['nonce'],send_taps=0,app=plan['app'],ui_before={},
                artifacts=[{'path':str(artifact),'sha256':sha256(artifact.read_bytes()).hexdigest()}]))
    def call(program,request):
        assert program=='backend'and 'token'not in request
        events.append(request['kind'])
        if request['kind']=='checkpoint':raise Invalid('actual native source changed')
        assert request['kind']=='stop_new'
        return {'status':'READ'}
    report=execute(plan,config,root,now=lambda:datetime(2026,11,16,2,tzinfo=timezone.utc),
                   clock=clock,sleep=sleep,call=call)
    assert events==['UI_PREPARED','checkpoint','stop_new']
    assert not(root/'00-admission.json').exists()
    assert report['totals']==dict(PASS=0,FAIL=0,UNKNOWN=1,UNRUN=13)
    assert report['denominator']==14 and not report['release_allowed']
    assert report['service_layer']=='L0_CONTROL'and report['real_gate_status']=='UNRUN'


def test_night_refuses_even_UI_preparation_and_retains_full_denominator(tmp_path):
    plan,config=inputs(tmp_path);calls=[]
    report=execute(plan,config,tmp_path/'night',now=lambda:datetime(2026,11,16,15,tzinfo=timezone.utc),
                   call=lambda name,request:calls.append((name,request['kind']))or{'status':'READ'})
    assert calls==[('backend','stop_new')]
    assert report['totals']==dict(PASS=0,FAIL=0,UNKNOWN=1,UNRUN=13)
    assert report['cost']['actual_paid_cny']is None and not report['release_allowed']
