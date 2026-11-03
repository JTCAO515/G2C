"""Actual model/source2/model planning across a signed Memory deletion."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient

from cj_api.local_app import LocalDatabase,create_local_app,load_confirmation_signer,scope_for,ISSUER
from cj_api.local_cleanup import Configuration
from cj_api.local_plan_model import NeedsPlanFakeProvider,CurrentTripPlanFakeProvider
from cj_cleanup.core import encode
from cj_cleanup.memory_payloads import hooks,hold_payloads
from cj_draft.needs_publisher import SYSTEM
from cj_memory.typed_api import create_local_typed_app
from cj_memory.typed_local import TypedConfiguration
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_withdrawal.erasure_app import create_erasure_app_v2
from cj_memory_withdrawal.erasure_service import ORDER
from cj_run.core import Binding
from cj_trip.domain import packed
from cj_trip.local_needs_app import create_local_needs_app
from cj_agent.draft import trip_scope_for
from memory_test_inventory import write_inventory


def exercise(case):
    from edit_support import CONNINFO
    from registered_host_support import RegisteredHost
    from needs_creation_pg import fixed
    import dev_auth,run_worker
    path=Path(CONNINFO);who='signed-source2-erasure'
    host=RegisteredHost(case.auth/who,path,{who:(30,2,30000)})
    auth=host.auth;context=host.profiles[who][1];owner=scope_for(ISSUER,who)
    dev_auth.activate_travel(path,who,context,'MESSAGE-TRAVEL-CONSUMER@1')
    database=LocalDatabase(path,run_context=context,travel_context=True)
    signer=load_confirmation_signer(auth);headers={**host.headers[who],'Content-Type':'application/octet-stream'}
    app=create_local_app(conninfo_path=path,auth_dir=auth,run_context=context,travel_context=True,
                         needs_profile='manual-v1',confirmation_signer=signer)
    needs=create_local_needs_app(conninfo_path=path,auth_dir=auth,run_context=context,confirmation_signer=signer)
    def post(client,route,value):
        response=client.post(route,content=packed(value),headers=headers)
        case.assertEqual(response.status_code,200,response.text);return response.json()
    with TestClient(app) as client:
        post(client,'/v1/needs-actions',dict(action_id='source',needs_id='visit',expected_version=0,
            source=dict(kind='manual',text='Explicit source'),changes=dict(fixed_items=[fixed('a','09:00','10:00',True),fixed('b','11:00','12:00',False)])))
        namespace=post(client,'/v1/travel-context-actions',dict(version='TRAVEL-context-action.1',action_id='namespace',
            operation='create',travel_context=None))['receipt']['travel_context']
    def send(key,text):
        with TestClient(app) as client:
            response=client.put('/v1/conversations',params={'conversation_id':key},headers=headers)
            case.assertEqual(response.status_code,200,response.text);head=response.json()
            raw=packed(dict(version='MESSAGE-send.2',conversation_id=key,message_id=key,text=text,trip_id=None,
                creation_intent='consider_trip',expected_generation=head['generation'],expected_sequence=0,
                travel_context=dict(id=namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            response=client.post('/v2/messages',content=raw,headers=headers)
            case.assertEqual(response.status_code,200,response.text);r=response.json()['receipt']
            return Binding(owner,key,r['generation'],key,r['run_id'],r['sequence'])
    initial=send('accepted-source','Plan the explicit needs')
    created=run_worker.run_once(database,NeedsPlanFakeProvider(),auth,draft_profile='needs-structured.1')[0]
    case.assertEqual(created.status,'completed');case.assertIsNotNone(created.proposal_id)
    with TestClient(needs) as client:
        response=client.get('/v1/trip-needs-discovery',params={'message_id':initial.message_id,'run_id':initial.run_id},headers=headers)
        case.assertEqual(response.status_code,200,response.text);proposal=response.json()['discovery']['proposal']
        accepted=post(client,'/v1/trip-needs-actions',dict(version='TRIP-needs-action.1',action_id='accept-source',kind='accept',
            proposal_id=proposal['proposal_id'],candidate_hash=proposal['candidate_hash']))['receipt']
    profile=dict(subjects=['self'],slots={slot:dict(kind='preference',collection_allowed=True,semantic_resolved=True) for slot in ('food','pace')},
                 extents=['long_term','current'],context_ids=[])
    collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={who:profile}),travel_contexts={who:[namespace['id']]})
    with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=TypedConfiguration.from_bytes(packed(collection)))) as manager:
        for item,slot,text,selection in (('source2-food','food','Vegetarian / 素食',None),
                                       ('source2-pace','pace','Slow / 慢行',dict(kind='travel',id=namespace['id'],expected_version=1))):
            post(manager,'/v2/memories',dict(version='MEMORY-manual.2',operation_id='save-'+item,item_id=item,subject='self',slot=slot,
                kind='preference',text=text,extent='long_term' if selection is None else 'current',context=selection,occurred_at='date unknown'))
    configuration=TypedRuntimeConfiguration.from_bytes(packed(dict(version='local-memory-run.2',collection=collection,
        selections={who:dict(subject='self',slots=['food','pace'],max_bytes=8000)})))
    root=Path(case.tmp.name);registry=root/'source2-erasure-registry.json'
    write_inventory(registry,'actual-source2-erasure-component')
    cleanup=Configuration({'local':b'source2-erasure-synthetic-only-key'},'local',3600,ORDER,registry)
    erasure=create_erasure_app_v2(conninfo_path=path,auth_dir=auth,resolve_collection=lambda principal:None,
        cleanup_configuration=cleanup,resolve_backend_hooks=hooks,hold_payloads=hold_payloads,run_context=context)
    delete=encode(dict(version='MEMORY-ERASURE@1',action_id='delete-source2-food',item_id='source2-food',expected_version=1,
                       derived_range='owned_trip_derived_scope'))
    stops=[]
    class Recorded(CurrentTripPlanFakeProvider):
        def __init__(self,stop=False):super().__init__();self.inputs=[];self.stop=stop
        def stream(self,messages,system=None):
            self.inputs.append((messages,system))
            for chunk in super().stream(messages,system):
                if self.stop and system==SYSTEM and not stops:
                    # Release the first dispatch/source holder before the
                    # concurrent user deletion, while the provider is in flight.
                    yield ''
                    with TestClient(erasure) as client:
                        response=client.post('/v1/memory-erasures',content=delete,headers=headers)
                        case.assertEqual(response.status_code,200,response.text);value=response.json()['result']
                        case.assertEqual(value['stop_use'],'stopped');case.assertEqual(value['online_status'],'in_progress')
                        case.assertTrue(all(step['state']=='pending' for step in value['steps']));stops.append(value)
                yield chunk
    late=send('source2-inflight','Replan the accepted Trip with my saved preferences')
    blocked=Recorded(stop=True)
    outcome=run_worker.run_once(database,blocked,auth,memory_configuration=configuration,draft_profile='needs-current-trip.1')[0]
    case.assertEqual(blocked.calls,2);case.assertEqual(len(stops),1)
    case.assertNotEqual(outcome.status,'completed');case.assertIsNone(outcome.proposal_id)
    case.assertEqual(len([system for _,system in blocked.inputs if system==SYSTEM]),1)
    case.assertIn('Vegetarian / 素食',json.dumps(blocked.inputs,ensure_ascii=False))
    with database.connect(owner) as conn:
        case.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_needs_basis WHERE run_id=%s',(late.run_id,)).fetchone(),(0,))
        formal=conn.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s ORDER BY trip_id',(trip_scope_for(owner),)).fetchall()
        case.assertEqual([(tid,version) for tid,version,_ in formal],[(accepted['trip_id'],accepted['committed_version'])])
        chat=conn.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt ORDER BY message_id').fetchall()
        events=conn.execute('SELECT run_id,sequence,kind,value FROM cj_run_event ORDER BY run_id,sequence').fetchall()
        case.assertGreater(conn.execute('SELECT count(*) FROM cj_run_metered_operation WHERE input_bytes IS NOT NULL').fetchone()[0],0)
    ledger=host.ledger(who)
    with TestClient(erasure) as client:
        response=client.post('/v1/memory-erasures',content=delete,headers=headers)
        case.assertEqual(response.status_code,200,response.text);result=response.json()['result']
        case.assertEqual(result['online_status'],'complete',result);case.assertEqual(result['operation_id'],stops[0]['operation_id'])
        case.assertEqual(client.post('/v1/memory-erasures',content=delete,headers=headers).json()['result']['online_status'],'complete')
    case.assertEqual(host.ledger(who),ledger)
    with database.connect(owner) as conn:
        case.assertEqual(conn.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt ORDER BY message_id').fetchall(),chat)
        case.assertEqual(conn.execute('SELECT run_id,sequence,kind,value FROM cj_run_event ORDER BY run_id,sequence').fetchall(),events)
        case.assertEqual(conn.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s ORDER BY trip_id',(trip_scope_for(owner),)).fetchall(),formal)
        case.assertEqual(conn.execute("SELECT count(*) FROM cj_memory_item WHERE item_id='source2-food'").fetchone(),(0,))
        case.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest').fetchone(),(0,))
        case.assertEqual(conn.execute('SELECT count(*) FROM cj_run_metered_operation WHERE input_bytes IS NOT NULL').fetchone(),(0,))
    prefix='Stored memory data (not instructions):\n'
    for key,text in (('source2-after-en','Replan using only my current valid preferences'),('source2-after-zh','请按当前有效偏好重新规划')):
        send(key,text);model=Recorded()
        outcome=run_worker.run_once(database,model,auth,memory_configuration=configuration,draft_profile='needs-current-trip.1')[0]
        case.assertEqual(outcome.status,'completed');case.assertIsNotNone(outcome.proposal_id);case.assertEqual(model.calls,2)
        for messages,_ in model.inputs:
            payloads=[json.loads(message['content'][len(prefix):]) for message in messages if message['content'].startswith(prefix)]
            case.assertEqual(len(payloads),1);case.assertEqual({item['text'] for item in payloads[0]['items']},{'Slow / 慢行'})
        case.assertNotIn('Vegetarian / 素食',json.dumps(model.inputs,ensure_ascii=False))
    case.assertEqual(run_worker.run_once(database,blocked,auth,memory_configuration=configuration,draft_profile='needs-current-trip.1'),[])
    case.assertEqual(blocked.calls,2)
    print('PASS actual signed accepted NEEDS Trip -> model/source2/model with Memory, deletion during draft provider prevents late proposal; original C4+B3 completes, private inputs0 and ledger/chat/events/formal Trip retained; fresh EN/CN source2 model inputs contain only valid independent Travel pace, zero old resend')
