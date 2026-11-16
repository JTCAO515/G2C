"""C parser controls over B fact shapes, with no native transport/calls."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from eval.basic_chain.native import checkpoint,observation,collection_pending
from eval.basic_chain.plan import Invalid,digest,make_plan,packed
from cj_message.demo_dialogue import lio_conversation

H='a'*64


def test_only_explicit_HTTP_publication_pending_with_qualified_live_roles_can_wait():
    host,_,expected,_,_=fixture()
    host['original']={'version':'G2C-App-smoke-read.1','status':'UNAVAILABLE','reason':'APP_SMOKE_HTTP_OUTER_PENDING'}
    assert collection_pending(host,expected)
    for reason in('CAPTURE_UNKNOWN','AUTH_UNAVAILABLE','APP_SMOKE_HTTP_OUTER_UNAVAILABLE'):
        host['original']['reason']=reason
        assert not collection_pending(host,expected)
    host['original']['reason']='APP_SMOKE_HTTP_OUTER_PENDING'
    host['actual_roles']['api']['source']='0'*40
    with pytest.raises(Invalid):collection_pending(host,expected)


def fixture():
    scope='synthetic-only-owner';scope_sha=sha256(scope.encode()).hexdigest()
    app=dict(build=46,source_sha='b'*40,artifact_sha256=H,protocol='LIO-message.2')
    plan=make_plan(app=app,old_chats={},first_setup=True,run_id='OFFLINE-NATIVE-CONTROL')
    step=next(s for s in plan['steps']if s['locale']=='zh'and s['gate_id']=='SM02')
    expected=dict(source='c'*40,image='sha256:'+H,qualification_sha256=H,
                  policy_sha256='d'*64,scope_sha256=scope_sha,default_conversation_id=lio_conversation(scope))
    state=dict(version='G2C-App-smoke-state.1',scope_sha256=scope_sha,runtime_role='cj_m1_runtime',
        role_flags=[False]*7,message_ids=[],native_messages=[],messages_sha256=sha256(packed([])).hexdigest(),
        trip_sha256=H,memory_sha256=H,background_rows=[],memory_history_rows=[],pending=0,active=0,
        saved_memory_definition='all non-candidate current items; no extraction-job inference')
    common=dict(version='G2C-App-smoke-read.1',status='READ',source=expected['source'],
        plan_sha256=digest(plan),window_id=plan['run_id'],nonce=step['nonce'],state='ACTIVE',
        policy_sha256=expected['policy_sha256'],scope_sha256=scope_sha)
    roles={key:dict(source=expected['source'],image=expected['image'],running=True,health='healthy')for key in('api','worker')}
    host=dict(version='G2C-App-smoke-host-read.1',qualification_sha256=H,actual_roles=roles,
        original=dict(common,kind='checkpoint',checkpoint_ref=H,native_state=state,
                      ledger_anchor={'count':0,'sha256':H},claims=[],
                      default_history_target=dict(version='LIO-readonly-history-anchor.1',
                          conversation_id=expected['default_conversation_id'],generation=None,messages=[])))
    point=checkpoint(host,expected,plan,step)
    mid='00000000-0000-4000-8000-000000000001';cid='lio-dialogue-'+'e'*32;canonical='f'*64
    wire=dict(version=app['protocol'],message_id=mid,text=step['text'],locale='zh',new_conversation=True)
    raw=json.dumps(wire,ensure_ascii=False);outer_sha=sha256(raw.encode()).hexdigest();answer='是的，北京是中国的首都。'
    binding=dict(scope=scope,conversation_id=cid,generation='generation',message_id=mid,run_id='original-run',message_sequence=1)
    after=deepcopy(state)
    record=dict(message_id=mid,run_id=binding['run_id'],conversation_id=cid,generation=binding['generation'],sequence=1,canonical_sha256=canonical)
    after.update(message_ids=[mid],native_messages=[record],messages_sha256=sha256(packed([[record[k]for k in(
        'message_id','run_id','conversation_id','generation','sequence','canonical_sha256')]])).hexdigest())
    original=dict(common,kind='observe',before=deepcopy(state),after=after,
        claim=dict(binding=binding,slot_id='zh.SM02',input_sha256=outer_sha,canonical_sha256=canonical),
        message=dict(message_id=mid,conversation_id=cid,generation=binding['generation'],run_id=binding['run_id'],sequence=1,
            input_sha256=outer_sha,canonical_sha256=canonical,text=step['text'],locale='zh',protocol=app['protocol'],
            answer=answer,answer_sha256=sha256(answer.encode()).hexdigest()),
        outer_request=dict(binding=binding,slot_id='zh.SM02',source_commit=expected['source'],policy_sha256=expected['policy_sha256'],
            outer_utf8=raw,input_sha256=outer_sha,canonical_sha256=canonical,method='POST',route='/v2/lio/messages',protocol=app['protocol']),
        inventory=dict(message_input_sha256=canonical,run_id=binding['run_id'],status='completed',operations=[]),components=[],
        http=dict(http_coverage='OBSERVED',read_coverage='OBSERVED',unknown_read_exchanges=[],pending_read_exchanges=[],read_exchanges=[],
            post_count=1,actual_reads=[],post_exchanges=[
            dict(phase='started',exchange_id='actual-exchange',policy_sha256=expected['policy_sha256'],scope_sha256=scope_sha,method='POST',route='/v2/lio/messages'),
            dict(phase='finished',exchange_id='actual-exchange',policy_sha256=expected['policy_sha256'],scope_sha256=scope_sha,method='POST',route='/v2/lio/messages',
                 status=200,message_id=mid,body_fully_observed=True,input_sha256=outer_sha)]))
    observed=dict(host,original=original)
    return observed,point,expected,plan,step


def test_actual_server_checkpoint_and_distinct_outer_canonical_join():
    host,point,expected,plan,step=fixture()
    result=observation(host,point,expected,plan,step)
    assert result.new_message_ids==(host['original']['message']['message_id'],)
    assert host['original']['message']['input_sha256']!=host['original']['message']['canonical_sha256']
    assert result.before==point.native_state


@pytest.mark.parametrize('mutate',[
    lambda x:x['actual_roles']['api'].update(source='0'*40),
    lambda x:x.update(qualification_sha256='0'*64),
    lambda x:x['original'].update(nonce='wrong'),
    lambda x:x['original']['before'].update(trip_sha256='0'*64),
    lambda x:x['original']['after']['role_flags'].__setitem__(0,True),
    lambda x:x['original']['http'].update(http_coverage='UNKNOWN',post_count=None,observed_post_count=1),
    lambda x:x['original']['http']['post_exchanges'].append(deepcopy(x['original']['http']['post_exchanges'][0])),
    lambda x:x['original']['claim'].update(slot_id='zh.SM05'),
    lambda x:x['original']['outer_request'].update(input_sha256='0'*64),
    lambda x:x['original']['message'].update(canonical_sha256='0'*64),
    lambda x:x['original']['http']['post_exchanges'][1].update(message_id='another-mid'),
])
def test_actual_native_provenance_never_uses_client_before_or_observed_subtotal(mutate):
    host,point,expected,plan,step=fixture();mutate(host)
    with pytest.raises(Invalid):observation(host,point,expected,plan,step)


def test_components_cannot_turn_unavailable_bytes_into_a_tool_proof():
    host,point,expected,plan,step=fixture()
    host['original']['components']=[dict(operation={'operation_id':'op'},
        tool_artifact={'status':'UNAVAILABLE','utf8':'{}','sha256':sha256(b'{}').hexdigest()})]
    with pytest.raises(Invalid):observation(host,point,expected,plan,step)


def add_read(host,expected):
    original=host['original'];binding=original['claim']['binding']
    raw=json.dumps(dict(version='LIO-timeline.2',conversation_id=binding['conversation_id'],messages=[],next_before=None))
    record=dict(source_commit=expected['source'],policy_sha256=expected['policy_sha256'],scope_sha256=expected['scope_sha256'],
        method='GET',status=200,route='/v2/lio/timeline',selector={'conversation_id':binding['conversation_id']},
        response_utf8=raw,response_sha256=sha256(raw.encode()).hexdigest(),exchange_id='current-get',binding=deepcopy(binding))
    original['http']['actual_reads']=[record]
    base={key:record[key]for key in('method','route','policy_sha256','scope_sha256','exchange_id')}
    original['http']['read_exchanges']=[dict(base,phase='started'),
        dict(base,phase='finished',status=200,selector=record['selector'],body_fully_observed=True,response_sha256=record['response_sha256']),
        dict(base,phase='capture_result',capture_status='CAPTURED')]


def add_default_read(host,expected,point):
    add_read(host,expected)
    record=host['original']['http']['actual_reads'][0]
    record.update(origin='readonly_default',route='/v1/lio/timeline',selector={},binding=None,
                  default_conversation_id=point.default_history_target['conversation_id'],
                  default_generation=point.default_history_target['generation'])
    record['response_utf8']=json.dumps(dict(version='LIO-timeline.1',conversation_id=None,messages=[],next_before=None))
    record['response_sha256']=sha256(record['response_utf8'].encode()).hexdigest()
    for exchange in host['original']['http']['read_exchanges']:
        exchange['route']=record['route']
        if exchange['phase']=='finished':exchange.update(selector={},response_sha256=record['response_sha256'])
    return record


@pytest.mark.parametrize('fault',[None,'wrong_owner','wrong_head','ordinary_unbound','query_CID','wrong_response_CID','lost_GET','changed_default_census'])
def test_actual_empty_default_has_no_fabricated_MESSAGE_but_requires_owner_head_and_GET_proof(fault):
    host,point,expected,plan,step=fixture();record=add_default_read(host,expected,point)
    if fault=='wrong_owner':record['default_conversation_id']='lio-dialogue-'+'0'*32
    if fault=='wrong_head':record['default_generation']='invented-generation'
    if fault=='ordinary_unbound':record.pop('origin')
    if fault=='query_CID':record['selector']={'conversation_id':expected['default_conversation_id']}
    if fault=='wrong_response_CID':
        payload=json.loads(record['response_utf8']);payload['conversation_id']='lio-dialogue-'+'0'*32
        record['response_utf8']=json.dumps(payload);record['response_sha256']=sha256(record['response_utf8'].encode()).hexdigest()
        host['original']['http']['read_exchanges'][1]['response_sha256']=record['response_sha256']
    if fault=='lost_GET':host['original']['http']['read_exchanges']=[]
    if fault=='changed_default_census':
        host['original']['after']['native_messages'][0]['conversation_id']=expected['default_conversation_id']
        # Refresh the digest so this control reaches the default-specific census check.
        row=host['original']['after']['native_messages'][0]
        host['original']['after']['messages_sha256']=sha256(packed([[row[k]for k in(
            'message_id','run_id','conversation_id','generation','sequence','canonical_sha256')]])).hexdigest()
    if fault is None:
        observed=observation(host,point,expected,plan,step)
        assert observed.actual_reads[0]['binding']is None
        assert observed.default_history_target['messages']==[]
    else:
        with pytest.raises(Invalid):observation(host,point,expected,plan,step)


def test_nonempty_default_retains_its_real_old_MESSAGE_binding_and_census():
    host,point,expected,plan,step=fixture()
    old=dict(message_id='00000000-0000-4000-8000-000000000002',run_id='old-default-run',
        conversation_id=expected['default_conversation_id'],generation='old-default-generation',sequence=1,canonical_sha256='1'*64)
    def add_old(state):
        state=deepcopy(state);state['native_messages'].append(deepcopy(old))
        state['message_ids']=[row['message_id']for row in state['native_messages']]
        state['messages_sha256']=sha256(packed([[row[k]for k in(
            'message_id','run_id','conversation_id','generation','sequence','canonical_sha256')]
            for row in state['native_messages']])).hexdigest()
        return state
    original=host['original'];original['before']=add_old(original['before']);original['after']=add_old(original['after'])
    target=dict(version='LIO-readonly-history-anchor.1',conversation_id=old['conversation_id'],generation=old['generation'],
        messages=[{key:old[key]for key in('message_id','run_id','sequence','canonical_sha256')}])
    point=replace(point,native_state=original['before'],default_history_target=target)
    record=add_default_read(host,expected,point)
    record['binding']=dict(scope='synthetic-only-owner',conversation_id=old['conversation_id'],generation=old['generation'],
        message_id=old['message_id'],run_id=old['run_id'],message_sequence=old['sequence'])
    record['response_utf8']=json.dumps(dict(version='LIO-timeline.1',conversation_id=old['conversation_id'],next_before=None,
        messages=[dict(message_id=old['message_id'],text='Old default question',answer='Old default answer',status='completed',failure=None)]))
    record['response_sha256']=sha256(record['response_utf8'].encode()).hexdigest()
    original['http']['read_exchanges'][1]['response_sha256']=record['response_sha256']
    assert observation(host,point,expected,plan,step).actual_reads[0]['binding']['message_id']==old['message_id']
    record['binding']['generation']='another-old-head'
    with pytest.raises(Invalid):observation(host,point,expected,plan,step)


def test_actual_read_requires_current_request_exchange_not_late_publication():
    host,point,expected,plan,step=fixture();add_read(host,expected)
    assert len(observation(host,point,expected,plan,step).actual_reads)==1
    host['original']['http']['read_exchanges']=[] # old request published late
    with pytest.raises(Invalid):observation(host,point,expected,plan,step)


def test_pending_collection_is_explicit_and_never_same_as_fully_observed():
    host,point,expected,plan,step=fixture()
    http=host['original']['http'];http.update(read_coverage='PENDING',pending_read_exchanges=['still-running'])
    http['read_exchanges']=[dict(phase='started',method='GET',exchange_id='still-running',route='/v2/lio/timeline',
        scope_sha256=expected['scope_sha256'],policy_sha256=expected['policy_sha256'])]
    assert observation(host,point,expected,plan,step).read_collection_status=='PENDING'
    http['read_coverage']='OBSERVED'
    with pytest.raises(Invalid):observation(host,point,expected,plan,step)
