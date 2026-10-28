"""P2a end to end on real PostgreSQL: login token -> message -> worker -> model -> SSE.

Run by scripts/pg_suites.py (group e2e), which provides CJ_E2E_CONNINFO for a fresh
private cluster with migrations 1-10 applied. FakeProvider only: no network or cost.
"""
import json
import base64
import secrets
import time
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

os.environ.setdefault('CJ_ENV', 'local')
from fastapi.testclient import TestClient

from cj_agent.draft import DraftPublisher, trip_scope_for
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


class Harness(unittest.TestCase):
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

    def send(self, client, subject, text, conversation='chat-1', intent='none'):
        opened = client.put('/v1/conversations', params={'conversation_id': conversation}, headers=self.headers(subject))
        if opened.status_code != 200:
            return None, opened
        self.assertEqual(client.put('/v1/conversations', params={'conversation_id': conversation},
                                    headers=self.headers(subject)).json()['generation'],
                         opened.json()['generation'])  # idempotent
        mid = 'm-' + uuid.uuid4().hex
        status = client.get('/v1/message-send-status', params={'conversation_id': conversation},
                            headers=self.headers(subject))
        self.assertEqual(status.status_code, 200, status.text)
        head = status.json()['head']
        raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id=conversation, message_id=mid,
                              text=text, trip_id=None, creation_intent=intent,
                              expected_generation=head['generation'],
                              expected_sequence=head['last_sequence']), ensure_ascii=False).encode()
        response = client.post('/v1/messages', content=raw,
                               headers={**self.headers(subject), 'Content-Type': 'application/octet-stream'})
        return mid, response

    def work(self, subject, provider):
        scope = scope_for(ISSUER, subject)
        messages = MessageService(self.database.message_repository(scope), new_run_id=lambda: None)
        runs = RunService(self.database.run_repository(scope),
                          valid=lambda binding: messages.query(binding.message_id) is not None)
        drafts = DraftPublisher(self.database.trip_repository(scope))
        return RunWorker(scope=scope, messages=messages, runs=runs, provider=provider, drafts=drafts).process()

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



class LocalEndToEnd(Harness):
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
            cid = response.json()['receipt']['conversation_id']
            for conversation, message in ((cid, mid), ('absent-chat', 'absent-message')):
                status = client.get('/v1/message-send-status',
                                    params={'conversation_id': conversation, 'message_id': message},
                                    headers=self.headers('bob'))
                self.assertEqual(status.status_code, 200, status.text)
                self.assertIsNone(status.json()['receipt'])
                self.assertIsNone(status.json()['head'])
            _, uninvited = self.send(client, 'carol', 'hello')
            self.assertIn(uninvited.status_code, (401, 403))
            self.assertEqual(client.get('/v1/run-events', params={'message_id': mid}).status_code, 401)

    def test_process_crash_after_accept_before_dispatch_recovers_one_original_run(self):
        subject = 'crash-' + uuid.uuid4().hex
        auth = Path(self.tmp.name) / subject
        dev_auth('init', str(auth), '--invite', subject)
        headers = {'Authorization': 'Bearer ' + dev_auth('token', str(auth), '--subject', subject)}
        app = create_local_app(conninfo_path=CONNINFO, auth_dir=auth)
        conversation, mid = uuid.uuid4().hex, uuid.uuid4().hex
        with TestClient(app) as client:
            self.assertEqual(client.put('/v1/conversations', params={'conversation_id': conversation},
                                        headers=headers).status_code, 200)
            head = client.get('/v1/message-send-status', params={'conversation_id': conversation},
                              headers=headers).json()['head']
        raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id=conversation, message_id=mid,
                              text='recover original', trip_id=None, creation_intent='none',
                              expected_generation=head['generation'], expected_sequence=head['last_sequence']))
        child = '''import os, sys, subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app
conninfo, auth, raw, issuer, subject = sys.argv[1:]
token = subprocess.check_output([sys.executable, '-B', issuer, 'token', auth, '--subject', subject], text=True).strip()
with TestClient(create_local_app(conninfo_path=conninfo, auth_dir=Path(auth))) as client:
    response = client.post('/v1/messages', content=raw.encode(), headers={'Authorization':'Bearer '+token, 'Content-Type':'application/octet-stream'})
    if response.status_code != 200: raise RuntimeError('synthetic receive failed')
    os._exit(73)  # committed, no response to parent and no worker dispatch
'''
        crashed = subprocess.run([sys.executable, '-B', '-c', child, CONNINFO, str(auth), raw,
                                  str(ROOT / 'scripts/dev_auth.py'), subject], capture_output=True, text=True)
        self.assertEqual(crashed.returncode, 73, crashed.stderr)
        with TestClient(create_local_app(conninfo_path=CONNINFO, auth_dir=auth)) as recovered:
            status = recovered.get('/v1/message-send-status', params={'conversation_id': conversation, 'message_id': mid},
                                   headers=headers)
            self.assertEqual(status.status_code, 200, status.text)
            receipt = status.json()['receipt']
            replay = recovered.post('/v1/messages', content=raw.encode(),
                                    headers={**headers, 'Content-Type': 'application/octet-stream'})
            self.assertEqual(replay.json()['receipt'], receipt)
        provider = FakeProvider()
        self.assertTrue(self.work(subject, provider))
        self.assertFalse(self.work(subject, provider))
        with self.database.connect(scope_for(ISSUER, subject)) as conn:
            self.assertEqual(conn.execute('SELECT run_id FROM cj_run_record').fetchall(), [(receipt['run_id'],)])
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0], 1)

    def test_runtime_database_enforces_bidirectional_scope_without_repository_filters(self):
        import psycopg
        scopes = {s: scope_for(ISSUER, s) for s in ('alice', 'bob')}
        with TestClient(self.app) as client:
            for subject in scopes:
                self.send(client, subject, 'synthetic private', conversation='isolation-' + uuid.uuid4().hex)
        for subject, other in (('alice', 'bob'), ('bob', 'alice')):
            with self.subTest(subject=subject):
                with self.database.connect(scopes[subject]) as conn:
                    self.assertEqual(conn.execute('SELECT current_user').fetchone()[0], 'cj_m1_runtime')
                    self.assertEqual(conn.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone(), (False, False))
                    self.assertGreater(conn.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0], 0)
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s', (scopes[other],)).fetchone()[0], 0)
                    self.assertEqual(conn.execute('UPDATE cj_message_chat SET active=false WHERE scope=%s RETURNING conversation_id', (scopes[other],)).fetchall(), [])
                    for table, foreign_scope in (('cj_message_scope', scopes[other]), ('cj_run_scope', scopes[other]),
                                                 ('cj_trip_scope', trip_scope_for(scopes[other]))):
                        with self.subTest(table=table), self.assertRaises(psycopg.errors.InsufficientPrivilege):
                            with conn.transaction():
                                if table == 'cj_run_scope':
                                    conn.execute('INSERT INTO cj_run_scope(scope,epoch,active) VALUES (%s,%s,true)', (foreign_scope + '-forged', '1'))
                                else:
                                    conn.execute('INSERT INTO ' + table + '(scope) VALUES (%s)', (foreign_scope + '-forged',))
                    conn.rollback()

    def test_runtime_database_missing_scope_fails_closed_and_cannot_assume_initializer(self):
        import psycopg
        with psycopg.connect(**self.database.conninfo) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_message_chat').fetchone()[0], 0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute("INSERT INTO cj_message_scope(scope) VALUES ('unbound')")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    from psycopg import sql
                    initializer = json.loads(Path(CONNINFO).read_text())['user']
                    conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(initializer)))

    def test_runtime_role_rejects_privileged_membership_or_bypassrls(self):
        import psycopg
        from psycopg import sql
        from cj_api.composition import CompositionUnavailable
        config = json.loads(Path(CONNINFO).read_text())
        scope = scope_for(ISSUER, 'alice')
        with psycopg.connect(**config, autocommit=True) as admin:
            try:
                admin.execute('ALTER ROLE cj_m1_runtime BYPASSRLS')
                with self.assertRaises(CompositionUnavailable): self.database.connect(scope)
            finally:
                admin.execute('ALTER ROLE cj_m1_runtime NOBYPASSRLS')
            try:
                admin.execute(sql.SQL('GRANT {} TO cj_m1_runtime').format(sql.Identifier(config['user'])))
                with self.assertRaises(CompositionUnavailable): self.database.connect(scope)
            finally:
                admin.execute(sql.SQL('REVOKE {} FROM cj_m1_runtime').format(sql.Identifier(config['user'])))

    def test_worker_rechecks_invitation_before_provider_dispatch(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import run_worker
        from cj_agent.provider import ProviderFailed
        class CountingProvider(FakeProvider):
            calls = 0
            def stream(self, *args, **kwargs):
                self.calls += 1
                yield from super().stream(*args, **kwargs)
        model = CountingProvider()
        with TestClient(self.app) as client:
            mid, response = self.send(client, 'alice', 'must not dispatch after revocation', conversation=uuid.uuid4().hex)
            self.assertEqual(response.status_code, 200)
        wrapper = run_worker.InvitedProvider(model, self.auth, 'alice')
        original = (self.auth / 'invited.json').read_bytes()
        try:
            (self.auth / 'invited.json').write_text('[]')
            self.assertEqual(run_worker.run_once(self.database, model, self.auth), [])
            with self.assertRaises(ProviderFailed): list(wrapper.stream([{'role':'user','content':'synthetic'}]))
            self.assertEqual(model.calls, 0)
            scope = scope_for(ISSUER, 'alice')
            self.assertIsNotNone(MessageService(self.database.message_repository(scope), new_run_id=lambda: None).query(mid))
        finally:
            (self.auth / 'invited.json').write_bytes(original)

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


class BadDraftProvider(FakeProvider):
    def stream(self, messages, system=None):
        if system is not None:
            yield 'I would rather chat than give JSON.'
            return
        yield from super().stream(messages)


class DraftToTrip(Harness):
    def act(self, client, subject, kind, proposal):
        raw = json.dumps(['a-' + uuid.uuid4().hex, kind, proposal['proposal_id'], proposal['candidate_hash'],
                          'ui-confirm'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        response = client.post('/v1/trip-actions', content=raw,
                               headers={**self.headers(subject), 'Content-Type': 'application/octet-stream'})
        return raw, response

    def draft(self, client, subject, text, provider=None):
        mid, response = self.send(client, subject, text, conversation='trip-' + uuid.uuid4().hex,
                                  intent='consider_trip')
        self.assertEqual(response.status_code, 200, response.text)
        run_id = response.json()['receipt']['run_id']
        outcome = [o for o in self.work(subject, provider or FakeProvider()) if o.message_id == mid][0]
        return run_id, outcome

    def test_draft_accept_writes_formal_trip_and_reject_does_not(self):
        with TestClient(self.app) as client:
            run_id, outcome = self.draft(client, 'alice', '帮我安排北京三天')
            self.assertEqual((outcome.status, outcome.proposal_id), ('completed', 'p-' + run_id))
            proposal = client.get('/v1/trip-proposals', params={'proposal_id': outcome.proposal_id},
                                  headers=self.headers('alice'))
            self.assertEqual(proposal.status_code, 200, proposal.text)
            snapshot = proposal.json()['proposal']
            self.assertEqual(snapshot['status'], 'pending')
            self.assertEqual(snapshot['document']['title'], '北京三日游')
            self.assertTrue(all(i['verification'] == 'pending' and i['evidence'] == []
                                for i in snapshot['document']['items']))
            # Another user cannot see or act on it.
            self.assertNotEqual(client.get('/v1/trip-proposals', params={'proposal_id': outcome.proposal_id},
                                           headers=self.headers('bob')).status_code, 200)
            _, foreign = self.act(client, 'bob', 'accept', snapshot)
            self.assertNotEqual(foreign.status_code, 200)
            raw, accepted = self.act(client, 'alice', 'accept', snapshot)
            self.assertEqual(accepted.status_code, 200, accepted.text)
            receipt = accepted.json()['receipt']
            self.assertEqual((receipt['kind'], receipt['committed_version']), ('accept', 1))
            replay = client.post('/v1/trip-actions', content=raw,
                                 headers={**self.headers('alice'), 'Content-Type': 'application/octet-stream'})
            self.assertEqual(replay.json()['receipt'], receipt)  # same action, same original result
            _, again = self.act(client, 'alice', 'accept', snapshot)
            self.assertEqual(again.status_code, 409)  # a decided candidate cannot be accepted twice
            detail = client.get('/v1/trip-details', params={'trip_id': snapshot['trip_id']}, headers=self.headers('alice'))
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.json()['trip']['version'], 1)
            self.assertEqual(detail.json()['trip']['document'], snapshot['document'])
            listed = client.get('/v1/trips', params={'limit': 50}, headers=self.headers('alice')).json()
            self.assertIn(snapshot['trip_id'], [t['trip_id'] for t in listed['trips']])

            run_id, outcome = self.draft(client, 'alice', 'Plan Beijing for me')
            snapshot = client.get('/v1/trip-proposals', params={'proposal_id': outcome.proposal_id},
                                  headers=self.headers('alice')).json()['proposal']
            _, rejected = self.act(client, 'alice', 'reject', snapshot)
            self.assertEqual(rejected.json()['receipt']['committed_version'], None)
            absent = client.get('/v1/trip-details', params={'trip_id': snapshot['trip_id']}, headers=self.headers('alice'))
            self.assertEqual((absent.status_code, absent.json()['trip']), (200, None))  # rejected: no formal Trip

    def test_invalid_model_draft_publishes_nothing_but_answer_completes(self):
        with TestClient(self.app) as client:
            run_id, outcome = self.draft(client, 'bob', 'Beijing please', provider=BadDraftProvider())
            self.assertEqual((outcome.status, outcome.proposal_id), ('completed', None))
            self.assertNotEqual(client.get('/v1/trip-proposals', params={'proposal_id': 'p-' + run_id},
                                           headers=self.headers('bob')).status_code, 200)


class SignedTripConfirmation(Harness):
    draft = DraftToTrip.draft

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from cj_trip.confirmation import ConfirmationSigner
        cls.signer = ConfirmationSigner(secrets.token_bytes(32))
        cls.app = create_local_app(conninfo_path=CONNINFO, auth_dir=cls.auth, confirmation_signer=cls.signer)

    def prepare(self, client, snapshot, kind='accept', subject='alice', action_id=None):
        return client.post('/v1/trip-confirmations', json=dict(action_id=action_id or uuid.uuid4().hex,
            kind=kind, proposal_id=snapshot['proposal_id'], candidate_hash=snapshot['candidate_hash']),
            headers=self.headers(subject))

    def post_action(self, client, raw, subject='alice'):
        return client.post('/v1/trip-actions', content=raw,
            headers={**self.headers(subject), 'Content-Type': 'application/octet-stream'})

    def test_all_m1_tables_enforce_runtime_scope_after_signed_flow(self):
        from psycopg import sql
        tables = ('cj_message_scope', 'cj_message_chat', 'cj_message_receipt',
                  'cj_message_delivery', 'cj_message_draft', 'cj_run_scope',
                  'cj_run_record', 'cj_run_event', 'cj_trip_scope',
                  'cj_trip_proposal', 'cj_trip_record', 'cj_trip_receipt')
        with TestClient(self.app) as client:
            for subject in ('alice', 'bob'):
                _, outcome = self.draft(client, subject, 'Synthetic Beijing plan')
                scope = scope_for(ISSUER, subject)
                message = MessageService(self.database.message_repository(scope), new_run_id=lambda: None)
                receipt = message.query(outcome.message_id).receipt
                message.save_draft(receipt.conversation_id, receipt.generation, b'synthetic draft', 0)
                proposal = client.get('/v1/trip-proposals', params={'proposal_id': outcome.proposal_id}, headers=self.headers(subject)).json()['proposal']
                prepared = self.prepare(client, proposal, subject=subject)
                self.assertEqual(prepared.status_code, 200)
                raw = base64.b64decode(prepared.json()['action_utf8_base64'], validate=True)
                self.assertEqual(self.post_action(client, raw, subject).status_code, 200)
        for subject, other in (('alice', 'bob'), ('bob', 'alice')):
            with self.database.connect(scope_for(ISSUER, subject)) as conn:
                for table in tables:
                    with self.subTest(subject=subject, table=table):
                        relation = sql.Identifier(table)
                        expected = scope_for(ISSUER, subject)
                        foreign = scope_for(ISSUER, other)
                        if table.startswith('cj_trip_'):
                            expected, foreign = trip_scope_for(expected), trip_scope_for(foreign)
                        rows = conn.execute(sql.SQL('SELECT DISTINCT scope FROM {}').format(relation)).fetchall()
                        self.assertEqual(rows, [(expected,)])  # own rows exist: no vacuous foreign denial
                        self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {} WHERE scope=%s').format(relation), (foreign,)).fetchone()[0], 0)
                        self.assertEqual(conn.execute(sql.SQL('UPDATE {} SET scope=scope WHERE scope=%s RETURNING scope').format(relation), (foreign,)).fetchall(), [])
                        flags = conn.execute('SELECT relrowsecurity,relforcerowsecurity,relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) FROM pg_class WHERE oid=%s::regclass', (table,)).fetchone()
                        self.assertEqual(flags, (True, True, False))
                conn.rollback()

    def test_signed_accept_reject_replay_and_foreign_refusal(self):
        with TestClient(self.app) as client:
            for kind in ('accept', 'reject'):
                _, outcome = self.draft(client, 'alice', 'Beijing please')
                snapshot = client.get('/v1/trip-proposals', params={'proposal_id': outcome.proposal_id},
                    headers=self.headers('alice')).json()['proposal']
                self.assertEqual(self.prepare(client, snapshot, subject='bob').status_code, 503)
                response = self.prepare(client, snapshot, kind)
                self.assertEqual(response.status_code, 200, response.text)
                prepared = response.json()
                self.assertEqual(prepared['proposal'], snapshot)
                self.assertLessEqual(prepared['expires_at'], snapshot['expires_at'])
                raw = base64.b64decode(prepared['action_utf8_base64'], validate=True)
                original = json.loads(raw)
                self.assertIsNone(client.get('/v1/trip-details', params={'trip_id': snapshot['trip_id']},
                    headers=self.headers('alice')).json()['trip'])
                self.assertEqual(self.post_action(client, raw, 'bob').status_code, 503)
                tampered = list(original); tampered[4] = 'caller-confirmed'
                self.assertEqual(self.post_action(client, json.dumps(tampered, separators=(',', ':')).encode()).status_code, 503)
                accepted = self.post_action(client, raw)
                self.assertEqual(accepted.status_code, 200, accepted.text)
                self.assertEqual(accepted.json()['receipt']['committed_version'], 1 if kind == 'accept' else None)
                self.assertEqual(self.post_action(client, raw).json()['receipt'], accepted.json()['receipt'])
                self.assertEqual(self.prepare(client, snapshot, kind, action_id=original[0]).status_code, 409)
                detail = client.get('/v1/trip-details', params={'trip_id': snapshot['trip_id']},
                    headers=self.headers('alice')).json()['trip']
                if kind == 'accept': self.assertEqual(detail['document'], snapshot['document'])
                else: self.assertIsNone(detail)

    def test_issuance_withholds_if_auth_changes_during_signing(self):
        from cj_trip.confirmation import ConfirmationSigner
        with TestClient(self.app) as client:
            _, outcome = self.draft(client, 'alice', 'Beijing please')
            snapshot = client.get('/v1/trip-proposals', params={'proposal_id': outcome.proposal_id},
                headers=self.headers('alice')).json()['proposal']
        def withdraw():
            (self.auth / 'invited.json').write_text('[]')
            return time.time()
        changed = create_local_app(conninfo_path=CONNINFO, auth_dir=self.auth,
            confirmation_signer=ConfirmationSigner(secrets.token_bytes(32), clock=withdraw))
        try:
            with TestClient(changed) as client:
                response = self.prepare(client, snapshot)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('action_utf8_base64', response.json())
        finally:
            (self.auth / 'invited.json').write_text(json.dumps(['alice', 'bob']))


if __name__ == '__main__':
    from transaction_scope_checks import TransactionScopeChecks
    from cancellation_checks import CancellationChecks
    from ownership_checks import OwnershipChecks
    unittest.main(verbosity=2)
