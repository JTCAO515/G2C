"""Actual signed local cancellation/worker tests; disposable PG and FakeProvider only."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
from cj_message.domain import Service as MessageService
from cj_run.core import Binding, Conflict, Denied, Event, Service as RunService
from cj_agent.draft import DraftPublisher
from cj_agent.provider import FakeProvider
from e2e_local import Harness, CONNINFO, dev_auth


class CancellationChecks(Harness):
    def setUp(self):
        self.own = 'cancel-' + uuid.uuid4().hex
        self.other = 'other-' + uuid.uuid4().hex
        self.auth = Path(self.tmp.name) / self.own
        dev_auth('init', str(self.auth), '--invite', self.own, '--invite', self.other)
        with patch.dict('os.environ', {'CJ_ENV': 'local', 'CJ_LOCAL_CONNINFO': CONNINFO, 'CJ_LOCAL_AUTH_DIR': str(self.auth)}):
            self.app = app_from_environment()
        self.database = LocalDatabase(CONNINFO)
        self.scope = scope_for(ISSUER, self.own)

    def cancel(self, client, mid, subject=None):
        return client.post('/v1/run-cancellations', json={'version': 'RUN-cancel.1', 'message_id': mid},
                           headers=self.headers(subject or self.own))

    def services(self):
        messages = MessageService(self.database.message_repository(self.scope), lambda: None)
        runs = RunService(self.database.run_repository(self.scope), lambda b: messages.query(b.message_id) is not None)
        return messages, runs

    def binding(self, receipt):
        return Binding(self.scope, receipt['conversation_id'], receipt['generation'], receipt['message_id'],
                       receipt['run_id'], receipt['sequence'])

    def test_cancel_before_dispatch_replays_once_and_other_account_cannot_cancel(self):
        with TestClient(self.app) as client:
            mid, accepted = self.send(client, self.own, 'original', conversation=uuid.uuid4().hex)
            self.assertEqual(accepted.status_code, 200)
            binding = self.binding(accepted.json()['receipt'])
            with self.database.connect(self.scope) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_run_record').fetchone()[0], 0)
            missing = self.cancel(client, 'absent', self.other)
            foreign = self.cancel(client, mid, self.other)
            self.assertEqual((missing.status_code, foreign.status_code), (503, 503))
            self.assertEqual(missing.json()['error'], foreign.json()['error'])
            first = self.cancel(client, mid)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual((first.json()['status'], first.json()['event_highwater']), ('cancelled', 1))
            repeated = self.cancel(client, mid).json()
            self.assertEqual({k: v for k, v in repeated.items() if k != 'request_id'},
                             {k: v for k, v in first.json().items() if k != 'request_id'})
            provider = FakeProvider()
            self.assertEqual(self.work(self.own, provider)[0].status, 'cancelled')
            self.assertEqual(provider.calls, 0)
            self.assertEqual(self.events(client, self.own, mid)[-1][2], {'status': 'cancelled'})
            self.assertEqual(self.services()[1].snapshot(binding).sequence, 1)

    def test_cancel_while_answer_in_flight_discards_late_text_and_draft(self):
        paused, release = threading.Event(), threading.Event()
        class Provider:
            calls = 0
            closed = False
            def stream(self, messages, system=None):
                self.calls += 1
                try:
                    yield 'committed partial answer ' * 2
                    paused.set()
                    if not release.wait(10): raise AssertionError('test did not release in-flight call')
                    yield 'LATE_PRIVATE_OUTPUT'
                finally: self.closed = True
        provider = Provider()
        with TestClient(self.app) as client, ThreadPoolExecutor(1) as pool:
            mid, accepted = self.send(client, self.own, 'original', conversation=uuid.uuid4().hex, intent='consider_trip')
            binding = self.binding(accepted.json()['receipt'])
            work = pool.submit(self.work, self.own, provider)
            try:
                self.assertTrue(paused.wait(10))
                response = self.cancel(client, mid)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['status'], 'cancelled')
                other_mid, other_response = self.send(client, self.other, 'other account text', conversation=uuid.uuid4().hex)
                self.assertEqual(self.work(self.other, FakeProvider())[0].status, 'completed')
                r = other_response.json()['receipt']; other_scope = scope_for(ISSUER, self.other)
                other_binding = Binding(other_scope, r['conversation_id'], r['generation'], r['message_id'], r['run_id'], r['sequence'])
                other_runs = RunService(self.database.run_repository(other_scope), lambda _: True)
                other_state = other_runs.snapshot(other_binding)
            finally: release.set()
            self.assertEqual(work.result(timeout=10)[0].status, 'cancelled')
            self.assertEqual(provider.calls, 1); self.assertTrue(provider.closed)
            _, runs = self.services(); stopped = runs.snapshot(binding)
            self.assertEqual(stopped.text, 'committed partial answer ' * 2)
            self.assertEqual(stopped.effects, ())
            with self.assertRaises(Conflict): runs.apply(Event(binding, stopped.sequence + 1, 'late', 'text_delta', 'late'))
            self.assertEqual(runs.snapshot(binding), stopped)
            self.assertEqual(other_runs.snapshot(other_binding), other_state)
            self.assertIn('other account text', other_state.text)
            with self.assertRaises(Denied): other_runs.apply(Event(binding, stopped.sequence + 1, 'foreign-late', 'text_delta', 'late'))
            with self.database.connect(self.scope) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0], 0)
            foreign = client.get('/v1/run-display', params={'message_id': mid}, headers=self.headers(self.other))
            self.assertEqual(foreign.status_code, 503)
            self.assertNotIn('committed partial', foreign.text)

    def test_busy_first_step_reports_unknown_instead_of_false_cancellation(self):
        started, release = threading.Event(), threading.Event()
        class Provider:
            calls = 0
            def stream(self, messages, system=None):
                self.calls += 1; started.set()
                if not release.wait(15): raise AssertionError('test release missing')
                yield 'already-started request'
        provider = Provider()
        with TestClient(self.app) as client, ThreadPoolExecutor(1) as pool:
            mid, accepted = self.send(client, self.own, 'original', conversation=uuid.uuid4().hex)
            binding = self.binding(accepted.json()['receipt'])
            work = pool.submit(self.work, self.own, provider)
            try:
                self.assertTrue(started.wait(10))
                response = self.cancel(client, mid)  # existing five-second RUN lock timeout
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()['error']['outcome'], 'unknown')
                self.assertNotIn('status', response.json())
            finally: release.set()
            self.assertEqual(work.result(timeout=10)[0].status, 'completed')
            completed = self.services()[1].snapshot(binding)
            self.assertEqual(self.cancel(client, mid).json()['status'], 'completed')
            self.assertEqual(self.services()[1].snapshot(binding), completed)
            self.assertEqual(provider.calls, 1)

    def test_cancel_between_model_calls_or_during_draft_never_publishes_candidate(self):
        for during_draft in (False, True):
            with self.subTest(during_draft=during_draft):
                if during_draft: self.setUp()
                paused, release = threading.Event(), threading.Event()
                class Provider:
                    calls = 0
                    def stream(inner, messages, system=None):
                        inner.calls += 1
                        if system is None:
                            yield 'committed answer ' * 3
                            if not during_draft:
                                paused.set()
                                if not release.wait(10): raise AssertionError('test release missing')
                        else:
                            yield '{"title":"late",'
                            paused.set()
                            if not release.wait(10): raise AssertionError('test release missing')
                            yield '"items":["late"]}'
                provider = Provider()
                with TestClient(self.app) as client, ThreadPoolExecutor(1) as pool:
                    mid, accepted = self.send(client, self.own, 'plan', conversation=uuid.uuid4().hex, intent='consider_trip')
                    binding = self.binding(accepted.json()['receipt'])
                    work = pool.submit(self.work, self.own, provider)
                    try:
                        self.assertTrue(paused.wait(10))
                        self.assertEqual(self.cancel(client, mid).json()['status'], 'cancelled')
                    finally: release.set()
                    self.assertEqual(work.result(timeout=10)[0].status, 'cancelled')
                    self.assertEqual(provider.calls, 2 if during_draft else 1)
                    self.assertEqual(self.services()[1].snapshot(binding).text, 'committed answer ' * 3)
                    with self.database.connect(self.scope) as conn:
                        self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0], 0)

    def test_cancel_preserves_committed_candidate_and_completed_run(self):
        with TestClient(self.app) as client:
            mid, accepted = self.send(client, self.own, 'plan', conversation=uuid.uuid4().hex, intent='consider_trip')
            binding = self.binding(accepted.json()['receipt']); _, runs = self.services()
            runs.accept(binding); runs.apply(Event(binding, 1, 'start', 'started'))
            runs.apply(Event(binding, 2, 'text', 'text_delta', 'committed partial'))
            publisher = DraftPublisher(self.database.trip_repository(self.scope))
            candidate = publisher.publish(binding.run_id, json.dumps({'title': 'Committed', 'items': ['first']}))
            runs.apply(Event(binding, 3, 'effect', 'effect_committed', 'trip_proposal:' + candidate.proposal_id))
            self.assertEqual(self.cancel(client, mid).json()['status'], 'cancelled')
            stopped = runs.snapshot(binding)
            self.assertEqual((stopped.text, stopped.effects), ('committed partial', ('trip_proposal:' + candidate.proposal_id,)))
            with self.database.connect(self.scope) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0], 1)
            second, accepted = self.send(client, self.own, 'complete', conversation=uuid.uuid4().hex)
            states = {value.message_id: value.status for value in self.work(self.own, FakeProvider())}
            self.assertEqual(states[second], 'completed')
            binding2 = self.binding(accepted.json()['receipt']); completed = runs.snapshot(binding2)
            self.assertEqual(self.cancel(client, second).json()['status'], 'completed')
            self.assertEqual(runs.snapshot(binding2), completed)

    def test_real_commit_ack_loss_requires_original_readback(self):
        original_connect = LocalDatabase.connect
        class Connection:
            def __init__(self, inner): self.inner = inner; self.cancel_write = False
            def __getattr__(self, name): return getattr(self.inner, name)
            def __enter__(self): self.inner.__enter__(); return self
            def __exit__(self, *args): return self.inner.__exit__(*args)
            def cursor(self):
                actual = self.inner.cursor(); parent = self
                class Cursor:
                    def execute(self, sql, args=()):
                        result = actual.execute(sql, args)
                        if sql.startswith('INSERT INTO cj_run_event') and args[4] == 'cancelled': parent.cancel_write = True
                        return result
                    def __getattr__(self, name): return getattr(actual, name)
                return Cursor()
            def commit(self):
                self.inner.commit()
                if self.cancel_write: raise OSError('synthetic lost acknowledgement after actual cancel commit')
        with TestClient(self.app) as client:
            mid, accepted = self.send(client, self.own, 'original', conversation=uuid.uuid4().hex)
            with patch.object(LocalDatabase, 'connect', lambda db, scope: Connection(original_connect(db, scope))):
                response = self.cancel(client, mid)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['error']['outcome'], 'unknown')
            self.assertEqual(response.json()['error']['recovery'], 'reconcile_original')
            binding = self.binding(accepted.json()['receipt'])
            self.assertEqual(self.services()[1].snapshot(binding).status, 'cancelled')
            self.assertEqual(self.cancel(client, mid).json()['event_highwater'], 1)
