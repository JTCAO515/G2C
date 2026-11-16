"""Joint logical controls; synthetic data never grants release acceptance."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from eval.basic_chain.joint_v2 import Conversations,assess,draft_marker
from eval.basic_chain.native import observation
from eval.tests.test_basic_native_v2 import fixture,add_read


def write_fixture():
    host,point,expected,plan,step=fixture();add_read(host,expected)
    original=host['original'];message=original['message'];record=original['http']['actual_reads'][0]
    view=json.loads(record['response_utf8']);view['messages']=[dict(message_id=message['message_id'],text=message['text'],
        answer=message['answer'],status='completed',failure=None,trip=None)]
    record['response_utf8']=json.dumps(view,ensure_ascii=False)
    record['response_sha256']=sha256(record['response_utf8'].encode()).hexdigest()
    original['http']['read_exchanges'][1]['response_sha256']=record['response_sha256']
    native=observation(host,point,expected,plan,step)
    pair={'question':step['text'],'answer':message['answer']}
    ui=dict(version='LIO-basic-app-witness.2',source='actual_ordinary_Home_AX',app=plan['app'],
        run_id=plan['run_id'],gate_id=step['gate_id'],locale=step['locale'],nonce=step['nonce'],
        message_id_observed=None,conversation_id_observed=None,send_taps=1,submitted_text=step['text'],
        artifacts=[{'path':'CONTROL-ONLY','sha256':'a'*64}],before={'transcript':[],'draft':''},
        after=dict(body_complete=True,errors=[],transcript=[pair],draft='',new_greeting_count=0),actions=['new_chat'],
        timing=dict(clock='actual_App_monotonic',first_body_ms=30,complete_ms=40,first_progress_ms=None,progress_status='NOT_OBSERVED'))
    money=dict(full_coverage=True,unresolved_attempt_count=0,price_status='PARTLY_UNKNOWN')
    return plan,step,point,native,ui,Conversations(),money


def evaluate(args):return assess(*args[:6],lambda text:text,args[6])


def test_ui_ids_stay_null_native_single_write_and_actual_read_match():
    args=write_fixture();result=evaluate(args)
    assert result['status']=='PASS'
    assert result['ui_message_id_observed']is result['ui_conversation_id_observed']is None
    assert result['evidence_scope']=='DATA_ASSESSMENT_ONLY_NOT_A_RELEASE_CERTIFICATE'
    assert len(args[5].views)==1 and args[5].qa_cid==args[3].original['message']['conversation_id']


def test_raw_RUN_and_projected_timeline_are_separate_originals():
    args=write_fixture();n=args[3];raw='是的，北京是中国的首都。可以查询官方资料核实。'
    n.original['message']['answer']=raw
    record=n.actual_reads[0];view=json.loads(record['response_utf8'])
    displayed=raw.replace('查询','查看').replace('核实','确认')
    view['messages'][-1]['answer']=displayed
    record['response_utf8']=json.dumps(view,ensure_ascii=False)
    record['response_sha256']=sha256(record['response_utf8'].encode()).hexdigest()
    args[4]['after']['transcript'][-1]['answer']=displayed
    assert evaluate(args)['status']=='PASS'
    assert n.original['message']['answer']==raw
    view['messages'][-1]['answer']=raw
    record['response_utf8']=json.dumps(view,ensure_ascii=False)
    assert evaluate(args)['status']=='UNKNOWN'


@pytest.mark.parametrize('mutate',[
    lambda a:a[4].update(message_id_observed=a[3].original['message']['message_id']),
    lambda a:a[4].update(submitted_text='another question'),
    lambda a:a[4]['after'].update(transcript=[{'question':a[1]['text'],'answer':'local welcome'}]),
    lambda a:a[4]['after'].update(body_complete=False),
    lambda a:a[6].update(full_coverage=False),
    lambda a:a[6].update(unresolved_attempt_count=1),
])
def test_actual_display_or_native_evidence_cannot_be_replaced_by_labels(mutate):
    args=write_fixture();mutate(args)
    assert evaluate(args)['status']=='UNKNOWN'
    assert not args[5].views


def test_known_ui_failure_and_native_side_effect_remain_fail():
    args=write_fixture();args[4]['after']['errors']=['actual UI failure']
    assert evaluate(args)['status']=='FAIL'
    args=write_fixture();args[3].after['memory_sha256']='0'*64
    assert evaluate(args)['status']=='FAIL'


def read_fixture(gate='SM01'):
    plan,_,_,native,ui,context,money=write_fixture()
    cid=native.original['message']['conversation_id'];view=json.loads(native.actual_reads[0]['response_utf8'])
    step=next(s for s in plan['steps']if s['gate_id']==gate and s['locale']=='zh')
    context.views[cid]=view;context.old_cid=context.qa_cid=cid
    point=type('ControlCheckpoint',(),{'claims':({'binding':{'conversation_id':cid}},),'history_targets':()})()
    before=deepcopy(native.after);after=deepcopy(native.after)
    n=type(native)(native.original,before,after,(),native.actual_reads,(),native.read_collection_status)
    ui.update(gate_id=gate,nonce=step['nonce'],send_taps=0,submitted_text=None,actions=['cold_launch'])
    ui['before']=deepcopy(ui['after']);ui['before']['draft']=ui['after']['draft']=draft_marker(plan,step)
    return plan,step,point,n,ui,context,money


def test_restore_needs_actual_App_read_not_cache_and_independent_server_lookup():
    args=read_fixture();assert evaluate(args)['status']=='PASS'
    args=read_fixture();native=args[3]
    missing=type(native)(native.original,native.before,native.after,(),(),(),native.read_collection_status)
    changed=(*args[:3],missing,*args[4:])
    assert evaluate(changed)['status']=='UNKNOWN'


def test_repeated_body_or_incomplete_candidate_census_is_not_unique_restore():
    args=read_fixture();args[5].views['another-cid']=deepcopy(next(iter(args[5].views.values())))
    assert evaluate(args)['status']=='UNKNOWN'
    args=read_fixture();args[4]['after']['draft']=''
    assert evaluate(args)['status']=='UNKNOWN'


def test_both_lifecycle_returns_must_be_observed_not_only_final_repair():
    args=read_fixture('SM04');ui=args[4]
    ui['actions']=['background_return','lock_return']
    ui['lifecycle']=[dict(action=action,transcript=deepcopy(ui['after']['transcript']),draft=ui['after']['draft'],
                         errors=[],body_complete=True)for action in ui['actions']]
    n=args[3];second=deepcopy(n.actual_reads[0]);second['exchange_id']='second-lifecycle-get'
    tworeads=type(n)(n.original,n.before,n.after,(),(*n.actual_reads,second),(),n.read_collection_status)
    amended=(*args[:3],tworeads,*args[4:])
    # Two reads of one fenced parent cannot certify two distinct transitions.
    assert evaluate(amended)['status']=='UNKNOWN'


@pytest.mark.parametrize('number',[0,1])
def test_each_lifecycle_action_needs_its_own_nonce_and_actual_read(number):
    args=read_fixture('SM04');parent=args[1];child=parent['read_actions'][number]
    step=dict(parent,**child,parent_nonce=parent['nonce']);ui=args[4]
    ui.update(nonce=step['nonce'],actions=[step['action']])
    ui['lifecycle']=[dict(action=step['action'],transcript=deepcopy(ui['after']['transcript']),
        draft=ui['after']['draft'],errors=[],body_complete=True)]
    amended=(args[0],step,*args[2:])
    assert evaluate(amended)['status']=='PASS'
    ui['lifecycle'][0]['errors']=['this return failed']
    assert evaluate(amended)['status']=='FAIL'


def test_history_opens_every_unique_native_conversation_not_just_matching_titles():
    plan,_,_,n,ui,context,money=read_fixture()
    step=next(s for s in plan['steps']if s['gate_id']=='SM03'and s['locale']=='zh')
    first_cid=next(iter(context.views));first_view=context.views[first_cid]
    second_cid='lio-dialogue-'+'1'*32;second_view=deepcopy(first_view)
    second_view['conversation_id']=second_cid
    second_view['messages'][0].update(message_id='another-mid',text='Unique old synthetic code',answer='Unique code repeated')
    context.views[second_cid]=second_view
    state=deepcopy(n.after);record=deepcopy(state['native_messages'][0])
    record.update(message_id='another-mid',conversation_id=second_cid)
    state['native_messages'].append(record)
    second=deepcopy(n.actual_reads[0]);second['binding']=dict(second['binding'],conversation_id=second_cid)
    second['exchange_id']='second-history-read';second['response_utf8']=json.dumps(second_view)
    second['response_sha256']=sha256(second['response_utf8'].encode()).hexdigest()
    native=type(n)(n.original,state,state,(),(*n.actual_reads,second),(),n.read_collection_status)
    point=type('ControlCheckpoint',(),{'claims':tuple({'binding':{'conversation_id':cid}}for cid in context.views),'history_targets':()})()
    opened=[dict(row_key=str(index),transcript=[{'question':m['text'],'answer':m['answer']}for m in view['messages']])
            for index,view in enumerate(context.views.values())]
    ui.update(gate_id='SM03',nonce=step['nonce'],actions=['open_history'],
              history=dict(rows=[{'row_key':str(i),'title':'Same truncated title'}for i in range(2)],opened=opened))
    args=(plan,step,point,native,ui,context,money)
    assert evaluate(args)['status']=='PASS'
    ui['history']['opened'][1]['transcript']=deepcopy(ui['history']['opened'][0]['transcript'])
    assert evaluate(args)['status']=='UNKNOWN'
