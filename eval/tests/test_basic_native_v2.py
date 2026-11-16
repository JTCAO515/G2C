"""C parser controls over B fact shapes, with no native transport/calls."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from eval.basic_chain.native import checkpoint,observation,collection_pending
from eval.basic_chain.plan import Invalid,digest,make_plan,packed

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
                  policy_sha256='d'*64,scope_sha256=scope_sha)
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
                      ledger_anchor={'count':0,'sha256':H},claims=[]))
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
