"""Scenario execution through signed API, restricted PG and original worker."""
import base64
from copy import deepcopy
from hashlib import sha256
from importlib import reload
import json
from pathlib import Path
import sys
import uuid
import time
import subprocess
from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_api.local_app import ISSUER, scope_for
from runtime import ROOT, harness


class ObservedProvider(FakeProvider):
    """Actual FakeProvider subclass, preserving the host's Fake-only guard."""
    def __init__(self):
        super().__init__()
        self.inputs = []

    def stream(self, messages, system=None):
        self.inputs.append(deepcopy(messages))
        yield from super().stream(messages, system=system)


def state(database, owner):
    foreign = scope_for(ISSUER, 'eval-foreign-' + uuid.uuid4().hex)
    with database.connect(foreign) as conn:
        reads = conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s', (owner,)).fetchone()[0]
        updates = conn.execute('UPDATE cj_message_chat SET active=false WHERE scope=%s RETURNING conversation_id', (owner,)).fetchall()
    with database.connect(owner) as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
        trips = conn.execute('SELECT version,content FROM cj_trip_record').fetchall()
        memory_count = conn.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0]
    return dict(runtime_role=role, foreign_message_rows=reads, foreign_mutations=len(updates),
                memory_item_count=memory_count, formal_trip_count=len(trips), formal_trip_version=trips[0][0] if len(trips)==1 else None,
                formal_content_sha256=sha256(bytes(trips[0][1])).hexdigest() if len(trips)==1 else None)


def travel_case(scenario, language):
    with harness('SignedTripConfirmation') as h, TestClient(h.app) as client:
        actor = 'eval-' + uuid.uuid4().hex
        path = h.auth / 'invited.json'
        path.write_text(json.dumps([*json.loads(path.read_text()), actor]))
        intent = 'consider_trip' if scenario['recipe'] in ('preview','accept','reject') else 'none'
        model = ObservedProvider()
        started=time.monotonic()
        mid, response = h.send(client, actor, scenario['inputs'][language], uuid.uuid4().hex, intent=intent)
        assert response.status_code == 200, response.text
        outcomes = h.work(actor, model)
        current = next(o for o in outcomes if o.message_id == mid)
        assert current.status == 'completed', current
        observed = dict(message_receipt=response.json()['receipt'], provider_inputs=model.inputs,
                        model_calls=model.calls, run_status=current.status)
        if intent == 'consider_trip':
            response = client.get('/v1/trip-proposals', params={'proposal_id': current.proposal_id}, headers=h.headers(actor))
            assert response.status_code == 200, response.text
            candidate = response.json()['proposal']
            observed['candidate_document'] = candidate['document']
            observed['candidate_content_sha256'] = sha256(base64.b64decode(candidate['content_utf8_base64'])).hexdigest()
            if scenario['recipe'] in ('accept', 'reject'):
                confirmation = h.prepare(client, candidate, scenario['recipe'], subject=actor)
                assert confirmation.status_code == 200, confirmation.text
                raw = base64.b64decode(confirmation.json()['action_utf8_base64'])
                response = h.post_action(client, raw, subject=actor)
                assert response.status_code == 200, response.text
                observed['action_receipt'] = response.json()['receipt']
        observed.update(state(h.database, scope_for(ISSUER, actor)))
        observed['api_task_seconds']=time.monotonic()-started
        return observed, {}


from contextlib import contextmanager


@contextmanager
def case_session():
    import e2e_local
    reload(e2e_local)
    sys.path.insert(0, str(ROOT / 'backend/memory/tests'))
    import typed_pg
    reload(typed_pg)
    cls = typed_pg.TypedStorageChecks
    cls.setUpClass()
    try:
        yield cls
    finally:
        cls.tearDownClass()


def memory_case(scenario, language, fixture):
    import run_worker
    h = fixture()
    try:
        h.setUp()
        model = ObservedProvider()
        _, document = h.runtime_configuration()
        kind = scenario.get('memory_kind', 'preference')
        for profile in document['collection']['collection']['profiles'].values():
            profile['slots']['pace-'+h.tag]['kind'] = kind
        from cj_memory.typed_runtime import TypedRuntimeConfiguration
        from cj_memory.typed_local import TypedConfiguration
        from cj_memory.typed_api import create_local_typed_app
        import e2e_local
        configuration = TypedRuntimeConfiguration.from_bytes(json.dumps(document).encode())
        memory_app = create_local_typed_app(conninfo_path=e2e_local.CONNINFO,auth_dir=h.auth,
            configuration=TypedConfiguration.from_bytes(json.dumps(document['collection']).encode()))
        memory = scenario['memory_' + language]
        cid = 'eval-memory-' + h.tag
        recipe = scenario['recipe']
        with TestClient(memory_app) as api, TestClient(h.app) as client:
            started=time.monotonic()
            before, _ = h.send_v2(client, cid, None, text='合成基线' if language=='zh' else 'Synthetic baseline')
            run_worker.run_once(h.database, model, h.auth, memory_configuration=configuration)
            command = json.loads(h.raw(text=memory))
            command['kind'] = kind
            body = json.dumps(command,ensure_ascii=False).encode()
            saved = api.post('/v2/memories', content=body, headers={**h.headers('alice'),'Content-Type':'application/octet-stream'})
            assert saved.status_code == 200, saved.text
            iid = saved.json()['receipt']['item_id']
            status = 'active'
            expected_text = memory
            headers = {**h.headers('alice'), 'Content-Type':'application/octet-stream'}
            if recipe in ('memory-edit','memory-pause'):
                command = dict(version='MEMORY-management.2',action_id='eval-'+h.tag,
                               operation='edit' if recipe=='memory-edit' else 'pause', item_id=iid,
                               expected_version=1,expected_source_version=1)
                if recipe=='memory-edit':
                    expected_text = '我喜欢紧凑安排' if language=='zh' else 'I prefer a packed schedule'
                    command.update(text=expected_text,context=None)
                else:
                    status = 'disabled'
                changed = api.post('/v2/memory-management-actions',content=json.dumps(command,ensure_ascii=False).encode(),headers=headers)
                assert changed.status_code==200, changed.text
            if recipe=='memory-stop':
                item = api.get('/v2/memory-items',params={'item_id':iid},headers=h.headers('alice')).json()['item']
                command = dict(version='MEMORY-STOP-USE@2',action_id='eval-stop-'+h.tag,operation='withdraw',
                               item_id=iid,expected_version=1,source_id=item['command']['source_id'],expected_source_version=1)
                stopped=api.post('/v2/memory-withdrawal-actions',content=json.dumps(command).encode(),headers=headers)
                assert stopped.status_code==200, stopped.text
                status='withdrawn'
            if recipe in ('memory-new-chat','memory-restart'):
                cid='new-'+cid
            selected = h.travel[1] if recipe=='memory-other-travel' else None
            mid, receipt = h.send_v2(client,cid,selected,text=scenario['inputs'][language])
            if recipe=='memory-restart':
                import e2e_local
                path=h.auth/'evaluation-memory.json'
                path.write_text(json.dumps(document));path.chmod(0o600)
                child=subprocess.run([sys.executable,'-B',str(ROOT/'eval/worker_probe.py'),
                    e2e_local.CONNINFO,str(h.auth),str(h.run_path),str(path)],
                    text=True,capture_output=True,timeout=60)
                assert child.returncode==0,child.stderr
                result=json.loads(child.stdout)
                current=next(o for o in result['outcomes'] if o['message_id']==mid)
                assert current['status']=='completed',current
                model.calls+=result['model_calls'];model.inputs.extend(result['provider_inputs'])
                run_status=current['status']
            else:
                results=run_worker.run_once(h.database,model,h.auth,memory_configuration=configuration)
                current=next(o for o in results if o.message_id==mid)
                assert current.status=='completed',current
                run_status=current.status
            current_item=api.get('/v2/memory-items',params={'item_id':iid},headers=h.headers('alice'))
            assert current_item.status_code==200,current_item.text
            item=current_item.json()['item']
            observed=dict(message_receipt=receipt['receipt'],provider_inputs=model.inputs,
                          model_calls=model.calls,run_status=run_status,
                          memory_status=item['status'],memory_text=item['command']['text'],memory_kind=item['command']['kind'])
            observed.update(state(h.database,h.scope))
            with h.database.connect(h.scope) as conn:
                observed['memory_item_count']=conn.execute('SELECT count(*) FROM cj_memory_item WHERE item_id=%s',(iid,)).fetchone()[0]
            observed['api_task_seconds']=time.monotonic()-started
            expected=dict(memory_kind=kind, memory_item_count=1, memory_texts=[] if status in ('disabled','withdrawn') else [expected_text],
                          memory_status=status,memory_text=expected_text)
            return observed,expected
    finally:
        h.tearDown()


def run_case(scenario, language, fixture):
    # Real hosts provide their actual observations to judge/report; this runner
    # remains Fake-only and does not disguise another provider as FakeProvider.
    if scenario['recipe'].startswith('memory-'):
        return memory_case(scenario,language,fixture)
    return travel_case(scenario,language)
