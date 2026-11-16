"""Joint logical controls; synthetic data never grants release acceptance."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from eval.basic_chain.joint_v2 import Conversations,assess,draft_marker,_views
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
    pair={'question':step['text'],'answer':message['answer'],'visible_failure':False}
    ui=dict(version='LIO-basic-app-witness.2',source='actual_ordinary_Home_AX',app=plan['app'],
        run_id=plan['run_id'],gate_id=step['gate_id'],locale=step['locale'],nonce=step['nonce'],
        message_id_observed=None,conversation_id_observed=None,send_taps=1,submitted_text=step['text'],
        artifacts=[{'path':'CONTROL-ONLY','sha256':'a'*64}],before={'transcript':[],'draft':''},
        after=dict(body_complete=True,errors=[],transcript=[pair],draft='',new_greeting_count=0),actions=['new_chat'],
        timing=dict(clock='actual_App_monotonic',first_body_ms=30,complete_ms=40,first_progress_ms=None,progress_status='NOT_OBSERVED'))
    money=dict(full_coverage=True,unresolved_attempt_count=0,price_status='PARTLY_UNKNOWN')
    return plan,step,point,native,ui,Conversations(),money


def evaluate(args):return assess(*args[:6],lambda text:text,args[6])


def paged_history(count,wire):
    native=write_fixture()[3];cid=native.original['message']['conversation_id']
    messages=[dict(message_id='historical-'+str(i),text='Synthetic question '+str(i),answer='Synthetic answer '+str(i),
                   status='completed',failure=None,trip=None)for i in range(count)]
    state=deepcopy(native.after);template=state['native_messages'][0]
    state['native_messages']=[dict(template,message_id=m['message_id'],sequence=i+1)for i,m in enumerate(messages)]
    records=[];end=count;cursor=None
    while end:
        start=max(0,end-20);next_before=messages[start]['message_id']if start else None
        record=deepcopy(native.actual_reads[0]);record.update(route=f'/v{wire}/lio/timeline',
            exchange_id='historical-page-'+str(len(records)),selector=dict(conversation_id=cid))
        if cursor is not None:record['selector']['before']=cursor
        value=dict(version=f'LIO-timeline.{wire}',conversation_id=cid,messages=messages[start:end],next_before=next_before)
        record['response_utf8']=json.dumps(value);record['response_sha256']=sha256(record['response_utf8'].encode()).hexdigest()
        records.append(record);cursor=next_before;end=start
    return replace(native,after=state,actual_reads=tuple(reversed(records))),cid,messages


@pytest.mark.parametrize('count,wire',[(32,1),(41,1),(41,2)])
def test_complete_current_history_joins_actual_cursor_pages_not_publication_order(count,wire):
    native,cid,messages=paged_history(count,wire)
    original_bytes=[r['response_utf8']for r in native.actual_reads]
    assert _views(native)[cid]['messages']==messages
    assert [r['response_utf8']for r in native.actual_reads]==original_bytes
    assert _views(native)[cid]['view_origin']=='actual_GET_cursor_chain'


def test_old_complete_pre_accept_poll_does_not_replace_the_final_cursor_chain():
    native,cid,messages=paged_history(32,2)
    old=deepcopy(native.actual_reads[-1]);old['exchange_id']='pre-accept-poll'
    value=json.loads(old['response_utf8']);value['messages']=messages[:-1][-20:]
    value['next_before']=value['messages'][0]['message_id']
    old['response_utf8']=json.dumps(value);old['response_sha256']=sha256(old['response_utf8'].encode()).hexdigest()
    repeated=deepcopy(native.actual_reads[-1]);repeated['exchange_id']='same-final-page-polled-again'
    actual=replace(native,actual_reads=(old,*native.actual_reads,repeated))
    assert _views(actual)[cid]['messages']==messages


@pytest.mark.parametrize('fault',['missing_root','missing_older','wrong_cursor','cycle','changed_page'])
def test_incomplete_or_ambiguous_cursor_chains_never_become_a_complete_history(fault):
    native,cid,_=paged_history(41,1);reads=list(native.actual_reads)
    if fault=='missing_root':reads.pop()
    if fault=='missing_older':reads.pop(0)
    if fault=='wrong_cursor':reads[0]['selector']['before']='another-history-cursor'
    if fault=='cycle':
        payload=json.loads(reads[0]['response_utf8']);payload['next_before']=payload['messages'][0]['message_id']
        reads[0]['response_utf8']=json.dumps(payload)
        reads[0]['response_sha256']=sha256(reads[0]['response_utf8'].encode()).hexdigest()
    if fault=='changed_page':
        changed=deepcopy(reads[0]);payload=json.loads(changed['response_utf8']);payload['messages'][0]['answer']='different complete answer'
        changed['response_utf8']=json.dumps(payload);changed['exchange_id']='conflicting-older-page';reads.append(changed)
        changed['response_sha256']=sha256(changed['response_utf8'].encode()).hexdigest()
    assert cid not in _views(replace(native,actual_reads=tuple(reads)))


@pytest.mark.parametrize('field,value',[('trip',{'saved':'card'}),('sources',[{'url':'https://example.com'}]),
                                       ('memory',{'candidate':'different'}),('activity','different')])
@pytest.mark.parametrize('conflict_last',[False,True])
def test_same_cursor_different_complete_wire_fields_cannot_be_selected_by_read_order(field,value,conflict_last):
    args=write_fixture();native=args[3];original=native.actual_reads[0]
    changed=deepcopy(original);page=json.loads(changed['response_utf8']);page['messages'][0][field]=value
    changed['response_utf8']=json.dumps(page);changed['response_sha256']=sha256(changed['response_utf8'].encode()).hexdigest()
    changed['exchange_id']='same-cursor-different-wire'
    reads=(original,changed)if conflict_last else(changed,original)
    amended=(*args[:3],replace(native,actual_reads=reads),*args[4:])
    assert evaluate(amended)['status']=='UNKNOWN'


def test_equivalent_wire_JSON_order_is_not_a_conflicting_page():
    args=write_fixture();native=args[3];other=deepcopy(native.actual_reads[0])
    other['response_utf8']=json.dumps(json.loads(other['response_utf8']),sort_keys=True)
    other['response_sha256']=sha256(other['response_utf8'].encode()).hexdigest();other['exchange_id']='same-data-different-json-order'
    assert evaluate((*args[:3],replace(native,actual_reads=(*native.actual_reads,other)),*args[4:]))['status']=='PASS'


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
    lambda a:a[4]['after'].update(transcript=[{'question':a[1]['text'],'answer':'local welcome','visible_failure':False}]),
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


def test_a_new_native_CID_cannot_replace_an_actual_UI_new_chat():
    args=write_fixture();args[4]['actions']=[]
    assert evaluate(args)['status']=='UNKNOWN'
    args=write_fixture();args[4]['before']['transcript']=deepcopy(args[4]['after']['transcript'])
    assert evaluate(args)['status']=='UNKNOWN'
    args=write_fixture();args[3].after['memory_sha256']='0'*64
    assert evaluate(args)['status']=='FAIL'


def read_fixture(gate='SM01'):
    plan,_,_,native,ui,context,money=write_fixture()
    cid=native.original['message']['conversation_id'];view=json.loads(native.actual_reads[0]['response_utf8'])
    step=next(s for s in plan['steps']if s['gate_id']==gate and s['locale']=='zh')
    context.views[cid]=view;context.old_cid=context.qa_cid=cid
    point=type('ControlCheckpoint',(),{'claims':({'binding':{'conversation_id':cid}},),'history_targets':(),
        'default_history_target':native.default_history_target})()
    before=deepcopy(native.after);after=deepcopy(native.after)
    n=type(native)(native.original,before,after,(),native.actual_reads,(),native.read_collection_status,native.default_history_target)
    ui.update(gate_id=gate,nonce=step['nonce'],send_taps=0,submitted_text=None,actions=['cold_launch'])
    ui['before']=deepcopy(ui['after']);ui['before']['draft']=ui['after']['draft']=draft_marker(plan,step)
    if gate=='SM01':ui['lifecycle']=[dict(action='cold_launch',transcript=deepcopy(ui['after']['transcript']),
        draft=ui['after']['draft'],errors=[],body_complete=True)]
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


def test_cold_restore_failure_cannot_be_repaired_by_later_history_navigation():
    args=read_fixture();args[4]['lifecycle'][0].update(errors=['cold restore failed'],body_complete=False)
    assert evaluate(args)['status']=='FAIL'
    args=read_fixture();args[4]['lifecycle'][0]['body_complete']=False
    assert evaluate(args)['status']=='UNKNOWN'
    args=read_fixture();args[4]['after']['draft']=''
    assert evaluate(args)['status']=='UNKNOWN'


def failed_historical_restore():
    args=read_fixture();native=args[3];cid=args[5].old_cid
    page=json.loads(native.actual_reads[0]['response_utf8']);page['messages'][0].update(status='failed',failure='unavailable',answer='')
    native.actual_reads[0]['response_utf8']=json.dumps(page)
    native.actual_reads[0]['response_sha256']=sha256(native.actual_reads[0]['response_utf8'].encode()).hexdigest()
    args[5].views[cid]=deepcopy(page)
    pair=dict(question=page['messages'][0]['text'],answer=None,visible_failure=True)
    args[4]['before']['transcript']=[deepcopy(pair)];args[4]['after']['transcript']=[deepcopy(pair)]
    args[4]['lifecycle'][0]['transcript']=[deepcopy(pair)]
    return args


def test_loading_a_retained_failed_history_preserves_its_failure_instead_of_regrading_it():
    args=failed_historical_restore()
    result=evaluate(args)
    assert result['status']=='PASS'and result['historical_public_failure_count']==1
    assert args[5].views[args[5].old_cid]['messages'][0]['status']=='failed'


def test_historical_failure_cannot_be_hidden_or_substituted_for_a_new_load_error():
    args=failed_historical_restore();args[4]['after']['transcript'][0]['visible_failure']=False
    assert evaluate(args)['status']=='UNKNOWN'
    args=failed_historical_restore();del args[4]['after']['transcript'][0]['visible_failure']
    assert evaluate(args)['status']=='UNKNOWN'
    args=failed_historical_restore();args[4]['after']['errors']=['new current page load failed']
    assert evaluate(args)['status']=='FAIL'


def test_a_new_failed_message_does_not_acquire_the_old_history_exception():
    args=write_fixture();native=args[3];page=json.loads(native.actual_reads[0]['response_utf8'])
    page['messages'][0].update(status='failed',failure='unavailable',answer='')
    native.actual_reads[0]['response_utf8']=json.dumps(page)
    native.original['inventory']['status']='failed'
    args[4]['after']['transcript'][0].update(answer=None,visible_failure=True)
    assert evaluate(args)['status']=='FAIL'


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
    empty=deepcopy(n.actual_reads[0]);empty.update(exchange_id='actual-empty-default',route='/v1/lio/timeline',
        binding=None,origin='readonly_default',selector={},default_conversation_id=n.default_history_target['conversation_id'],
        default_generation=n.default_history_target['generation'])
    empty['response_utf8']=json.dumps(dict(version='LIO-timeline.1',conversation_id=None,messages=[],next_before=None))
    empty['response_sha256']=sha256(empty['response_utf8'].encode()).hexdigest()
    native=type(n)(n.original,state,state,(),(*n.actual_reads,second,empty),(),n.read_collection_status,n.default_history_target)
    point=type('ControlCheckpoint',(),{'claims':tuple({'binding':{'conversation_id':cid}}for cid in context.views),'history_targets':(),
        'default_history_target':n.default_history_target})()
    opened=[dict(row_key=str(index),body_complete=True,errors=[],transcript=[{'question':m['text'],'answer':m['answer'],'visible_failure':False}for m in view['messages']])
            for index,view in enumerate(context.views.values())]
    opened.append(dict(row_key='default',body_complete=True,errors=[],transcript=[]))
    ui.update(gate_id='SM03',nonce=step['nonce'],actions=['open_history'],
              history=dict(rows=[{'row_key':str(i),'title':'Same truncated title'}for i in range(2)]+[
                  {'row_key':'default','title':'First conversation'}],default_row_key='default',opened=opened))
    args=(plan,step,point,native,ui,context,money)
    assert evaluate(args)['status']=='PASS'
    missing=replace(native,actual_reads=native.actual_reads[:-1])
    assert evaluate((plan,step,point,missing,ui,context,money))['status']=='UNKNOWN'
    ui['history']['default_row_key']='0'
    assert evaluate(args)['status']=='UNKNOWN'
    ui['history']['default_row_key']='default'
    ui['history']['opened']=[opened[-1],*opened[:-1]]
    assert evaluate(args)['status']=='UNKNOWN'
    ui['history']['opened']=opened
    ui['history']['opened'][0].update(errors=['actual row failed to open'],body_complete=False)
    assert evaluate(args)['status']=='FAIL'
    # A known earlier UI failure survives even if another native read is absent.
    assert evaluate((plan,step,point,missing,ui,context,money))['status']=='FAIL'
    ui['history']['opened'][0].update(errors=[],body_complete=False)
    assert evaluate(args)['status']=='UNKNOWN'
    ui['history']['opened'][0].update(errors=[],body_complete=True)
    ui['history']['opened'][1]['transcript']=deepcopy(ui['history']['opened'][0]['transcript'])
    assert evaluate(args)['status']=='UNKNOWN'
