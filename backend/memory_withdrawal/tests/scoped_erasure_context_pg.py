"""Signed scoped-run deletion race with the actual C4/B3 physical composition."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from cj_api.local_cleanup import Configuration
from cj_cleanup.core import encode
from cj_cleanup.memory_payloads import hooks,hold_payloads
from cj_memory_withdrawal.erasure_app import create_erasure_app_v2
from cj_memory_withdrawal.erasure_service import ORDER
from cj_agent.draft import trip_scope_for
from memory_test_inventory import write_inventory


def exercise(case):
    from edit_support import CONNINFO
    from scoped_result_body_pg import Model
    f=case.fixture('signed-scoped-erasure',legacy=False)
    def model_memory(model):
        prefix='Stored memory data (not instructions):\n'
        payloads=[message['content'][len(prefix):] for message in model.inputs[0] if message['content'].startswith(prefix)]
        case.assertEqual(len(payloads),1)
        return json.loads(payloads[0])
    trip_scope=trip_scope_for(f.scope)
    clarification,_,_=case.send_result(f,key='old-clarification',clarify=True)
    no_model=Model();f.run(no_model);case.assertEqual(no_model.calls,0)
    pointer=case.pointer(f,clarification)
    case.assertEqual(case.get(f,pointer['result_id']).status_code,200)
    pending,_,_=case.send_result(f,key='old-proposal')
    previous=Model();outcome=f.run(previous)[0]
    case.assertEqual(outcome.status,'completed');case.assertIsNotNone(outcome.proposal_id)
    case.assertEqual(previous.calls,1)
    before=model_memory(previous)
    case.assertEqual({item['text'] for item in before['items']},{'Vegetarian / 素食','Slow / 慢行'})
    with f.database.connect(f.scope) as conn:
        formal=conn.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s ORDER BY trip_id',(trip_scope,)).fetchall()
        accepted=conn.execute("SELECT proposal_id,content FROM cj_trip_proposal WHERE scope=%s AND status='accepted' ORDER BY proposal_id",(trip_scope,)).fetchall()
        case.assertTrue(accepted)
        source=conn.execute("SELECT source_id FROM cj_memory_item WHERE item_id='mem-long'").fetchone()[0]
        case.assertGreater(conn.execute('SELECT count(*) FROM cj_trip_scoped_result').fetchone()[0],0)
        case.assertGreater(conn.execute("SELECT count(*) FROM cj_trip_proposal WHERE status<>'accepted'").fetchone()[0],0)
    registry=Path(case.tmp.name)/'scoped-erasure-registry.json'
    write_inventory(registry,'actual-scoped-erasure-component')
    configuration=Configuration({'local':b'scoped-erasure-synthetic-only-key'},'local',3600,ORDER,registry)
    app=create_erasure_app_v2(conninfo_path=CONNINFO,auth_dir=f.auth,resolve_collection=lambda principal:None,
        cleanup_configuration=configuration,resolve_backend_hooks=hooks,hold_payloads=hold_payloads,run_context=f.context)
    raw=encode(dict(version='MEMORY-ERASURE@1',action_id='original-scoped-delete',item_id='mem-long',
                    expected_version=1,derived_range='owned_trip_derived_scope'))
    headers={**f.headers,'Content-Type':'application/octet-stream'}
    late,_,_=case.send_result(f,key='inflight-scoped')
    stops=[]
    def stop_during_provider():
        with TestClient(app) as client:
            response=client.post('/v1/memory-erasures',content=raw,headers=headers)
            case.assertEqual(response.status_code,200,response.text);value=response.json()['result']
            case.assertEqual(value['stop_use'],'stopped')
            case.assertEqual(value['online_status'],'in_progress')
            case.assertTrue(all(step['state']=='pending' for step in value['steps']))
            stops.append(value)
    blocked=Model();blocked.hook=stop_during_provider
    outcome=f.run(blocked)[0]
    case.assertEqual(len(stops),1);case.assertEqual(blocked.calls,1)
    case.assertIn('Vegetarian / 素食',{item['text'] for item in model_memory(blocked)['items']})
    case.assertNotEqual(outcome.status,'completed');case.assertIsNone(outcome.proposal_id)
    state=f.database.run_repository(f.scope).recover(late).state
    case.assertEqual(state.effects,())
    ledger=f.host.ledger(f.subject)
    with f.database.connect(f.scope) as conn:
        chat=conn.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt ORDER BY message_id').fetchall()
        events=conn.execute('SELECT run_id,sequence,kind,value FROM cj_run_event ORDER BY run_id,sequence').fetchall()
        case.assertFalse(any(rid==late.run_id and kind in ('text_delta','completed') for rid,_,kind,_ in events))
        case.assertGreater(conn.execute('SELECT count(*) FROM cj_run_metered_operation WHERE input_bytes IS NOT NULL').fetchone()[0],0)
    with TestClient(app) as client:
        complete=client.post('/v1/memory-erasures',content=raw,headers=headers)
        case.assertEqual(complete.status_code,200,complete.text)
        result=complete.json()['result'];case.assertEqual(result['online_status'],'complete',result)
        case.assertEqual(result['operation_id'],stops[0]['operation_id'])
        case.assertEqual(client.post('/v1/memory-erasures',content=raw,headers=headers).json()['result']['online_status'],'complete')
        progress=client.get('/v1/memory-erasure-progress',params={'action_id':'original-scoped-delete'},headers=f.headers)
        case.assertEqual(progress.status_code,200,progress.text);case.assertEqual(progress.json()['result']['online_status'],'complete')
    case.assertEqual(f.host.ledger(f.subject),ledger)
    with f.database.connect(f.scope) as conn:
        case.assertEqual(conn.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt ORDER BY message_id').fetchall(),chat)
        case.assertEqual(conn.execute('SELECT run_id,sequence,kind,value FROM cj_run_event ORDER BY run_id,sequence').fetchall(),events)
        case.assertEqual(conn.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s ORDER BY trip_id',(trip_scope,)).fetchall(),formal)
        case.assertEqual(conn.execute("SELECT proposal_id,content FROM cj_trip_proposal WHERE scope=%s AND status='accepted' ORDER BY proposal_id",(trip_scope,)).fetchall(),accepted)
        case.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_scoped_result').fetchone(),(0,))
        case.assertEqual(conn.execute("SELECT count(*) FROM cj_trip_proposal WHERE status<>'accepted'").fetchone(),(0,))
        case.assertEqual(conn.execute("SELECT count(*) FROM cj_memory_item WHERE item_id='mem-long'").fetchone(),(0,))
        case.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_source WHERE source_id=%s',(source,)).fetchone(),(0,))
        case.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest').fetchone(),(0,))
        case.assertEqual(conn.execute('SELECT count(*) FROM cj_run_metered_operation WHERE input_bytes IS NOT NULL').fetchone(),(0,))
        case.assertEqual(conn.execute('SELECT item_id,status FROM cj_memory_item ORDER BY item_id').fetchall(),[('mem-other','active'),('mem-temp','active')])
    case.assertNotEqual(case.get(f,pointer['result_id']).status_code,200)
    for key in ('after-en','after-zh'):
        case.send_result(f,key=key)
        model=Model();outcomes=f.run(model)
        case.assertEqual([value.status for value in outcomes],['completed']);case.assertEqual(model.calls,1)
        data=model_memory(model)
        case.assertEqual({item['text'] for item in data['items']},{'Slow / 慢行'})
        case.assertNotIn('Vegetarian / 素食',json.dumps(model.inputs,ensure_ascii=False))
    case.assertEqual(f.run(blocked),[]);case.assertEqual(blocked.calls,1)
    print('PASS actual signed scoped run/Meter/Fake -> delete in provider -> all pending while busy, zero late effects -> same original API C4+B3 complete; old scoped result/draft/input copies0, raw chat/events/ledger/formal Trip retained; new model inputs omit erased food and keep independent Travel pace')
