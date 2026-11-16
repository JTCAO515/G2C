"""Real-action orchestration boundaries tested without UI/native transports."""
from datetime import datetime,timezone
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from cj_message import lio_context

import pytest

from eval.basic_chain.driver_v2 import execute,_actions,_gate_rows
from eval.basic_chain.plan import Invalid,decode,make_plan
from eval.basic_chain.runner import save
from eval.basic_chain.plan import digest
from cj_api.local_app import ISSUER,scope_for
from cj_message.demo_dialogue import lio_conversation


def inputs(tmp_path):
    app=dict(build=46,source_sha='a'*40,artifact_sha256='b'*64,protocol='LIO-message.2',
             surface='simulator',renderer_source_sha256='c'*64)
    old={language:dict(version='LIO-readonly-history-anchor.1',conversation_id='old-'+language,generation='control-generation',
        messages=[dict(message_id='old-mid-'+language,run_id='old-run-'+language,sequence=1,canonical_sha256='a'*64)])
        for language in('zh','en')}
    plan=make_plan(app=app,old_chats=old,run_id='OFFLINE-DRIVER-CONTROL')
    proof=tmp_path/'purpose.json'
    save(proof,dict(version='G2C-App-smoke-purpose-restriction-result.1',state='C_PURPOSE_RESTRICTED_ACKED_NOT_A_LEASE',
        new_money_cny=0,native_account_quota_changed=False,cash_ceiling_cny=60,model_call_bound=40,tool_call_bound=32,
        original_usage={'total':0,'calls':0,'model_calls':0,'tool_calls':0},
        restricted_policy={'cap':1_000_000_000,'active_cap':600_000_000,'model_calls':40,'tool_calls':32,'max_calls':72},
        baseline_policy={'cap':1_000_000_000,'active_cap':1_000_000_000}))
    config=dict(version='LIO-basic-chain-host.2',app=app,synthetic_only=True,
        purpose_receipt={'path':str(proof),'sha256':sha256(proof.read_bytes()).hexdigest()},
        pricing={'scale':10_000_000},subjects={'zh':'synthetic-zh','en':'synthetic-en'},
        candidate={'source':'d'*40,'image':'sha256:'+'e'*64,'qualification_sha256':'f'*64,'policy_sha256':'a'*64,
                   'display_answer_source_sha256':sha256(Path(lio_context.__file__).read_bytes()).hexdigest()},
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


def test_lifecycle_subevidence_retains_one_gate_and_stops_on_incomplete_return(tmp_path):
    plan,_=inputs(tmp_path)
    actions=[s for _,s in _actions(plan)if s['gate_id']=='SM04'and s['locale']=='zh']
    assert [s['action']for s in actions]==['background_return','lock_return']
    assert len({s['nonce']for s in actions})==2
    def row(status):
        results=[dict(gate_id='SM04',locale='zh',status=value)for value in status]
        rows=_gate_rows(plan,results)
        assert len(rows)==14
        return next(r for r in rows if r['gate_id']=='SM04'and r['locale']=='zh')
    assert row(['PASS'])['status']=='UNRUN'
    assert row(['PASS','PASS'])['status']=='PASS'
    assert row(['UNKNOWN'])['status']=='UNKNOWN'
    assert row(['FAIL'])['status']=='FAIL'
    assert row(['PASS','UNKNOWN'])['status']=='UNKNOWN'


@pytest.mark.parametrize('fault',[None,'missing_target','wrong_generation','wrong_canonical','publication_pending','capture_unknown','pending_source_changed'])
def test_standard_driver_bootstraps_old_chat_from_qualified_read_without_seed_or_prefilled_views(tmp_path,fault):
    from eval.tests.test_basic_native_v2 import fixture,add_read
    from eval.tests.test_basic_chain import PRICING
    from eval.basic_chain.joint_v2 import draft_marker
    plan,config=inputs(tmp_path);host,_,expected,_,_=fixture();add_read(host,expected)
    original=host['original'];native_message=original['message'];row=original['after']['native_messages'][0]
    anchor=dict(version='LIO-readonly-history-anchor.1',conversation_id=row['conversation_id'],generation=row['generation'],
        messages=[{key:row[key]for key in('message_id','run_id','sequence','canonical_sha256')}])
    if fault=='wrong_generation':anchor['generation']='another-generation'
    if fault=='wrong_canonical':anchor['messages'][0]['canonical_sha256']='0'*64
    plan['old_chats']['zh']=anchor
    config['candidate'].update(expected,display_answer_source_sha256=sha256(Path(lio_context.__file__).read_bytes()).hexdigest(),
        tool_implementation_sha256='a'*64)
    config['pricing']=PRICING;config['native_ledger_id']='C'
    scope=scope_for(ISSUER,config['subjects']['zh']);scope_sha=sha256(scope.encode()).hexdigest()
    def rebind(value):
        if type(value)is dict:return {key:rebind(v)for key,v in value.items()}
        if type(value)is list:return [rebind(v)for v in value]
        if value==expected['scope_sha256']:return scope_sha
        if value==expected['default_conversation_id']:return lio_conversation(scope)
        if value=='synthetic-only-owner':return scope
        return value
    host=rebind(host);original=host['original'];state=original['after']
    read=original['http']['actual_reads'][0]
    view=dict(version='LIO-timeline.2',conversation_id=anchor['conversation_id'],next_before=None,
        messages=[dict(message_id=row['message_id'],text=native_message['text'],answer=native_message['answer'],
                       status='completed',failure=None,trip=None)])
    import json
    read['response_utf8']=json.dumps(view,ensure_ascii=False);read['response_sha256']=sha256(read['response_utf8'].encode()).hexdigest()
    original['http']['read_exchanges'][1]['response_sha256']=read['response_sha256']
    original['http'].update(post_count=0,post_exchanges=[])
    step=plan['steps'][0];base=dict(version='G2C-App-smoke-read.1',status='READ',source=expected['source'],
        plan_sha256=digest(plan),window_id=plan['run_id'],nonce=step['nonce'],state='ACTIVE',
        policy_sha256=expected['policy_sha256'],scope_sha256=scope_sha)
    original.update(base,kind='observe_read',before=state,after=state,components=[],
        accounting=dict(attempts=[],coverage='complete',producer_closure_verified=True,closure_ref='CONTROL_ONLY',missing=[]))
    point=dict(base,kind='checkpoint',checkpoint_ref='1'*64,native_state=state,
        ledger_anchor={'count':0,'sha256':'a'*64},claims=[],history_targets=[anchor],
        default_history_target=dict(version='LIO-readonly-history-anchor.1',conversation_id=lio_conversation(scope),generation=None,messages=[]))
    if fault=='missing_target':point['history_targets']=[]
    root=tmp_path/'standard';ticks=[0];events=[]
    artifact=tmp_path/'actual-control-AX.json';save(artifact,{'CONTROL_ONLY':True})
    artifacts=[dict(path=str(artifact),sha256=sha256(artifact.read_bytes()).hexdigest())]
    transcript=[dict(question=native_message['text'],answer=native_message['answer'])]
    before=dict(body_complete=True,errors=[],transcript=transcript,draft=draft_marker(plan,step),new_greeting_count=0)
    def clock():ticks[0]+=.01;return ticks[0]
    def sleep(_):
        for index in(0,1):
            path=root/f'{index:02d}-prepare.json'
            if not path.exists():continue
            instruction=decode(path.read_bytes());s=instruction['step']
            prepared=root/f'{index:02d}-A-prepared.json'
            if not prepared.exists():
                if index==0:assert instruction['accepted_conversations']=={}
                save(prepared,dict(version='LIO-basic-app-prepared.2',run_id=plan['run_id'],nonce=s['nonce'],
                    send_taps=0,app=plan['app'],ui_before=before,artifacts=artifacts))
            if index==0 and(root/'00-admission.json').exists()and not(root/'00-A-completed.json').exists():
                save(root/'00-A-completed.json',dict(version='LIO-basic-app-witness.2',source='actual_ordinary_Home_AX',
                    app=plan['app'],run_id=plan['run_id'],gate_id='SM01',locale='zh',nonce=s['nonce'],artifacts=artifacts,
                    message_id_observed=None,conversation_id_observed=None,send_taps=0,submitted_text=None,
                    before=before,after=deepcopy(before),actions=['cold_launch']))
    def call(program,request):
        if program=='projector':
            return dict(version='LIO-reply-projection.1',app=plan['app'],input_sha256=request['input_sha256'],
                renderer_source_sha256=plan['app']['renderer_source_sha256'],rejected=False,
                rendered_utf8=request['raw_utf8'],rendered_sha256=request['input_sha256'])
        events.append(request['kind'])
        if request['kind']=='checkpoint':
            if request['nonce']!=step['nonce']:raise Invalid('CONTROL stop before next real action')
            return dict(host,original=point)
        if request['kind']=='observe_read':
            if fault in('publication_pending','capture_unknown','pending_source_changed')and events.count('observe_read')==1:
                pending=deepcopy(host)
                pending['original']=dict(version='G2C-App-smoke-read.1',status='UNAVAILABLE',
                    reason='CAPTURE_UNKNOWN'if fault=='capture_unknown'else'APP_SMOKE_HTTP_OUTER_PENDING')
                if fault=='pending_source_changed':pending['actual_roles']['api']['source']='0'*40
                return pending
            return host
        assert request['kind']=='stop_new'
        return {'status':'READ'}
    report=execute(plan,config,root,now=lambda:datetime(2026,11,16,2,tzinfo=timezone.utc),clock=clock,sleep=sleep,call=call)
    if fault in(None,'publication_pending'):
        assert report['totals']==dict(PASS=1,FAIL=0,UNKNOWN=1,UNRUN=12)
        assert report['rows'][0]['status']=='PASS'
        assert events==['checkpoint','observe_read']+(['observe_read']if fault=='publication_pending'else[])+['checkpoint','stop_new']
    else:
        assert report['totals']==dict(PASS=0,FAIL=0,UNKNOWN=1,UNRUN=13)
        assert events==['checkpoint']+(['observe_read']if fault in('capture_unknown','pending_source_changed')else[])+['stop_new']
    assert report['real_gate_status']=='UNRUN'and not report['release_allowed']and report['jt_invitation_status']=='UNRUN'
