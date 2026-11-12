"""Recipe boundary controls only; no live Lio/model/identity/fee qualification."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from cj_api.runtime_dialogue import NativeDialogue
from cj_message.demo_dialogue import _identity
from runtime_adapter import Binding,Invalid,Unavailable
from runtime_adapter.contract import decode,digest,encode


@pytest.fixture
def recipe():
    path=Path(__file__).resolve().parents[2]/'eval/optimization/cases.v2.json'
    binding=Binding('original-owner','original-session','original-ledger','original-producer')
    source=decode(path.read_bytes());task=next(t for t in source['tasks'] if t['id']=='dev-airport')
    pins=SimpleNamespace(value={'task_sha256':sha256(path.read_bytes()).hexdigest(),'task_version':source['version']})
    setup=dict(kind='task_setup',step_id='runtime-'+digest([binding.scope,'attempt',0]),attempt_id='attempt',prior_step_ids=[],
        payload=dict(task_id=task['id'],language='en',setup=task['setup'],dataset_sha256=pins.value['task_sha256']))
    stored={};writes=[];waited=[]
    context=SimpleNamespace(scope=binding.scope,query_message=stored.get)
    def receive(token,raw,**options):
        data=decode(raw);writes.append((data,options))
        cid='lio-dialogue-'+_identity(binding.scope,'lio-new:'+data['message_id'])
        receipt=SimpleNamespace(conversation_id=cid,run_id='original-run',sequence=1,input_sha256=sha256(raw).hexdigest())
        stored[data['message_id']]=SimpleNamespace(receipt=receipt)
        return receipt
    boundary=SimpleNamespace(with_history_context=lambda token,callback:callback(context),receive_lio=receive)
    claims=SimpleNamespace(binding=binding,pins=pins,read=lambda step,**kwargs:encode(setup),
        query=lambda context,mid:context.query_message(mid))
    db=SimpleNamespace(travel_context=True,needs_context=True,trip_context=True,_provision_scope=lambda *args:None)
    dialogue=NativeDialogue(claims,boundary,db,lambda:'fixture-token',lambda receipt,deadline:waited.append(receipt),dataset_path=path)
    return dialogue,setup,task,stored,writes,waited,db


def execution(task,language='en'):
    return {**{key:task[key] for key in ('id','split','trip_family','setup')},
        'variant':{'turns':task['variants'][language]['turns']}}


def test_prepare_requires_actual_composition_and_exact_public_recipe(recipe):
    dialogue,setup,task,stored,writes,waited,db=recipe
    dialogue.prepare_task(execution(task),'en')
    changed=execution(task);changed['variant']={'turns':['Save an unrelated trip']}
    with pytest.raises(Unavailable,match='TEXT_CHANGED'):dialogue.prepare_task(changed,'en')
    with pytest.raises(Unavailable,match='SETUP_NOT_CONNECTED'):
        dialogue.prepare_task({**execution(task),'id':'val-owner'},'en')
    db.trip_context=False
    with pytest.raises(Unavailable,match='COMPOSITION_NOT_CONNECTED'):dialogue.prepare_task(execution(task),'en')
    assert not writes and not waited


def test_readiness_never_invents_trip_state_or_message_run(recipe):
    dialogue,setup,task,stored,writes,waited,db=recipe
    state=decode(dialogue.setup(setup,deadline=30))
    assert state['first_original'] is None and state['trip_state']=='UNKNOWN'
    assert state['authorized_write']=='none' and not writes and not waited
    first=state['first_message_id']
    stored[first]=SimpleNamespace(receipt=SimpleNamespace(conversation_id='other-chat',sequence=1))
    with pytest.raises(Unavailable,match='FRESH_DIALOGUE_BINDING_CHANGED'):dialogue.setup(setup,deadline=30)


def test_message_uses_original_lio_v2_new_chat_without_defaults_or_extra_turns(recipe):
    dialogue,setup,task,stored,writes,waited,db=recipe
    request=dict(kind='message',step_id='runtime-'+digest([dialogue.claims.binding.scope,'attempt',1]),
        payload={'text':task['variants']['en']['turns'][0]},prior_step_ids=[setup['step_id']])
    dialogue.dispatch(request,deadline=30)
    body,options=writes[0]
    assert body==dict(version='LIO-message.2',message_id=request['step_id'],text=request['payload']['text'],locale='en',new_conversation=True)
    assert options==dict(prepare_scope=db._provision_scope,version='LIO-message.2')
    assert len(writes)==len(waited)==1
    state=decode(dialogue.setup(setup,deadline=30))
    assert state['first_original']['run_id']=='original-run' and state['trip_state']=='UNKNOWN'


def test_changed_message_or_setup_metadata_stops_before_native_admission(recipe):
    dialogue,setup,task,stored,writes,waited,db=recipe
    request=dict(kind='message',step_id='original-mid',payload={'text':'Save a different trip'},prior_step_ids=[setup['step_id']])
    with pytest.raises(Unavailable,match='TEXT_CHANGED'):dialogue.dispatch(request,deadline=30)
    setup['payload']['dataset_sha256']='0'*64
    with pytest.raises(Unavailable,match='RECIPE_BINDING_CHANGED'):dialogue.setup(setup,deadline=30)
    assert not writes and not waited


def test_wrong_source_dataset_is_rejected_before_recipe_use(recipe,tmp_path):
    dialogue,*_=recipe
    path=tmp_path/'changed-cases.json';path.write_bytes(b'{}')
    with pytest.raises(Invalid,match='DATA_PIN_CHANGED'):
        NativeDialogue(dialogue.claims,dialogue.boundary,dialogue.database,dialogue.token_supplier,
            dialogue.wait_original,dataset_path=path)
