"""Offline boundary controls only. These fixtures are never real smoke scores."""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile

import pytest

from eval.basic_chain.cost import costs
from eval.basic_chain.judge import judge,semantic
from eval.basic_chain.plan import make_plan,check_plan,packed,digest,decode,Invalid
from eval.basic_chain.runner import execute,private_read,save,day_guard,preflight
from eval.basic_chain.semantics_v2 import semantic as semantic_v2

H='a'*64
APP=dict(build=46,source_sha='a'*40,artifact_sha256=H,protocol='LIO-message.2')
CANDIDATE=dict(source='b'*40,image='sha256:'+H,schema=55,qualification_sha256=H)
PRICING=dict(scale=10_000_000,source_sha256=H,model_input_per_token=8,
    model_output_per_token=27,model_id='qualified-model',endpoint='qualified-endpoint',region='qualified-region',
    limits={'model':{'hold_per_attempt_units':10_000_000},'tool':{'hold_per_attempt_units':30_000}})
NOW=datetime(2026,11,16,6,tzinfo=timezone.utc)


def fixture():
    plan=make_plan(app=APP,old_chats=dict(zh='old-zh',en='old-en'),run_id='OFFLINE-CONTROL')
    step=plan['steps'][1]
    wire=dict(version=APP['protocol'],message_id='actual-app-mid',text=step['text'],locale='zh',new_conversation=True)
    raw=json.dumps(wire,ensure_ascii=False)
    answer='是的，北京是中国的首都。'
    context=dict(CANDIDATE,subject='synthetic-zh',old_cid='old-zh',qa_cid=None)
    state=dict(memory_sha256=H,trip_sha256=H)
    row=dict(ledger_id='C',attempt_id='original-op',kind='model',conservative_units=200,
        actual_wire_input_sha256='c'*64,native_binding_verified=True,state='RECEIVED',priceable_tool_units=None,
        receipt=dict(model_id=PRICING['model_id'],endpoint=PRICING['endpoint'],region=PRICING['region'],
                     usage=dict(prompt_tokens=10,completion_tokens=4,total_tokens=14)))
    accounting=dict(attempts=[row],coverage='complete',producer_closure_verified=True,closure_ref='real-producer-proof',missing=[])
    observation=dict(version='LIO-basic-chain-observation.1',run_id=plan['run_id'],gate_id=step['gate_id'],
        locale=step['locale'],nonce=step['nonce'],binding={k:context[k]for k in CANDIDATE}|{'subject':context['subject']},
        app=dict(APP,ordinary_home=True),
        ui=dict(producer_ref='A-original',artifacts_verified=True,intent_utf8=raw,render_source_mid=wire['message_id'],
            after_cid='new-zh',post_count=1,received_answer_sha256=sha256(answer.encode()).hexdigest(),
            answer_visible=True,visible_answer=answer),
        backend=dict(protected_read_verified=True,source_unchanged=True,evidence_sha256=H,accounting=accounting,
            outer_request=dict(provenance='B_actual_HTTP_boundary',protected_capture_verified=True,
                utf8=raw,sha256=sha256(raw.encode()).hexdigest(),method='POST',route='/v2/lio/messages'),
            timing=dict(source='A_actual_App_monotonic',first_progress_ms=None,progress_status='NOT_EMITTED',first_body_ms=20,complete_ms=30),
            before=state.copy(),after=state.copy(),bounded_claim_verified=True,new_message_ids=[wire['message_id']],
            inventory=dict(status='completed',message_input_sha256='d'*64,run_id='run'),
            message=dict(message_id=wire['message_id'],outer_input_sha256=sha256(raw.encode()).hexdigest(),
                canonical_sha256='d'*64,run_id='run',conversation_id='new-zh',answer=answer,
                answer_sha256=sha256(answer.encode()).hexdigest(),native_origin_verified=True)))
    return plan,step,observation,context


def test_dual_hashes_are_distinct_and_all_joint_evidence_needed():
    plan,step,obs,context=fixture()
    assert judge(plan,step,obs,context,PRICING)['status']=='PASS'
    assert len({obs['backend']['message']['outer_input_sha256'],obs['backend']['message']['canonical_sha256'],
                obs['backend']['accounting']['attempts'][0]['actual_wire_input_sha256']})==3
    for key,value in [('outer_input_sha256','d'*64),('canonical_sha256',H),('native_origin_verified',False)]:
        changed=deepcopy(obs);changed['backend']['message'][key]=value
        assert judge(plan,step,changed,context,PRICING)['status']=='UNKNOWN'


def test_A_need_not_export_wire_but_B_actual_outer_is_mandatory():
    plan,step,obs,context=fixture();del obs['ui']['intent_utf8']
    assert judge(plan,step,obs,context,PRICING)['status']=='PASS'
    del obs['backend']['outer_request']
    assert judge(plan,step,obs,context,PRICING)['status']=='UNKNOWN'


@pytest.mark.parametrize('mutation',[
    lambda o:o['ui'].update(answer_visible=False),
    lambda o:o['ui'].update(post_count=2),
    lambda o:o['backend'].update(bounded_claim_verified=False),
    lambda o:o['backend']['after'].update(memory_sha256='e'*64),
    lambda o:o['binding'].update(subject='other-owner'),
    lambda o:o['backend']['outer_request'].update(provenance='reconstructed_from_canonical'),
    lambda o:o['backend']['outer_request'].update(route='/v1/lio/messages'),
    lambda o:o['backend']['outer_request'].update(protected_capture_verified=False),
    lambda o:o['backend']['accounting'].update(producer_closure_verified=False),
    lambda o:o['backend']['accounting']['attempts'][0]['receipt']['usage'].update(total_tokens=999),
])
def test_missing_is_not_filled_by_http_or_completed(mutation):
    plan,step,obs,context=fixture();mutation(obs)
    result=judge(plan,step,obs,context,PRICING)
    assert result['status']=='UNKNOWN'


def test_preserves_charges_when_ui_evidence_later_fails():
    plan,step,obs,context=fixture();obs['ui']['error_visible']=True
    del obs['ui']['answer_visible']
    result=judge(plan,step,obs,context,PRICING)
    assert result['status']=='FAIL'
    assert result['cost']['observed_conservative_cny']=='0.00002'


def test_original_unresolved_hold_and_partial_coverage():
    _,_,obs,_=fixture();account=obs['backend']['accounting']
    account['attempts'][0].update(state='INTENT',receipt=None,conservative_units=10_000_000)
    account.update(coverage='UNKNOWN',producer_closure_verified=False)
    result=costs(account,PRICING)
    assert result['conservative_cny']is None and result['observed_conservative_cny']=='1'
    assert result['actual_paid_cny']is None and result['unresolved_attempt_count']==1
    account['attempts'][0]['conservative_units']=0
    with pytest.raises(Invalid):costs(account,PRICING)


def test_unregistered_or_duplicate_financial_kind_is_not_free():
    _,_,obs,_=fixture();account=obs['backend']['accounting']
    account['attempts'].append(deepcopy(account['attempts'][0]))
    with pytest.raises(Invalid):costs(account,PRICING)
    account['attempts']=account['attempts'][:1];account['attempts'][0]['kind']='new-paid-tool'
    with pytest.raises(Invalid):costs(account,PRICING)


def test_received_tool_missing_price_is_unknown_and_retains_original_hold():
    plan,step,obs,context=fixture();row=obs['backend']['accounting']['attempts'][0]
    row.update(kind='tool',priceable_tool_units=None,conservative_units=30_000)
    result=judge(plan,step,obs,context,PRICING)
    assert result['status']=='UNKNOWN'and result['cost']['observed_conservative_cny']=='0.003'
    assert result['cost']['token_estimate_cny']is None
    row['conservative_units']=0
    assert judge(plan,step,obs,context,PRICING)['status']=='UNKNOWN'


@pytest.mark.parametrize('gate,text,expected',[
    ('SM05','Hello!','UNKNOWN'),('SM05','I am Lio.','PASS'),
    ('SM06','Hello!','UNKNOWN'),('SM06','I help you plan travel in China.','PASS'),
    ('SM02','Beijing is not the capital of China.','FAIL'),
    ('SM02','Is Beijing the capital of China?','UNKNOWN'),
    ('SM02',"I don't know whether Beijing is the capital of China.",'UNKNOWN'),
    ('SM06','I do not offer travel planning services.','FAIL'),
    ('SM06',"I cannot help with travel planning.",'FAIL'),
    ('SM06','I am unable to provide travel planning services.','FAIL'),
    ('SM06','Sorry, travel planning is unavailable.','FAIL'),
    ('SM07','Sure, I will plan Beijing.','FAIL'),
    ('SM07','Beijing: Day 1 Forbidden City. Day 2 Summer Palace. Day 3 Temple of Heaven.','PASS'),
    ('SM07','Beijing: Day 1 sightseeing. Day 2 sightseeing. Day 3 sightseeing.','UNKNOWN'),
])
def test_no_greeting_ack_or_empty_three_days_pass(gate,text,expected):
    assert semantic(gate,text,'en')[0]==expected


def test_chinese_capability_requires_positive_statement():
    assert semantic('SM06','抱歉，我无法规划旅行行程。','zh')[0]=='FAIL'
    assert semantic('SM06','旅行行程规划','zh')[0]=='UNKNOWN'


def test_accepted_multiline_codebank_has_independent_complete_positive_vectors():
    root=Path(__file__).resolve().parents[1]/'basic_chain'
    corpus=json.loads((root/'accepted_codebank.v1.json').read_bytes())
    for locale,row in corpus['cases'].items():
        assert sha256(row['raw_utf8'].encode()).hexdigest()==row['raw_sha256']
        assert semantic_v2('SM06',row['raw_utf8'],locale)[0]=='PASS'
        assert semantic_v2('SM06',row['raw_utf8'].splitlines()[0],locale)[0]!='PASS'


@pytest.mark.parametrize('text,status',[
    ("Yes, Beijing (**北京**) is China's capital.",'PASS'),
    ('Beijing is the capital city of China (**中国**).','PASS'),
    ("China’s capital is Beijing (北京).",'PASS'),
    ('Is Beijing (**北京**) the capital of China?','UNKNOWN'),
    ('Beijing (北京) is not the capital of China.','FAIL'),
    ("I don't know whether Beijing (北京) is China's capital.",'UNKNOWN'),
    ('Yes, Beijing (**上海**) is the capital of China.','UNKNOWN'),
])
def test_v2_accepts_known_bilingual_fact_without_erasing_denial_or_wrong_name(text,status):
    assert semantic_v2('SM02',text,'en')[0]==status


def test_fixed_bilingual_plan_and_no_mid_wildcard():
    plan,*_=fixture();check_plan(plan)
    assert len(plan['steps'])==14 and plan['planned_message_count']==8
    assert all(step['expected_mid']is None for step in plan['steps'])
    plan['steps'][0]['expected_mid']='guessed'
    with pytest.raises(Invalid):check_plan(plan)
    initial=make_plan(app=APP,old_chats={},first_setup=True)
    assert initial['planned_message_count']==12 and len(initial['steps'])==18
    assert initial['execution_profile']['model_call_upper']==80
    assert initial['execution_profile']['total_tool_call_upper']==64
    assert initial['execution_profile']['cash_ceiling_cny']==80


def test_append_only_plan_quote_preserves_legacy_and_never_claims_prefunding():
    legacy=make_plan(app=APP,old_chats={},version='LIO-basic-chain-plan.1')
    assert 'execution_profile'not in legacy
    check_plan(legacy)
    plan=make_plan(app=APP,old_chats={})
    assert plan['execution_profile']['model_call_upper']==40
    assert plan['execution_profile']['total_tool_call_upper']==32
    assert plan['execution_profile']['coarse_sum_if_every_call_reserved_one_cny']==72
    assert plan['budget_ceiling_cny']==60
    plan['execution_profile']['cash_ceiling_cny']=144
    with pytest.raises(Invalid):check_plan(plan)


def test_json_duplicate_nonfinite_and_private_files():
    for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{'):
        with pytest.raises(Invalid):decode(raw)
    with tempfile.TemporaryDirectory()as temporary:
        path=Path(temporary)/'original.json';save(path,{'value':1})
        assert decode(private_read(path))=={'value':1}
        with pytest.raises(FileExistsError):save(path,{})
        path.chmod(0o644)
        with pytest.raises(Invalid):private_read(path)


def test_night_guard_boundary():
    for hour in (15,23): # UTC -> 23:00 and 07:00 CST
        with pytest.raises(Invalid):day_guard(NOW.replace(hour=hour))
    day_guard(NOW.replace(hour=0));day_guard(NOW.replace(hour=14))


def test_preflight_rejects_stale_other_plan_unqualified_or_wrong_owner():
    plan,step,_,_=fixture()
    config=dict(candidate=CANDIDATE,subjects={'zh':'synthetic-zh'},app=APP)
    value=dict(CANDIDATE,version='LIO-basic-chain-preflight.1',subject='synthetic-zh',run_id=plan['run_id'],
        plan_sha256=digest(plan),nonce=step['nonce'],status='ACTIVE',authority_verified=True,
        bounded_app_claims_verified=True,idle_verified=True,capture_ready=True,
        starts_at='2026-11-16T05:30:00+00:00',ends_at='2026-11-16T06:30:00+00:00',
        available_cny='60',required_remaining_hold_cny='56',app=APP)
    preflight(value,config,plan,step,NOW)
    for change in ({'source':'x'},{'subject':'other'},{'plan_sha256':H},
                   {'bounded_app_claims_verified':False},{'available_cny':'1'},
                   {'ends_at':'2026-11-16T05:59:00+00:00'}):
        with pytest.raises(Invalid):preflight(value|change,config,plan,step,NOW)


def test_first_unknown_stops_before_ui_and_keeps_fourteen_denominator():
    plan,*_=fixture();calls=[]
    config=dict(version='LIO-basic-chain-host.1',evidence_layer='L2+L3',app=APP,
                candidate=CANDIDATE,native_authority_ref='test-only-not-a-permit',ledger_anchor_ref='test-only',synthetic_only=True)
    def adapter(name,request):
        calls.append((name,request['action']))
        if request['action']=='preflight':raise Invalid('qualification unavailable')
        return {}
    with tempfile.TemporaryDirectory()as temporary:
        result=execute(plan,config,Path(temporary)/'new',clock=lambda:NOW,call=adapter)
    assert calls==[('backend','preflight'),('backend','stop_new')]
    assert result['totals']==dict(PASS=0,FAIL=0,UNKNOWN=1,UNRUN=13)
    assert result['release_allowed']is False and result['cost']['conservative_cny']is None


def test_fixture_layer_has_no_live_cli_path():
    plan,*_=fixture()
    with pytest.raises(Invalid):execute(plan,{'version':'LIO-basic-chain-host.1','evidence_layer':'L0'},'unused')
    legacy=make_plan(app=APP,old_chats={},version='LIO-basic-chain-plan.1')
    with pytest.raises(Invalid):execute(legacy,{},'unused-legacy')


@pytest.mark.parametrize('failure_at',[None,'zh-SM02','en-SM07','owner-mismatch'])
def test_control_steps_serial_first_failure_stops_and_costs_not_double_counted(failure_at):
    plan,*_=fixture();calls=[]
    config=dict(version='LIO-basic-chain-host.1',evidence_layer='L2+L3',app=APP,candidate=CANDIDATE,
        subjects={'zh':'synthetic-zh','en':'synthetic-en'},pricing=PRICING,
        native_authority_ref='TEST-ONLY',ledger_anchor_ref='TEST-ONLY',synthetic_only=True)
    with tempfile.TemporaryDirectory()as temporary:
        artifact=Path(temporary)/'control.json';save(artifact,{'CONTROL_ONLY':True})
        ref=dict(path=str(artifact),sha256=sha256(artifact.read_bytes()).hexdigest())
        def adapter(name,request):
            calls.append((name,request['action']))
            if request['action']=='stop_new':return {'status':'STOP_NEW'}
            step=request['step'];locale=step['locale'];gate=step['gate_id'];ctx=request['context']
            if request['action']=='preflight':
                return dict(CANDIDATE,version='LIO-basic-chain-preflight.1',subject=config['subjects'][locale],
                    run_id=plan['run_id'],plan_sha256=digest(plan),nonce=step['nonce'],status='ACTIVE',
                    authority_verified=True,bounded_app_claims_verified=True,idle_verified=True,capture_ready=True,
                    starts_at='2026-11-16T05:30:00+00:00',ends_at='2026-11-16T06:30:00+00:00',
                    available_cny='60',required_remaining_hold_cny='56',app=APP,admission_ref='CONTROL')
            _,_,obs,_=fixture();obs.update(gate_id=gate,locale=locale,nonce=step['nonce'])
            obs['binding']['subject']=config['subjects'][locale]
            ui=obs['ui'];backend=obs['backend']
            ui['artifacts']=[ref];backend['artifacts']=[ref]
            if step['text']is None:
                backend.update(new_message_ids=[],expected_message_ids_present=True)
                backend['accounting']['attempts']=[]
                cid=ctx['old_cid']if gate=='SM01'else ctx['qa_cid']
                backend['conversation_id']=cid
                ui.update(before_cid=cid,after_cid=cid,messages_visible=True,draft_before='draft',draft_after='draft',
                    new_greeting_count=0,background_returned=True,lock_returned=True,
                    listed_cids=[ctx['old_cid'],ctx['qa_cid']],selected_cids_verified=True)
            else:
                answers={'zh':{'SM02':'是的，北京是中国的首都。','SM05':'我是 Lio。','SM06':'我可以规划旅行行程。',
                    'SM07':'北京：第一天故宫，第二天颐和园，第三天天坛。'},
                    'en':{'SM02':'Yes, Beijing is the capital of China.','SM05':'I am Lio.',
                    'SM06':'I help you plan travel in China.',
                    'SM07':'Beijing: Day 1 Forbidden City. Day 2 Summer Palace. Day 3 Temple of Heaven.'}}
                answer=answers[locale][gate];answer_sha=sha256(answer.encode()).hexdigest()
                mid=locale+'-'+gate;cid='cid-'+mid
                wire=dict(version=APP['protocol'],message_id=mid,text=step['text'],locale=locale,new_conversation=True)
                ui.update(intent_utf8=json.dumps(wire,ensure_ascii=False),render_source_mid=mid,after_cid=cid,
                          received_answer_sha256=answer_sha,visible_answer=answer,three_day_readback_verified=True)
                backend['message'].update(message_id=mid,conversation_id=cid,answer=answer,answer_sha256=answer_sha,
                    outer_input_sha256=sha256(ui['intent_utf8'].encode()).hexdigest())
                backend['outer_request'].update(utf8=ui['intent_utf8'],sha256=sha256(ui['intent_utf8'].encode()).hexdigest())
                backend.update(new_message_ids=[mid],itinerary_verified=True,claims_saved=False,unrequested_date_or_party=False)
                backend['accounting']['attempts'][0]['attempt_id']=mid
            if locale+'-'+gate==failure_at:ui['error_visible']=True
            if name=='app':return ui
            if failure_at=='owner-mismatch':obs['binding']['subject']='other-owner'
            obs['ui']=request['ui'];return obs
        result=execute(plan,config,Path(temporary)/'run',clock=lambda:NOW,call=adapter)
    count=14 if failure_at is None else 2 if failure_at=='zh-SM02'else 1 if failure_at=='owner-mismatch'else 14
    assert result['totals']==dict(PASS=count-(failure_at is not None),FAIL=int(failure_at in('zh-SM02','en-SM07')),
                                  UNKNOWN=int(failure_at=='owner-mismatch'),UNRUN=14-count)
    assert calls==[('backend','preflight'),('app','one_gate'),('backend','observe_original')]*count+(
        [('backend','stop_new')]if failure_at else[])
    assert result['release_allowed']is False and result['evidence_layer']=='L0_CONTROL'
    assert result['cost']['conservative_cny']==(None if failure_at=='owner-mismatch'else
                                               '0.00002'if failure_at=='zh-SM02'else'0.00016')
    assert result['cost']['actual_paid_cny']is None
