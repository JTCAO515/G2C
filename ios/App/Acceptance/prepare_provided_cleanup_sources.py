"""Genuine C-domain input for #450/#27's all-provided account cleanup case.

All business data comes from signed public APIs and the original worker/Fake.
This helper never publishes a synthetic Proposal or inserts business rows.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid


def project_registry(document, inventory, version):
    """Keep exact actual leaf definitions and the separate real control catalog."""
    selected_targets = frozenset(inventory)

    def select(node, parent=''):
        target = parent + node['id']
        children = node.get('objects', [])
        nested = [child for child in children if isinstance(child, dict)]
        if nested:
            assert len(nested) == len(children), 'mixed registry children'
            selected = [value for child in nested if (value := select(child, target + '/')) is not None]
            return dict(node, objects=selected) if selected else None
        return node if target in selected_targets or target.startswith('cleanup-control/') else None

    return dict(version=version, stores=[value for node in document['stores'] if (value := select(node)) is not None])


def seed_c_sources(connection, auth, context, subject, token, other_token):
    from fastapi.testclient import TestClient
    from cj_memory.typed_api import create_local_typed_app
    from cj_memory.typed_local import TypedConfiguration
    from prepare_memory_candidate_source import build_source_host, prepare_source

    def encode(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

    def expect(response):
        assert response.status_code == 200, ('signed public C source API status', response.status_code)
        return response.json()

    app, host, jobs, background, model, originals = build_source_host(
        connection, auth, context, [subject], lambda selected: token if selected == subject else other_token)
    proof = prepare_source(app, host, jobs, background, model, originals, auth, token, other_token)
    assert proof['read_wire'] == 'MEMORY-CANDIDATE-projection@2' and model.calls == 2
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/octet-stream'}
    with TestClient(app) as client:
        page = expect(client.get('/v6/memory-candidates', params={
            'conversation_id': proof['conversation'], 'after_candidate_id': ''}, headers=headers))['result']
        assert len(page['candidates']) == 1
        row = page['candidates'][0]
        assert row['candidate_id'] == proof['candidate_id'] and row['review'] == proof['producer']
        action = dict(version='MEMORY-CANDIDATE@1', action_id=str(uuid.uuid4()),
            job_id=row['review']['job_id'], attempt_id=row['review']['attempt_id'],
            candidate_id=row['candidate_id'], expected_candidate_version=row['version'],
            expected_memory_epoch=page['memory_epoch'], operation='confirm', kind='preference',
            text='我明确确认偏好轻松节奏', extent='long_term', context=None, occurred_at='时间不详')
        expect(client.post('/v3/memory-candidate-actions', content=encode(action), headers=headers))

    configuration = TypedConfiguration.from_bytes(encode(configuration_document([subject])))
    typed = create_local_typed_app(conninfo_path=connection, auth_dir=auth, configuration=configuration)
    manual_id = str(uuid.uuid4())
    with TestClient(typed) as client:
        expect(client.post('/v2/memories', content=encode(dict(version='MEMORY-manual.2',
            operation_id=str(uuid.uuid4()), item_id=manual_id, subject='self', slot='budget',
            kind='preference', text='我明确保存预算偏好', extent='long_term', context=None,
            occurred_at='时间不详')), headers=headers))
        original = expect(client.get('/v2/memory-items', params={'item_id': manual_id}, headers=headers))['item']
        assert original is not None and original['status'] == 'active'
        expect(client.post('/v2/memory-management-actions', content=encode(dict(
            version='MEMORY-management.2', action_id=str(uuid.uuid4()), operation='edit',
            item_id=manual_id, expected_version=original['version'],
            expected_source_version=original['command']['source_version'], context=None,
            text='我明确修改保存的预算偏好')), headers=headers))
        hashes = {}
        for item_id in (manual_id, proof['candidate_id']):
            item = expect(client.get('/v2/memory-items', params={'item_id': item_id}, headers=headers))['item']
            assert item is not None and item['status'] == 'active'
            hashes[item_id] = hashlib.sha256(encode(item)).hexdigest()
    from cj_api.local_app import ISSUER, scope_for
    with host.database.connect(scope_for(ISSUER, subject)) as connection_cursor:
        assert connection_cursor.execute('SELECT current_user').fetchone() == ('cj_m1_runtime',)
    return dict(app=typed, proof=proof, item_hashes=hashes, model_calls=model.calls)


def configuration_document(subjects):
    profile = dict(subjects=['self'], slots={
        name: dict(kind='preference', collection_allowed=True, semantic_resolved=True)
        for name in ('pace', 'budget')}, extents=['long_term'], context_ids=[])
    return dict(version='local-memory-typed.1', collection=dict(version='local-memory-policy.1',
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        profiles={subject: profile for subject in subjects}), travel_contexts={subject: [] for subject in subjects})


def runtime_configuration(subjects):
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    # Existing live Memory must enter the worker through its actual typed
    # runtime authority. No deletion or empty-memory fallback is permitted.
    value = dict(version='local-memory-run.2', collection=configuration_document(subjects),
        selections={subject: dict(subject='self', slots=['pace', 'budget'], max_bytes=16384) for subject in subjects})
    return TypedRuntimeConfiguration.from_bytes(json.dumps(value).encode())


def verify_retained_source(source, token):
    from fastapi.testclient import TestClient
    headers = {'Authorization': 'Bearer ' + token}
    with TestClient(source['app']) as client:
        for item_id, expected in source['item_hashes'].items():
            response = client.get('/v2/memory-items', params={'item_id': item_id}, headers=headers)
            assert response.status_code == 200, ('retained other-owner C source', response.status_code)
            item = response.json()['item']
            raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
            assert hashlib.sha256(raw).hexdigest() == expected, 'other-owner C source changed'


# Independent audit inventory of current provided C stores. Queries run only
# inside the caller's actual original, eligible account cleanup transaction.
C_MEMORY_TABLES = ('cj_memory_scope', 'cj_memory_item', 'cj_memory_source', 'cj_memory_operation',
    'cj_memory_erasure_manifest', 'cj_memory_management_action', 'cj_memory_history_candidate_action',
    'cj_memory_history_origin', 'cj_memory_history_job', 'cj_memory_history_cursor',
    'cj_memory_history_action', 'cj_memory_history_consent')
C_TRIP_TABLES = ('cj_trip_scoped_action', 'cj_trip_scoped_result', 'cj_trip_scoped_basis',
    'cj_trip_needs_edit', 'cj_trip_needs_plan_context', 'cj_trip_needs_current', 'cj_trip_needs_action',
    'cj_trip_needs_basis', 'cj_trip_manual_intent', 'cj_trip_manual_basis',
    'cj_trip_receipt', 'cj_trip_record', 'cj_trip_proposal', 'cj_trip_scope')


def audit_c_copies(cursor, owner_scope):
    from cj_agent.draft import trip_scope_for
    result = {}
    for scope, tables in ((owner_scope, C_MEMORY_TABLES), (trip_scope_for(owner_scope), C_TRIP_TABLES)):
        cursor.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)", (scope,))
        for table in tables:
            cursor.execute('SELECT count(*) FROM ' + table + ' WHERE scope=%s', (scope,))
            result[table] = cursor.fetchone()[0]
    return result
