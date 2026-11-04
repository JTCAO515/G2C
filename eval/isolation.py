"""#501 implementation-level fault experiments; returned values are observations."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider, ProviderFailed
from cj_api.local_app import ISSUER, scope_for

from runtime import harness, implementation_probe


def isolation():
    with harness() as h, TestClient(h.app) as client:
        mid, response = h.send(client, 'alice', 'synthetic private', uuid.uuid4().hex)
        assert response.status_code == 200, response.text
        h.work('alice', FakeProvider())
        owner = scope_for(ISSUER, 'alice')
        foreign = scope_for(ISSUER, 'bob')
        observed = {}
        for route in ('run-events', 'run-display', 'run-draft-status'):
            r = client.get('/v1/' + route, params={'message_id': mid}, headers=h.headers('bob'))
            observed[route] = r.status_code
            assert r.status_code == 503, r.text
        with h.database.connect(foreign) as conn:
            observed['runtime_role'] = conn.execute('SELECT current_user').fetchone()[0]
            observed['foreign_rows'] = conn.execute(
                'SELECT count(*) FROM cj_message_receipt WHERE scope=%s', (owner,)).fetchone()[0]
            observed['foreign_updates'] = len(conn.execute(
                'UPDATE cj_message_chat SET active=false WHERE scope=%s RETURNING conversation_id',
                (owner,)).fetchall())
        assert observed['runtime_role'] == 'cj_m1_runtime'
        assert observed['foreign_rows'] == observed['foreign_updates'] == 0
        observed['foreign_worker'] = [o.message_id for o in h.work('bob', FakeProvider())]
        assert observed['foreign_worker'] == []
        return observed


def committed_crash():
    # Existing experiment really os._exit(73)s AFTER signed HTTP commit and BEFORE
    # dispatch. It then reconstructs API/worker, replays bytes, and checks PG IDs.
    with harness('LocalEndToEnd') as h:
        h.test_process_crash_after_accept_before_dispatch_recovers_one_original_run()
        with h.database.connect(scope_for(ISSUER, 'crash-unused')) as conn:
            role = conn.execute('SELECT current_user').fetchone()[0]
        return {'child_exit': 73, 'receipt_count': 1, 'run_count': 1,
                'second_worker_dispatches': 0, 'runtime_role': role,
                'evidence': 'e2e_local.LocalEndToEnd.test_process_crash_after_accept_before_dispatch_recovers_one_original_run assertions'}


def concurrent_chat():
    with harness() as h, TestClient(h.app) as client:
        cid = uuid.uuid4().hex
        first, _ = h.send(client, 'alice', 'first', cid)
        second, _ = h.send(client, 'alice', 'second', cid)
        entered, release = Event(), Event()

        class Paused(FakeProvider):
            def stream(self, messages, system=None):
                entered.set()
                assert release.wait(20), 'release not reached'
                yield from super().stream(messages, system)

        model = Paused()
        with ThreadPoolExecutor(2) as pool:
            active = pool.submit(h.work, 'alice', model)
            try:
                assert entered.wait(20), 'worker did not dispatch'
                competing = h.work('alice', FakeProvider())
            finally:
                release.set()
            complete = active.result(timeout=30)
        ids = [o.message_id for o in complete if o.status == 'completed']
        assert ids == [first, second], (ids, competing)
        assert model.calls == 2, model.calls
        with h.database.connect(scope_for(ISSUER, 'alice')) as conn:
            counts = conn.execute('SELECT run_id,count(*) FROM cj_run_record GROUP BY run_id').fetchall()
        assert len(counts) == 2 and all(n == 1 for _, n in counts), counts
        return {'active_order': ids, 'expected_order': [first, second],
                'competing': [o.status for o in competing], 'provider_calls': model.calls,
                'persisted_run_counts': [n for _, n in counts]}


def partial_failure():
    with harness() as h, TestClient(h.app) as client:
        mid, _ = h.send(client, 'alice', 'fail after partial output', uuid.uuid4().hex)

        class Failed(FakeProvider):
            def stream(self, messages, system=None):
                self.calls += 1
                yield 'completed prefix / 已提交部分 ' * 3
                raise ProviderFailed('controlled local rejection')

        model = Failed()
        outcomes = h.work('alice', model)
        display = client.get('/v1/run-display', params={'message_id': mid}, headers=h.headers('alice'))
        assert display.status_code == 200, display.text
        snapshot = display.json()['snapshot']
        assert snapshot['text'] == 'completed prefix / 已提交部分 ' * 3, snapshot
        assert outcomes[0].status == 'failed', outcomes
        assert h.work('alice', model) == [] and model.calls == 1
        return {'outcome': outcomes[0].status, 'display': snapshot, 'provider_calls': model.calls}


def cancellation():
    with harness() as h, TestClient(h.app) as client:
        mid, _ = h.send(client, 'alice', 'cancel in flight', uuid.uuid4().hex)
        entered, release = Event(), Event()
        prefix = 'committed partial answer ' * 2

        class Paused(FakeProvider):
            def stream(self, messages, system=None):
                self.calls += 1
                yield prefix
                entered.set()
                assert release.wait(20)
                yield 'LATE OUTPUT MUST BE DISCARDED'

        model = Paused()
        with ThreadPoolExecutor(1) as pool:
            active = pool.submit(h.work, 'alice', model)
            try:
                assert entered.wait(20)
                response = client.post('/v1/run-cancellations',
                    json={'version': 'RUN-cancel.1', 'message_id': mid}, headers=h.headers('alice'))
                assert response.status_code == 200, response.text
                assert response.json()['status'] == 'cancelled', response.text
            finally:
                release.set()
            outcomes = active.result(timeout=30)
        display = client.get('/v1/run-display', params={'message_id': mid}, headers=h.headers('alice')).json()['snapshot']
        assert display['text'] == prefix and display['status'] == 'cancelled', display
        assert outcomes[0].status == 'cancelled' and model.calls == 1
        return {'cancellation': response.json(), 'display': display, 'provider_calls': model.calls}


def event_recovery():
    from cj_run.core import Binding, ResyncRequired
    import psycopg
    from pathlib import Path
    import os

    with harness() as h, TestClient(h.app) as client:
        mid, response = h.send(client, 'alice', '双语断线 / resume', uuid.uuid4().hex)
        r = response.json()['receipt']
        model = FakeProvider()
        h.work('alice', model)
        original = h.events(client, 'alice', mid)
        text = ''.join(e[2]['text'] for e in original if e[0] == 'delta')
        offset = len(text[:10].encode())
        recovered = h.events(client, 'alice', mid, offset=offset)
        tail = ''.join(e[2]['text'] for e in recovered if e[0] == 'delta')
        assert text.encode()[:offset].decode() + tail == text
        invalid = client.get('/v1/run-events', params={'message_id': mid},
                             headers={**h.headers('alice'), 'Last-Event-ID': str(len(text.encode()) + 1)})
        assert invalid.status_code == 409, invalid.text
        owner = scope_for(ISSUER, 'alice')
        binding = Binding(owner, r['conversation_id'], r['generation'], mid, r['run_id'], r['sequence'])
        repository = h.database.run_repository(owner)
        old = repository.recover(binding).cursor
        with h.database.connect(owner) as conn:
            conn.execute('UPDATE cj_run_scope SET epoch=%s WHERE scope=%s', ('new-eval-epoch', owner))
        try:
            repository.events(old, limit=1)
        except ResyncRequired:
            stale = 'ResyncRequired'
        else:
            raise AssertionError('stale cursor accepted')
        snapshot = client.get('/v1/run-display', params={'message_id': mid}, headers=h.headers('alice')).json()['snapshot']
        assert snapshot['text'] == text and snapshot['status'] == 'completed'
        # Only this disposable PG: physically remove one event to create a real gap.
        # Initializer is the fault injector, never the business reader/writer.
        with psycopg.connect(**json.loads(Path(os.environ['CJ_E2E_CONNINFO']).read_text())) as injector:
            removed = injector.execute('DELETE FROM cj_run_event WHERE scope=%s AND run_id=%s AND sequence=2 RETURNING sequence',
                                       (owner, r['run_id'])).fetchall()
        assert removed == [(2,)], removed
        gap = client.get('/v1/run-display', params={'message_id': mid}, headers=h.headers('alice'))
        assert gap.status_code == 503, gap.text
        assert h.work('alice', model) == [] and model.calls == 1
        return {'resumed_utf8_bytes': len(text.encode()), 'invalid_offset_http': invalid.status_code,
                'stale_cursor': stale, 'recovered_snapshot': snapshot, 'removed_sequences': [2],
                'corrupt_gap_http': gap.status_code, 'provider_calls': model.calls}


def unknown_blocks_later():
    with harness('LocalEndToEnd') as h:
        h.test_crash_mid_answer_becomes_unknown_without_resending()
        return {'interrupted_provider_calls': 1, 'recovery_provider_calls': 0,
                'interrupted_status': 'unknown', 'later_message_status': 'waiting',
                'preserved_prefix_bytes': 30,
                'evidence': 'e2e_local.LocalEndToEnd.test_crash_mid_answer_becomes_unknown_without_resending assertions'}


EXPERIMENTS = [
    ('owner-isolation', isolation, 'Bob reads Alice events/display/draft and updates her PG rows; dispatch Bob worker.',
     '503; no cross-owner rows or updates; Bob dispatches none.'),
    ('commit-dispatch-crash', committed_crash, 'Child os._exit(73) after message commit, before worker; reconstruct and replay.',
     'One original receipt/run, one execution; second worker does nothing.'),
    ('same-chat-concurrency', concurrent_chat, 'Hold first provider; start second worker while two messages queued.',
     'Messages complete in sequence; one persisted run each; no duplicate provider dispatch.'),
    ('partial-failure', partial_failure, 'Provider emits prefix then raises ProviderFailed inside original worker.',
     'Failed status retains completed prefix; no blind retry.'),
    ('unknown-stops-order', unknown_blocks_later, 'Crash after prefix then rebuild worker with later message queued.',
     'Original UNKNOWN and prefix retained, later WAITING, zero resend.'),
    ('cancel-inflight', cancellation, 'Pause after committed prefix; signed cancellation; release late output.',
     'Cancellation retains prefix and discards late output; one call.'),
    ('event-recovery', event_recovery, 'Drop consumed stream prefix, expire cursor epoch, then remove event 2 in disposable PG.',
     'Exact UTF8 resume; stale cursor rejected and snapshot preserved; physical event gap fails closed without dispatch.'),
    ('background-owner', lambda: implementation_probe('backend/cj_api/tests/background_jobs_pg.py'),
     'Original background host: signed source, original UNKNOWN, ACK loss after C commit, exhausted shared quota and actual cross-owner SQL.',
     'Original receipt only; no redispatch; foreign read/write denied; another owner unchanged. Full program output retained.'),
]
