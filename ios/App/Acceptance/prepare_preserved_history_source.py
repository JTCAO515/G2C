"""Real retained formal history after public MEMORY-ERASURE@1; no SQL source seed."""
from datetime import datetime, timedelta, timezone
import base64
from dataclasses import replace
import hashlib
import json
import os
import uuid


def prepare_preserved_history(connection, auth, context, subjects, tokens, directory, registry_path):
    from fastapi.testclient import TestClient
    import dev_auth, message_trip_profile
    from run_worker import run_once
    from cj_api.local_app import create_local_app, LocalDatabase, load_confirmation_signer, load_history_configuration
    from cj_api.local_cleanup import load_configuration
    from cj_agent.provider import FakeProvider
    from cj_trip.local_needs_app import create_local_needs_app
    from cj_trip.local_structured_read import create_local_structured_read_app
    from cj_memory.manual import ManualPolicy
    from cj_memory.typed_local import TypedConfiguration
    from cj_memory.typed_api import create_local_typed_app
    from cj_memory_jobs.extraction import CollectionPolicy
    from cj_memory_withdrawal.erasure_app import create_erasure_app_v2
    from cj_memory_withdrawal.erasure_service import ORDER
    from cj_cleanup.memory_payloads import hooks, hold_payloads
    from cj_cleanup.registry import freeze_controls

    def packed(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

    def expect(response):
        assert response.status_code == 200, ('signed retained-history source status', response.status_code)
        return response.json()

    actor = subjects['A']; headers = {'Authorization':'Bearer '+tokens['A']}
    binary = {**headers, 'Content-Type':'application/octet-stream'}
    for subject in subjects.values():
        assert dev_auth.activate_travel(connection, subject, context, 'MESSAGE-TRAVEL-CONSUMER@1') == 'activated'
    signer = load_confirmation_signer(auth)
    creation = create_local_app(conninfo_path=connection, auth_dir=auth, run_context=context,
        travel_context=True, needs_profile='manual-v1', confirmation_signer=signer)
    database = LocalDatabase(connection, run_context=context, travel_context=True, needs_context=True)
    planning = 'planning-'+uuid.uuid4().hex; needs = 'needs-'+uuid.uuid4().hex
    with TestClient(creation) as client:
        expect(client.post('/v1/needs-actions', content=packed(dict(action_id=str(uuid.uuid4()),needs_id=needs,
            expected_version=0,source=dict(kind='manual',text='Explicit local operator party size'),
            changes=dict(party_size=dict(state='known',value=1)))), headers=binary))
        head = expect(client.put('/v1/conversations', params={'conversation_id':planning}, headers=headers))
        expect(client.post('/v2/messages', content=packed(dict(version='MESSAGE-send.2',conversation_id=planning,
            message_id=str(uuid.uuid4()),text='请安排北京行程，保留中文地点',trip_id=None,creation_intent='consider_trip',
            expected_generation=head['generation'],expected_sequence=0,travel_context=None,
            needs_reference=dict(id=needs,expected_version=1))), headers=binary))
        model = FakeProvider(); result = run_once(database, model, auth)
        assert len(result)==1 and result[0].status=='completed' and model.calls==2
        proposal = expect(client.get('/v1/trip-proposals', params={'proposal_id':result[0].proposal_id}, headers=headers))['proposal']
        confirmation = expect(client.post('/v1/trip-confirmations', json=dict(action_id=str(uuid.uuid4()),kind='accept',
            proposal_id=proposal['proposal_id'],candidate_hash=proposal['candidate_hash']), headers=headers))
        accepted = expect(client.post('/v1/trip-actions',content=base64.b64decode(confirmation['action_utf8_base64']),headers=binary))['receipt']
        trip = expect(client.get('/v1/trip-details',params={'trip_id':accepted['trip_id']},
            headers={**headers,'X-CJ-Trip-Content':'provenance.1'}))['trip']
    original_trip = base64.b64decode(trip['content_utf8_base64'])
    unknown = {key:dict(state='unknown') for key in ('date','time','timezone','utc_offset')}
    initialization = dict(version='TRIP-initialize.1',request_id=str(uuid.uuid4()),trip_id=trip['trip_id'],
        expected_version=trip['version'],original_hash=hashlib.sha256(original_trip).hexdigest(),
        items=[dict(id=item['id'],schedule=dict(start=unknown,end=unknown),fixed=dict(state='known',value=False)) for item in trip['document']['items']])
    with TestClient(create_local_needs_app(conninfo_path=connection,auth_dir=auth,run_context=context,confirmation_signer=signer)) as client:
        prepared = expect(client.post('/v1/trip-source-initializations', content=packed(dict(version='TRIP-source-initialize.1',
            needs_reference=dict(id=needs,expected_version=1),initialization=initialization)), headers=binary))['preparation']
        assert prepared['item_source_association']['status']=='UNKNOWN'
        receipt = expect(client.post('/v1/trip-source-initialization-saves', content=packed(dict(version='TRIP-source-initialize-save.1',
            action_id=str(uuid.uuid4()),proposal_id=prepared['proposal_id'],candidate_hash=prepared['candidate_hash'])), headers=binary))['receipt']
        assert receipt['trip_id']==trip['trip_id'] and receipt['committed_version']==trip['version']+1
    structured = create_local_structured_read_app(conninfo_path=connection,auth_dir=auth,run_context=context)
    with TestClient(structured) as client:
        retained_trip = expect(client.get('/v5/trip-structured',params={'trip_id':trip['trip_id']},headers=headers))['trip']
    for subject in subjects.values():
        assert message_trip_profile.activate(connection,subject,context,'MESSAGE-TRIP-CONSUMER@1')=='activated'
    human = create_local_app(conninfo_path=connection,auth_dir=auth,run_context=context,travel_context=True,
        trip_context=True,history_configuration=load_history_configuration(auth),confirmation_signer=signer)
    conversation = 'formal-history-'+uuid.uuid4().hex; message = str(uuid.uuid4()); text = '请说明这份正式行程，保留原聊天与回答'
    with TestClient(human) as client:
        head = expect(client.put('/v1/conversations',params={'conversation_id':conversation},headers=headers))
        original = packed(dict(version='MESSAGE-send.3',conversation_id=conversation,message_id=message,text=text,trip_id=None,
            creation_intent='none',expected_generation=head['generation'],expected_sequence=0,travel_context=None,needs_reference=None,
            trip_context=dict(id=trip['trip_id'],expected_version=retained_trip['version'],day=None,item_id=None)))
        accepted_message = expect(client.post('/v3/messages',content=original,headers=binary))['receipt']
        formal_model = FakeProvider(); outcomes = run_once(LocalDatabase(connection,run_context=context,travel_context=True,trip_context=True),formal_model,auth)
        assert len(outcomes)==1 and outcomes[0].status=='completed' and formal_model.calls==1
        before = expect(client.get('/v6/run-display',params={'message_id':message},headers=headers))
        assert before['source_state']=='retained' and before['reference'] is not None

    expiry = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    profile = dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    typed = TypedConfiguration.from_bytes(packed(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=expiry,profiles={s:profile for s in subjects.values()}),travel_contexts={s:[] for s in subjects.values()})))
    item = str(uuid.uuid4())
    with TestClient(create_local_typed_app(conninfo_path=connection,auth_dir=auth,configuration=typed)) as client:
        saved = expect(client.post('/v2/memories',content=packed(dict(version='MEMORY-manual.2',operation_id=str(uuid.uuid4()),
            item_id=item,subject='self',slot='pace',kind='preference',text='我明确保存轻松节奏偏好',extent='long_term',context=None,occurred_at='时间不详')),headers=binary))['receipt']
    full = json.loads(registry_path.read_bytes())
    def select(node,parent=''):
        name=parent+node['id'];children=node.get('objects',[])
        nested=[x for x in children if isinstance(x,dict)]
        if nested:
            assert len(nested)==len(children)
            selected=[v for child in nested if (v:=select(child,name+'/')) is not None]
            return dict(node,objects=selected) if selected else None
        return node if name in ORDER or name.startswith('cleanup-control/') else None
    projected=directory/'memory-registry.json';projected.write_bytes(packed(dict(version='actual-memory-human-history-projection',
        stores=[v for node in full['stores'] if (v:=select(node)) is not None])))
    frozen=freeze_controls(projected.read_bytes(),ORDER,versions=('CLEANUP@1.0','CLEANUP@1.1'))
    from check_account_cleanup_component import FULL_INVENTORY
    actual=freeze_controls(registry_path.read_bytes(),FULL_INVENTORY,versions=('CLEANUP@1.0','CLEANUP@1.1'))
    assert not actual.gaps
    assert not frozen.gaps and dict(frozen.retained_controls)==dict(actual.retained_controls)
    entries={e.registry_id:e for e in actual.entries};assert all(e==entries[e.registry_id] for e in frozen.entries)
    key=directory/'cleanup.key';key.write_bytes(os.urandom(32));key.chmod(0o600)
    config=directory/'cleanup.json';config.write_bytes(packed(dict(version='CJ-LOCAL-CLEANUP@3',key_file=str(key),key_id='human',lifetime_seconds=7200,inventory=list(ORDER))));config.chmod(0o600)
    options=replace(load_configuration(config),registry_path=projected)
    extraction=CollectionPolicy(frozenset({'self'}),frozenset({'pace'}),5,4096,lambda entry:True,lambda entry,rows:False)
    memory=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term'}),frozenset(),datetime.fromisoformat(expiry),lambda command,raw:True,lambda command,raw:True)
    erasure=create_erasure_app_v2(conninfo_path=connection,auth_dir=auth,resolve_collection=lambda p:(extraction,memory,lambda e:(None,None)),
        cleanup_configuration=options,resolve_backend_hooks=hooks,hold_payloads=hold_payloads,run_context=context)
    with TestClient(erasure) as client:
        erased=expect(client.post('/v1/memory-erasures',content=packed(dict(version='MEMORY-ERASURE@1',action_id=str(uuid.uuid4()),
            item_id=item,expected_version=saved['version'],derived_range='owned_trip_derived_scope')),headers=binary))['result']
        assert erased['stop_use']=='stopped' and erased['online_status']=='complete'
    with TestClient(human) as client:
        history=expect(client.get('/v5/message-history',params={'conversation_id':conversation,'limit':20},headers=headers))
        row=history['messages'][0];assert row['source_state']=='erased' and row['reference'] is None
        assert base64.b64decode(row['original_utf8_base64'])==original and row['text']==text
        after=expect(client.get('/v6/run-display',params={'message_id':message},headers=headers))
        assert after['source_state']=='erased' and after['reference'] is None and after['snapshot']==before['snapshot']
        assert client.get('/v2/message-history',params={'conversation_id':conversation,'limit':20},headers=headers).status_code==503
        assert client.get('/v3/run-display',params={'message_id':message},headers=headers).status_code==503
        assert client.get('/v5/message-history',params={'conversation_id':conversation,'limit':20},headers={'Authorization':'Bearer '+tokens['B']}).status_code!=200
    with TestClient(structured) as client:
        assert expect(client.get('/v5/trip-structured',params={'trip_id':trip['trip_id']},headers=headers))['trip']==retained_trip
    return human, dict(conversation_id=conversation,message_id=message,text=text,answer=after['snapshot']['text'],
        original_sha256=hashlib.sha256(original).hexdigest(),trip_id=trip['trip_id'],trip_version=retained_trip['version'],
        source_state='erased',provider_calls=model.calls+formal_model.calls,operation_id=erased['operation_id'])
