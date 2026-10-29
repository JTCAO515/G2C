"""Worker ownership/restart checks on signed local API and private PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
import json
from unittest.mock import patch
import socket
import httpx
import uvicorn

from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_agent.worker import RunWorker
from cj_message.domain import Service as MessageService
from cj_run.core import Service as RunService, WorkerOwnershipLost
from cj_run.core import ResyncRequired
from e2e_local import Harness, CONNINFO
import cancellation_checks as fixtures


class OwnershipChecks(Harness):
    setUp = fixtures.CancellationChecks.setUp
    services = fixtures.CancellationChecks.services
    binding = fixtures.CancellationChecks.binding

    def test_tcp_disconnect_resume_and_expired_cursor_use_original_snapshot(self):
        paused, release = threading.Event(), threading.Event()
        prefix, tail = '已提交片段 🧳 ' * 4, '后续片段 / tail'
        class Provider:
            calls = 0
            def stream(self, messages, system=None):
                self.calls += 1
                yield prefix
                paused.set()
                if not release.wait(20): raise AssertionError('test release missing')
                yield tail
        provider = Provider()
        with TestClient(self.app) as client:
            mid, accepted = self.send(client, self.own, 'stream', conversation=uuid.uuid4().hex)
        binding = self.binding(accepted.json()['receipt'])
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0)); port = available.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(self.app, host='127.0.0.1', port=port, log_level='error', access_log=False))
        thread = threading.Thread(target=server.run, daemon=True); thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            self.assertTrue(thread.is_alive()); self.assertLess(time.monotonic(), deadline); time.sleep(.02)
        headers = self.headers(self.own)
        url = f'http://127.0.0.1:{port}'
        try:
            with ThreadPoolExecutor(1) as pool, httpx.Client(base_url=url, timeout=10) as client:
                working = pool.submit(self.worker(provider).process)
                try:
                    self.assertTrue(paused.wait(15))
                    event = None; offset = None; first = None
                    with client.stream('GET', '/v1/run-events', params={'message_id': mid}, headers=headers) as stream:
                        self.assertEqual(stream.status_code, 200)
                        for line in stream.iter_lines():
                            if line.startswith('event: '): event = line[7:]
                            elif line.startswith('id: '): offset = int(line[4:])
                            elif line.startswith('data: ') and event == 'delta':
                                first = json.loads(line[6:])['text']; break
                    self.assertEqual(first, prefix)
                    self.assertEqual(offset, len(prefix.encode()))
                    self.assertEqual(self.services()[1].snapshot(binding).status, 'running')
                finally: release.set()
                self.assertEqual(working.result(timeout=15)[0].status, 'completed')
                response = client.get('/v1/run-events', params={'message_id': mid}, headers={**headers, 'Last-Event-ID': str(offset)})
                self.assertEqual(response.status_code, 200)
                frames = [dict(line.split(': ', 1) for line in block.splitlines()) for block in response.text.strip().split('\n\n')]
                rest = ''.join(json.loads(frame['data'])['text'] for frame in frames if frame['event'] == 'delta')
                self.assertEqual(first + rest, prefix + tail)
                self.assertEqual(json.loads(frames[-1]['data']), {'status': 'completed'})
                repeated = client.get('/v1/run-events', params={'message_id': mid}, headers={**headers, 'Last-Event-ID': str(len((prefix + tail).encode()))})
                self.assertNotIn('event: delta', repeated.text)
                repository = self.database.run_repository(self.scope)
                old = repository.recover(binding).cursor
                with self.database.connect(self.scope) as conn:
                    conn.execute('UPDATE cj_run_scope SET epoch=%s WHERE scope=%s', ('rotated-epoch', self.scope))
                with self.assertRaises(ResyncRequired): repository.events(old, limit=1)
                invalid = client.get('/v1/run-events', params={'message_id': mid}, headers={**headers, 'Last-Event-ID': str(len((prefix + tail).encode()) + 1)})
                self.assertEqual(invalid.status_code, 409)
                snapshot = client.get('/v1/run-display', params={'message_id': mid}, headers=headers).json()['snapshot']
                self.assertEqual((snapshot['run_id'], snapshot['text'], snapshot['text_state']), (binding.run_id, prefix + tail, 'complete'))
                self.assertEqual(provider.calls, 1)
                self.assertEqual(self.worker(FakeProvider()).process(), [])
        finally:
            release.set(); server.should_exit = True; thread.join(timeout=10)
            self.assertFalse(thread.is_alive())

    def test_actual_worker_entry_rechecks_revoked_or_unknown_authorization_before_publication(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
        import run_worker
        for unavailable in (False, True):
            with self.subTest(unavailable=unavailable):
                if unavailable: self.setUp()
                source = self.auth / 'invited.json'
                original = source.read_bytes()
                # Same formal entry and security assertions, now with real explicit
                # quota/NEEDS setup instead of the retired unmetered branch.
                from cj_api.local_run_context import load_run_context
                from cj_api.local_app import app_from_environment, LocalDatabase
                import local_run_context as operator
                now=int(time.time());context_file=self.auth/'run-context.json'
                context_file.write_text(json.dumps({'version':'CJ-LOCAL-RUN@1','current':{
                    'meter':dict(unit='provider_call',budget=4,period_start=now-10,period_end=now+3600,
                                 max_steps=4,max_tools=1,max_output=10000,max_seconds=600),
                    'output_limits':{'answer':1000,'draft':1000}},'history':[]}))
                context=load_run_context(context_file)
                operator.provision_budget(CONNINFO,context,self.own)
                operator.provision_budget(CONNINFO,context,self.other)
                with patch.dict('os.environ',{'CJ_LOCAL_CONNINFO':CONNINFO,'CJ_LOCAL_AUTH_DIR':str(self.auth),
                                              'CJ_LOCAL_RUN_CONTEXT':str(context_file)}):
                    self.app=app_from_environment()
                self.database=LocalDatabase(CONNINFO,run_context=context)
                operator.put_needs(CONNINFO,self.auth,self.own,json.dumps(dict(action_id='needs',needs_id='needs',
                    expected_version=0,source={'kind':'manual','text':'explicit test input'},
                    changes={'party_size':{'state':'known','value':1}})).encode())
                class Provider(FakeProvider):
                    calls = 0
                    def stream(inner, messages, system=None):
                        inner.calls += 1
                        yield 'committed before authority change ' * 2
                        source.write_text('{invalid-json' if unavailable else '[]')
                        yield 'MUST_NOT_PUBLISH_AFTER_AUTH_CHANGE' * 2
                model = Provider()
                with TestClient(self.app) as client:
                    conversation=uuid.uuid4().hex
                    self.assertEqual(client.put('/v1/conversations',params={'conversation_id':conversation},headers=self.headers(self.own)).status_code,200)
                    operator.bind_needs(CONNINFO,self.own,conversation,'needs')
                    _, accepted = self.send(client, self.own, 'original', conversation=conversation, intent='consider_trip')
                binding = self.binding(accepted.json()['receipt'])
                try:
                    outcomes = run_worker.run_once(self.database, model, self.auth)
                    self.assertEqual(outcomes[0].status, 'unknown' if unavailable else 'context_invalid')
                    state = self.services()[1].snapshot(binding)
                    self.assertEqual(state.text, 'committed before authority change ' * 2)
                    self.assertEqual(state.effects, ())
                    self.assertEqual(model.calls, 1)
                finally: source.write_bytes(original)

    def worker(self, provider, *, capture=None):
        messages = MessageService(self.database.message_repository(self.scope), lambda: None)
        repository = self.database.run_repository(self.scope)
        if capture is not None:
            connect = repository.connect
            def captured():
                conn = connect(); capture.append(conn); return conn
            repository.connect = captured
        return RunWorker(scope=self.scope, messages=messages, runs=RunService(repository,
                         lambda b: messages.query(b.message_id) is not None), provider=provider)

    def test_same_chat_waits_while_other_chat_progresses_without_duplicate_runs(self):
        paused, release = threading.Event(), threading.Event()
        class Provider:
            def __init__(self): self.calls = []
            def stream(self, messages, system=None):
                text = messages[-1]['content']; self.calls.append(text)
                yield text * 3
                if text == 'first-message':
                    paused.set()
                    if not release.wait(15): raise AssertionError('test release missing')
                yield ' done'
        provider = Provider(); other = FakeProvider()
        with TestClient(self.app) as client, ThreadPoolExecutor(1) as pool:
            chat = 'a-' + uuid.uuid4().hex
            first, r1 = self.send(client, self.own, 'first-message', conversation=chat)
            second, r2 = self.send(client, self.own, 'second-message', conversation=chat)
            unrelated, r3 = self.send(client, self.own, 'unrelated-chat', conversation='z-' + uuid.uuid4().hex)
            original = pool.submit(self.worker(provider).process, 2)
            try:
                self.assertTrue(paused.wait(15))
                outcomes = {value.message_id: value.status for value in self.worker(other).process()}
                self.assertEqual(outcomes, {first: 'waiting', second: 'waiting', unrelated: 'completed'})
                self.assertEqual(self.services()[1].snapshot(self.binding(r1.json()['receipt'])).status, 'running')
            finally: release.set()
            self.assertEqual([value.status for value in original.result(timeout=15)], ['completed', 'completed'])
            self.assertEqual(provider.calls, ['first-message', 'second-message'])
            self.assertEqual(other.calls, 1)
            runs = self.services()[1]
            self.assertEqual(runs.snapshot(self.binding(r1.json()['receipt'])).text, 'first-message' * 3 + ' done')
            self.assertEqual(runs.snapshot(self.binding(r2.json()['receipt'])).text, 'second-message' * 3 + ' done')
            self.assertEqual(self.worker(FakeProvider()).process(), [])
            with self.database.connect(self.scope) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_run_record').fetchone()[0], 3)

    def test_worker_process_death_releases_owner_and_recovers_original_unknown(self):
        with TestClient(self.app) as client:
            mid, accepted = self.send(client, self.own, 'crash original', conversation=uuid.uuid4().hex)
        binding = self.binding(accepted.json()['receipt'])
        ready = Path(self.tmp.name) / (uuid.uuid4().hex + '.ready')
        child = '''import sys, time
from pathlib import Path
from cj_api.local_app import LocalDatabase
from cj_message.domain import Service as Messages
from cj_run.core import Service as Runs
from cj_agent.worker import RunWorker
path, scope, ready = sys.argv[1:]
db = LocalDatabase(path)
messages = Messages(db.message_repository(scope), lambda: None)
runs = Runs(db.run_repository(scope), lambda b: messages.query(b.message_id) is not None)
class Provider:
    def stream(self, messages, system=None):
        yield 'committed before process death ' * 2
        Path(ready).write_text('provider is paused')
        time.sleep(120)
RunWorker(scope=scope, messages=messages, runs=runs, provider=Provider()).process()
'''
        process = subprocess.Popen([sys.executable, '-B', '-c', child, CONNINFO, self.scope, str(ready)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 40
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(ready.exists(), 'fresh worker did not reach committed partial state')
            state = self.services()[1].snapshot(binding)
            self.assertEqual((state.status, state.text), ('running', 'committed before process death ' * 2))
            model = FakeProvider()
            self.assertEqual(self.worker(model).process()[0].status, 'waiting')
            process.kill(); process.wait(timeout=10)
            deadline = time.monotonic() + 10
            while True:
                recovered = self.worker(model).process()
                if recovered and recovered[0].status != 'waiting': break
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.05)
            self.assertEqual(recovered[0].status, 'unknown')
            self.assertEqual(model.calls, 0)
            original = self.services()[1].snapshot(binding)
            self.assertEqual((original.binding.run_id, original.text), (binding.run_id, state.text))
            self.assertEqual(original.status, 'unknown')
            self.assertEqual(self.worker(model).process(), [])
        finally:
            if process.poll() is None: process.kill(); process.wait(timeout=10)
            process.communicate(timeout=10)

    def test_lost_physical_owner_cannot_publish_and_scope_is_not_session_bound(self):
        paused, release = threading.Event(), threading.Event()
        connections = []
        class Provider:
            calls = 0
            def stream(self, messages, system=None):
                self.calls += 1
                yield 'already committed ' * 3
                paused.set()
                if not release.wait(15): raise AssertionError('test release missing')
                yield 'STALE LATE TEXT'
        provider = Provider()
        with TestClient(self.app) as client, ThreadPoolExecutor(1) as pool:
            _, accepted = self.send(client, self.own, 'original', conversation=uuid.uuid4().hex)
            binding = self.binding(accepted.json()['receipt'])
            running = pool.submit(self.worker(provider, capture=connections).process)
            try:
                self.assertTrue(paused.wait(15))
                owner = connections[0]
                settings = owner.execute("SELECT current_setting('cj.message_scope',true), current_setting('cj.trip_scope',true)").fetchone()
                self.assertTrue(all(value in (None, '') for value in settings))
                owner.rollback(); owner.close()
            finally: release.set()
            with self.assertRaises(WorkerOwnershipLost): running.result(timeout=15)
            state = self.services()[1].snapshot(binding)
            self.assertEqual((state.status, state.text), ('running', 'already committed ' * 3))
            recovered = FakeProvider()
            self.assertEqual(self.worker(recovered).process()[0].status, 'unknown')
            self.assertEqual(recovered.calls, 0)
            self.assertEqual(self.services()[1].snapshot(binding).text, state.text)

    def test_dirty_advisory_session_is_refused_without_reentrant_acquisition(self):
        with TestClient(self.app) as client:
            _, accepted = self.send(client, self.own, 'original', conversation=uuid.uuid4().hex)
        binding = self.binding(accepted.json()['receipt'])
        conn = self.database.connect(self.scope)
        cursor = conn.cursor(); cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED'); conn.bind_scope(cursor)
        cursor.execute('SELECT pg_advisory_lock(17)'); conn.commit(); cursor.close()
        repository = self.database.run_repository(self.scope); repository.connect = lambda: conn
        with self.assertRaises(WorkerOwnershipLost):
            with repository.worker_lease(binding): self.fail('dirty session granted ownership')
        self.assertTrue(conn.closed)
        with self.database.run_repository(self.scope).worker_lease(binding) as check:
            self.assertIsNotNone(check); check()
        with self.assertRaises(WorkerOwnershipLost): check()
