"""P2a end to end on real PostgreSQL: login token -> message -> worker -> model -> SSE.

Run by scripts/pg_suites.py (group e2e), which provides CJ_E2E_CONNINFO for a fresh
private cluster with migrations 1-10 applied. FakeProvider only: no network or cost.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

os.environ.setdefault('CJ_ENV', 'local')
from fastapi.testclient import TestClient

from cj_agent.provider import FakeProvider
from cj_agent.worker import RunWorker
from cj_api.local_app import LocalDatabase, create_local_app, scope_for, ISSUER
from cj_message.domain import Service as MessageService
from cj_run.core import Service as RunService

ROOT = Path(__file__).resolve().parents[3]
CONNINFO = os.environ['CJ_E2E_CONNINFO']


class Crash(BaseException):
    """Simulates the worker process dying mid-answer (not an Exception)."""


class CrashingProvider:
    def __init__(self):
        self.calls = 0

    def stream(self, messages):
        self.calls += 1
        yield 'x' * 30
        raise Crash()


def dev_auth(*args):
    return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/dev_auth.py'), *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class LocalEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='g2c-e2e-')
        cls.auth = Path(cls.tmp.name) / 'auth'
        dev_auth('init', str(cls.auth), '--invite', 'alice', '--invite', 'bob')
        cls.app = create_local_app(conninfo_path=CONNINFO, auth_dir=cls.auth)
        cls.database = LocalDatabase(CONNINFO)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def headers(self, subject):
        return {'Authorization': 'Bearer ' + dev_auth('token', str(self.auth), '--subject', subject)}

    def send(self, client, subject, text, conversation='chat-1'):
        opened = client.put('/v1/conversations', params={'conversation_id': conversation}, headers=self.headers(subject))
        if opened.status_code != 200:
            return None, opened
        self.assertEqual(client.put('/v1/conversations', params={'conversation_id': conversation},
                                    headers=self.headers(subject)).json()['generation'],
                         opened.json()['generation'])  # idempotent
        mid = 'm-' + uuid.uuid4().hex
        raw = json.dumps(dict(version='MESSAGE-draft.1', conversation_id=conversation, message_id=mid,
                              text=text, trip_id=None, creation_intent='none'), ensure_ascii=False).encode()
        response = client.post('/v1/messages', content=raw,
                               headers={**self.headers(subject), 'Content-Type': 'application/octet-stream'})
        return mid, response

    def work(self, subject, provider):
        scope = scope_for(ISSUER, subject)
        messages = MessageService(self.database.message_repository(scope), new_run_id=lambda: None)
        runs = RunService(self.database.run_repository(scope),
                          valid=lambda binding: messages.query(binding.message_id) is not None)
        return RunWorker(scope=scope, messages=messages, runs=runs, provider=provider).process()

    def events(self, client, subject, mid, offset=None):
        headers = self.headers(subject)
        if offset is not None:
            headers['Last-Event-ID'] = str(offset)
        with client.stream('GET', '/v1/run-events', params={'message_id': mid}, headers=headers) as response:
            self.assertEqual(response.status_code, 200, response.read())
            self.assertTrue(response.headers['content-type'].startswith('text/event-stream'))
            body = response.read().decode()
        parsed = []
        for block in body.strip().split('\n\n'):
            fields = dict(line.split(': ', 1) for line in block.splitlines())
            parsed.append((fields['event'], int(fields['id']), json.loads(fields['data'])))
        return parsed

    def test_answer_streams_in_both_languages_and_resumes_without_duplication(self):
        fake = FakeProvider()
        with TestClient(self.app) as client:
            for text, expected in (('我想去北京玩三天', '收到：我想去北京玩三天'),
                                   ('Plan three days in Beijing', 'Received: Plan three days in Beijing')):
                mid, response = self.send(client, 'alice', text, conversation='chat-' + uuid.uuid4().hex)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual([o.status for o in self.work('alice', fake) if o.message_id == mid], ['completed'])
                events = self.events(client, 'alice', mid)
                answer = ''.join(e[2]['text'] for e in events if e[0] == 'delta')
                self.assertIn(expected, answer)
                self.assertEqual(events[-1][:1] + (events[-1][2],), ('status', {'status': 'completed'}))
                total = len(answer.encode())
                middle = len(answer[:len(answer) // 2].encode())
                resumed = self.events(client, 'alice', mid, offset=middle)
                tail = ''.join(e[2]['text'] for e in resumed if e[0] == 'delta')
                self.assertEqual(answer.encode()[:middle].decode() + tail, answer)
                self.assertEqual(resumed[-1][1], total)

    def test_other_user_and_uninvited_user_are_refused(self):
        with TestClient(self.app) as client:
            mid, response = self.send(client, 'alice', 'private plan', conversation='chat-' + uuid.uuid4().hex)
            self.assertEqual(response.status_code, 200)
            foreign = client.get('/v1/run-events', params={'message_id': mid}, headers=self.headers('bob'))
            self.assertEqual(foreign.status_code, 503)  # withheld exactly like an absent message
            _, uninvited = self.send(client, 'carol', 'hello')
            self.assertIn(uninvited.status_code, (401, 403))
            self.assertEqual(client.get('/v1/run-events', params={'message_id': mid}).status_code, 401)

    def test_crash_mid_answer_becomes_unknown_without_resending(self):
        conversation = 'chat-' + uuid.uuid4().hex
        with TestClient(self.app) as client:
            mid, _ = self.send(client, 'bob', 'crash me', conversation=conversation)
            crashing = CrashingProvider()
            with self.assertRaises(Crash):
                self.work('bob', crashing)
            later, _ = self.send(client, 'bob', 'next question', conversation=conversation)
            fake = FakeProvider()
            outcomes = {o.message_id: o.status for o in self.work('bob', fake)}
            self.assertEqual(outcomes[mid], 'unknown')
            self.assertEqual(crashing.calls, 1)
            self.assertEqual(fake.calls, 0)  # the interrupted request is not sent again
            # RUN keeps later messages in that chat queued until the unknown run is reconciled.
            self.assertEqual(outcomes[later], 'waiting')
            events = self.events(client, 'bob', mid)
            self.assertEqual(events[-1][2], {'status': 'unknown'})
            self.assertEqual(''.join(e[2]['text'] for e in events if e[0] == 'delta'), 'x' * 30)


if __name__ == '__main__':
    unittest.main(verbosity=2)
