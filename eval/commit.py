"""#502 signed original receipts and concurrent sole Trip writer experiments."""
import base64
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json
import sys
from importlib import reload

from fastapi.testclient import TestClient
from runtime import ROOT, harness


def concurrent_accept():
    with harness('SignedTripConfirmation') as h, TestClient(h.app) as client:
        _, outcome = h.draft(client, 'alice', '北京三日 / synthetic')
        proposal = client.get('/v1/trip-proposals', params={'proposal_id': outcome.proposal_id},
                              headers=h.headers('alice')).json()['proposal']
        raw = base64.b64decode(h.prepare(client, proposal).json()['action_utf8_base64'])
        barrier = Barrier(2)

        def submit():
            with TestClient(h.app) as contender:
                barrier.wait(timeout=20)
                response = h.post_action(contender, raw)
                return response.status_code, response.json()

        with ThreadPoolExecutor(2) as pool:
            left, right = pool.submit(submit), pool.submit(submit)
            results = [left.result(timeout=30), right.result(timeout=30)]
        assert [r[0] for r in results] == [200, 200], results
        assert results[0][1]['receipt'] == results[1][1]['receipt'], results
        trip = client.get('/v1/trip-details', params={'trip_id': proposal['trip_id']},
                          headers=h.headers('alice')).json()['trip']
        assert trip['version'] == 1, trip
        assert h.prepare(client, proposal).status_code == 409
        return {'concurrent_http': [r[0] for r in results],
                'original_receipt': results[0][1]['receipt'], 'formal_version': trip['version'],
                'second_action_http': 409}


def duplicate_message():
    import uuid
    from cj_agent.provider import FakeProvider
    from cj_api.local_app import ISSUER, scope_for

    with harness() as h, TestClient(h.app) as client:
        cid = uuid.uuid4().hex
        head = client.put('/v1/conversations', params={'conversation_id': cid}, headers=h.headers('alice')).json()
        raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id=cid, message_id='same-message',
                              text='synthetic repeated delivery', trip_id=None, creation_intent='none',
                              expected_generation=head['generation'], expected_sequence=0)).encode()
        headers = {**h.headers('alice'), 'Content-Type': 'application/octet-stream'}
        barrier = Barrier(2)

        def post():
            with TestClient(h.app) as other:
                barrier.wait(timeout=20)
                r = other.post('/v1/messages', content=raw, headers=headers)
                return r.status_code, r.json()

        with ThreadPoolExecutor(2) as pool:
            a, b = pool.submit(post), pool.submit(post)
            results = [a.result(timeout=30), b.result(timeout=30)]
        assert [r[0] for r in results] == [200, 200], results
        assert results[0][1]['receipt'] == results[1][1]['receipt'], results
        model = FakeProvider()
        h.work('alice', model)
        h.work('alice', model)
        with h.database.connect(scope_for(ISSUER, 'alice')) as conn:
            receipts = conn.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0]
            runs = conn.execute('SELECT count(*) FROM cj_run_record').fetchone()[0]
        assert receipts == runs == model.calls == 1, (receipts, runs, model.calls)
        return dict(http=[r[0] for r in results], original_receipt=results[0][1]['receipt'],
                    persisted_receipts=receipts, persisted_runs=runs, provider_calls=model.calls)


def manual(mode):
    import e2e_local
    reload(e2e_local)
    sys.path.insert(0, str(ROOT / 'backend/trip/tests'))
    import manual_pg
    reload(manual_pg)
    cls = manual_pg.ManualChecks
    cls.setUpClass()
    h = cls()
    try:
        h.setUp()
        if mode == 'lost-ack':
            h.test_ack_unknown_reconciles_original_and_rollback_retains_trip()
            return {'rollback_receipt': None, 'rollback_version': h.base_version,
                    'lost_ack_http': 503, 'recovery': 'reconcile_original',
                    'committed_version': h.repository.detail(h.trip_id).version,
                    'asserted_by': 'manual_pg.ManualChecks.test_ack_unknown_reconciles_original_and_rollback_retains_trip'}
        with TestClient(h.app) as client:
            first = h.prepare(client)
            edit = json.loads(h.edit)
            edit.update(request_id='second-' + h.tag, title='second candidate')
            second = h.write(client, '/v1/trip-manual-preparations', manual_pg.packed(edit)).json()['preparation']
            raw1 = h.save(first)
            raw2 = json.loads(h.save(second))
            raw2['action_id'] = 'second-save-' + h.tag
            barrier = Barrier(2)

            def save(raw):
                with TestClient(h.app) as c:
                    barrier.wait(timeout=20)
                    r = h.write(c, '/v1/trip-manual-saves', raw)
                    return r.status_code, r.json()

            with ThreadPoolExecutor(2) as pool:
                a, b = pool.submit(save, raw1), pool.submit(save, manual_pg.packed(raw2))
                results = [a.result(timeout=30), b.result(timeout=30)]
            assert sorted(r[0] for r in results) == [200, 409], results
            current = h.repository.detail(h.trip_id)
            assert current.version == h.base_version + 1
            losing = 'save-' + h.tag if results[0][0] == 409 else raw2['action_id']
            assert h.repository.query_action(losing) is None
            return dict(http=[r[0] for r in results], base_version=h.base_version,
                        final_version=current.version, losing_action_receipt=None)
    finally:
        cls.tearDownClass()


EXPERIMENTS = [
    ('duplicate-message', duplicate_message, 'Two concurrent signed POSTs with identical original message bytes.',
     'Same original receipt; one persisted message/run and one provider call.'),
    ('concurrent-accept', concurrent_accept, 'Two concurrent signed accepts with identical confirmation bytes; then new action on same candidate.',
     'Same original receipt, Trip version1; new action409.'),
    ('concurrent-formal-version', lambda: manual('concurrent'), 'Two distinct prepared candidates race saves from the same formal version.',
     'One200/one409, version advances once, losing action has no receipt.'),
    ('physical-ack-loss', lambda: manual('lost-ack'), 'Raise before actual INSERT (rollback), then after actual PG commit (lost ACK).',
     '503 reconcile_original; rollback absent/unchanged, actual committed original is recovered once.'),
]
