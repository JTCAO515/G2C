"""Independent raw surfaces, explicit gaps and same-original read fences."""
import base64
from hashlib import sha256
from types import SimpleNamespace

import pytest

from cj_api.runtime_surface_inventory import NativeSurfaceInventory
from runtime_adapter import Unavailable
from runtime_adapter.contract import decode,encode


@pytest.fixture
def fixture():
    def blob(raw):return dict(sha256=sha256(raw).hexdigest(),bytes_base64=base64.b64encode(raw).decode())
    inventory=dict(message_id='e-original',run_id='e-run',status='completed',operations=[
        dict(operation_id='native-model',attempt_id='attempt-model',kind='model',registration_id='model.answer'),
        dict(operation_id='native-tool',attempt_id='attempt-tool',kind='tool',registration_id='tool.weather')])
    visible=dict(version='G2C-runtime-visible-original.1',message_id='e-original',run_id='e-run',
        input=blob(b'actual original request'),events=[dict(sequence=1,kind='text_delta',value=blob(b'actual published chunk'))],
        tail=dict(delivery_acknowledged=True,associated_history_jobs=[]))
    state=dict(allowed=True,inventory=inventory,visible=visible,missing=set(),calls=[],failure=None)
    def guard():
        if not state['allowed']:raise Unavailable('CURRENT_E_REVOKED')
    def native_inventory(token,mid):guard();state['calls'].append('inventory');return encode(state['inventory'])
    def native_visible(token,mid):guard();state['calls'].append('visible');return encode(state['visible'])
    def logical(token,mid,op):guard();return ('actual logical '+op).encode()
    def artifact(token,mid,op,wire_input=False):
        guard()
        if state['failure']:raise state['failure']
        if(op,wire_input)in state['missing']:raise FileNotFoundError('absent capture')
        return encode({'wire_input_utf8':'actual model HTTP body'}if wire_input else
            {'result_utf8':'actual output '+op})
    originals=SimpleNamespace(inventory=native_inventory,visible_original=native_visible,input=logical,artifact=artifact)
    collector=NativeSurfaceInventory(originals,lambda:'native-E-token',guard=guard)
    return SimpleNamespace(collector=collector,state=state,originals=originals)


def test_original_surfaces_preserve_exact_bytes_without_g_state_copy(fixture):
    result=decode(fixture.collector.collect('e-original'))
    assert result['evidence_status']=='COMPLETE'and not result['missing']
    raw={base64.b64decode(s['bytes_base64'])for s in result['surfaces']}
    assert raw=={b'actual original request',b'actual published chunk',b'actual logical native-model',
        b'actual logical native-tool',b'actual model HTTP body',b'actual output native-model',b'actual output native-tool'}
    assert all(sha256(base64.b64decode(s['bytes_base64'])).hexdigest()==s['sha256']for s in result['surfaces'])
    assert result['privacy_scope']=='TRUSTED_OBSERVER_ONLY_NO_PUBLICATION'


def test_missing_final_or_wire_capture_is_unknown_not_zero(fixture):
    fixture.state['missing']={('native-model',False),('native-model',True)}
    result=decode(fixture.collector.collect('e-original'))
    assert result['evidence_status']=='UNKNOWN'and len(result['missing'])==2
    assert result['operations'][0]['output']is None and result['operations'][0]['wire_input']is None
    assert any(base64.b64decode(s['bytes_base64'])==b'actual published chunk'for s in result['surfaces'])


@pytest.mark.parametrize('field,value',[('status','running'),('ack',False),('ack',None),('job','completed')])
def test_nonterminal_unacked_or_associated_uncaptured_job_never_claims_complete(fixture,field,value):
    if field=='status':fixture.state['inventory']['status']=value
    elif field=='ack':fixture.state['visible']['tail']['delivery_acknowledged']=value
    else:fixture.state['visible']['tail']['associated_history_jobs']=[dict(job_id='original-job',attempt_id='original-attempt',state=value)]
    assert decode(fixture.collector.collect('e-original'))['evidence_status']=='UNKNOWN'


def test_auth_erasure_or_corrupt_capture_is_withheld_not_reclassified_as_absent(fixture):
    for error in (Unavailable('ORIGINAL_PAYLOAD_ERASED'),ValueError('corrupt artifact'),PermissionError('unsafe file')):
        fixture.state['failure']=error
        with pytest.raises(type(error)):fixture.collector.collect('e-original')


def test_original_changes_between_reads_withhold_collection(fixture):
    native=fixture.originals.inventory;count=0
    def changed(*args):
        nonlocal count
        count+=1
        if count==2:fixture.state['inventory']['status']='cancelled'
        return native(*args)
    fixture.originals.inventory=changed
    with pytest.raises(Unavailable,match='INVENTORY_CHANGED'):fixture.collector.collect('e-original')


def test_final_current_guard_rejects_earlier_bytes(fixture):
    original=fixture.originals.visible_original;count=0
    def withdraw(*args):
        nonlocal count
        count+=1
        raw=original(*args)
        if count==2:fixture.state['allowed']=False
        return raw
    fixture.originals.visible_original=withdraw
    with pytest.raises(Unavailable):fixture.collector.collect('e-original')
