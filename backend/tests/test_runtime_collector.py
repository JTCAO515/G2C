"""Erasure projection controls with controlled native readers, no dispatch."""
from types import SimpleNamespace

import pytest

from cj_api.runtime_collector import RuntimeCollector
from runtime_adapter import Binding,Unavailable
from runtime_adapter.contract import decode,encode


def test_erased_input_withholds_old_state_result_and_opaque_reference(tmp_path):
    tmp_path.chmod(0o700)
    binding=Binding('original-owner','original-session','original-ledger','original-producer')
    mid='runtime-'+'a'*64
    request=dict(kind='message',step_id=mid,attempt_id='original-attempt',payload={'text':'Synthetic'},candidate={})
    state=dict(erased=False,reads=0)
    stored=SimpleNamespace(receipt=SimpleNamespace(conversation_id='chat',generation='generation',sequence=1,run_id='run'))
    context=SimpleNamespace(scope=binding.scope,query_message=lambda message_id:stored)
    def inventory(token,message_id):
        return encode(dict(run_id='run',status='completed',operations=[dict(operation_id='operation',input_erased=state['erased'])]))
    originals=SimpleNamespace(inventory=inventory,boundary=SimpleNamespace(with_history_context=lambda token,project:project(context)))
    claims=SimpleNamespace(binding=binding,read=lambda *args,**kwargs:encode(request),query=lambda context,mid:context.query_message(mid))
    def private_state(token,message_id):
        assert not state['erased'],'erased raw state must never be read'
        state['reads']+=1
        return encode({'private':'synthetic original value'})
    collector=RuntimeCollector(originals,claims,SimpleNamespace(request=lambda native:request),lambda:'fixture-token',
        SimpleNamespace(key='b'*64),tmp_path,guard=lambda **kwargs:None,state_reader=private_state,model_reader=None)
    reference=collector.refs.issue('fixture-token',kind='state',message_id=mid)
    assert state['reads']==1 and b'synthetic original value' not in next(tmp_path.iterdir()).read_bytes()
    state['erased']=True
    for kind in ('state','result'):
        with pytest.raises(Unavailable,match='PAYLOAD_ERASED'):collector.projection('fixture-token',kind,mid,None)
    with pytest.raises(Unavailable,match='PAYLOAD_ERASED'):collector.refs.resolve('fixture-token',reference['ref'])
    action=decode(collector.projection('fixture-token','action',mid,None))
    assert action['status']=='UNKNOWN' and action['result'] is None and action['state_evidence']==[]
    assert state['reads']==1
