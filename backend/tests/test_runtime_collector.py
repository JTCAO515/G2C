"""Erasure projection controls with controlled native readers, no dispatch."""
from types import SimpleNamespace

import pytest

from cj_api.runtime_collector import RuntimeCollector
from runtime_adapter import Binding,Unavailable
from runtime_adapter.contract import decode,encode
from test_runtime_run_requests import routing


@pytest.mark.parametrize('kind',['message','task_setup'])
def test_erased_input_withholds_old_state_result_and_opaque_reference(tmp_path,kind):
    tmp_path.chmod(0o700)
    binding=Binding('original-owner','original-session','original-ledger','original-producer')
    mid='runtime-'+'a'*64
    request=dict(kind=kind,step_id=mid,attempt_id='original-attempt',payload=({'text':'Synthetic'} if kind=='message' else
        {'task_id':'val-deleted-recall','language':'en'}),candidate={})
    state=dict(erased=False,reads=0)
    stored=SimpleNamespace(receipt=SimpleNamespace(conversation_id='chat',generation='generation',sequence=1,run_id='run'))
    context=SimpleNamespace(scope=binding.scope,query_message=lambda message_id:stored)
    def inventory(token,message_id):
        return encode(dict(run_id='run',status='completed',operations=[dict(operation_id='operation',registration_id='model.answer',input_erased=state['erased'])]))
    originals=SimpleNamespace(inventory=inventory,boundary=SimpleNamespace(with_history_context=lambda token,project:project(context)))
    claims=SimpleNamespace(binding=binding,read=lambda *args,**kwargs:encode(request),query=lambda context,mid:context.query_message(mid))
    def private_state(token,message_id):
        assert not state['erased'],'erased raw state must never be read'
        state['reads']+=1
        return encode({'private':'synthetic original value'})
    def setup_proof(*args,**kwargs):raise AssertionError('erased preparation must not read old Memory action data')
    collector=RuntimeCollector(originals,claims,SimpleNamespace(request=lambda native:request),lambda:'fixture-token',
        SimpleNamespace(key='b'*64),tmp_path,guard=lambda **kwargs:None,state_reader=private_state,model_reader=None,dialogue=SimpleNamespace(setup=setup_proof))
    reference=collector.refs.issue('fixture-token',kind='state',message_id=mid)
    assert state['reads']==1 and b'synthetic original value' not in next(tmp_path.iterdir()).read_bytes()
    state['erased']=True
    for kind in ('state','result'):
        with pytest.raises(Unavailable,match='PAYLOAD_ERASED'):collector.projection('fixture-token',kind,mid,None)
    with pytest.raises(Unavailable,match='PAYLOAD_ERASED'):collector.refs.resolve('fixture-token',reference['ref'])
    action=decode(collector.projection('fixture-token','action',mid,None))
    assert action['status']=='UNKNOWN' and action['result'] is None and action['state_evidence']==[]
    assert state['reads']==1


@pytest.mark.parametrize('changed',['text','native_digest','run'])
def test_original_request_checks_actual_native_input_not_only_same_mid(tmp_path,routing,changed):
    resolver,bound,state,_=routing;resolver.claims.history_profile='lio.2'
    tmp_path.chmod(0o700)
    record=dict(run_id=bound.run_id,status='completed',operations=[])
    originals=SimpleNamespace(inventory=lambda token,mid:encode(record),boundary=resolver.boundary)
    collector=RuntimeCollector(originals,resolver.claims,resolver,lambda:'fixture-token',
        SimpleNamespace(key='b'*64),tmp_path,guard=lambda **kwargs:None,
        state_reader=None,model_reader=None,clock=lambda:0)
    assert collector.original_request(bound.message_id,deadline=100)==encode(state['request'])
    if changed=='text':state['text']='another same-MID text'
    elif changed=='native_digest':state['native_digest']='d'*64
    else:record['run_id']='another-run'
    with pytest.raises(Unavailable):collector.original_request(bound.message_id,deadline=100)
