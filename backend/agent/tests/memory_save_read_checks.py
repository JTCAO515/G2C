"""#226: signed local MEMORY API and runtime-role SQL on a fresh private PG.

All statements and identities are synthetic. Initialization identity is used by
pg_suites only for migrations, never by these business operations.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import sys
import time
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from fastapi.testclient import TestClient

from e2e_local import Harness, CONNINFO, ROOT
from cj_api.local_app import app_from_environment, scope_for, ISSUER
from cj_api.composition import CompositionUnavailable
from cj_memory.domain import Service, CommitUnknown, Unavailable, Conflict
from cj_memory.postgres import Repository

TABLES = ('cj_memory_scope', 'cj_memory_source', 'cj_memory_item', 'cj_memory_operation')


class MemorySaveReadChecks(Harness):
    def setUp(self):
        self.tag = uuid.uuid4().hex[:10]
        self.chat_a, self.chat_b = 'memory-a-' + self.tag, 'memory-b-' + self.tag
        self.slots = {kind: kind + '-' + self.tag for kind in ('fact', 'experience', 'preference', 'ambiguous', 'blocked')}
        slot_rules = {self.slots[kind]: dict(kind=kind, collection_allowed=True, semantic_resolved=True)
                      for kind in ('fact', 'experience', 'preference')}
        slot_rules[self.slots['ambiguous']] = dict(kind='fact', collection_allowed=True, semantic_resolved=False)
        slot_rules[self.slots['blocked']] = dict(kind='fact', collection_allowed=False, semantic_resolved=True)
        profile = dict(subjects=['self'], slots=slot_rules, extents=['long_term', 'current'],
                       context_ids=[self.chat_a, self.chat_b])
        self.policy = dict(version='local-memory-policy.1',
                           expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                           profiles={'alice': profile, 'bob': deepcopy(profile)})
        self.policy_path = self.auth / ('memory-policy-' + self.tag + '.json')
        self.write_policy()
        self.memory_app = self.app_from_policy()

    def write_policy(self):
        self.policy_path.write_text(json.dumps(self.policy)); self.policy_path.chmod(0o600)

    def app_from_policy(self, *, enabled=True):
        env = dict(CJ_ENV='local', CJ_LOCAL_CONNINFO=CONNINFO, CJ_LOCAL_AUTH_DIR=str(self.auth))
        if enabled: env['CJ_LOCAL_MEMORY_POLICY'] = str(self.policy_path)
        with patch.dict(os.environ, env):
            if not enabled: os.environ.pop('CJ_LOCAL_MEMORY_POLICY', None)
            return app_from_environment()

    def raw(self, slot_kind='preference', **changes):
        value = dict(operation_id='memory-op-' + uuid.uuid4().hex, item_id='memory-item-' + uuid.uuid4().hex,
                     subject='self', slot=self.slots[slot_kind], kind=slot_kind,
                     text='Synthetic ' + slot_kind + ' / 合成声明', extent='long_term', context_id=None,
                     occurred_at='date unknown')
        value.update(changes)
        return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()

    def save(self, client, raw, subject='alice'):
        return client.post('/v1/memories', content=raw,
                           headers={**self.headers(subject), 'Content-Type': 'application/octet-stream'})

    def receipt(self, client, raw, subject='alice'):
        return client.get('/v1/memory-receipts', params={'operation_id': json.loads(raw)['operation_id']},
                          headers=self.headers(subject))

    def counts(self, subject='alice'):
        with self.database.connect(scope_for(ISSUER, subject)) as conn:
            return tuple(conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
                         for table in TABLES[1:])

    def service(self, subject='alice'):
        scope = scope_for(ISSUER, subject)
        return Service(Repository(lambda: self.database.connect(scope), scope,
                                  transaction_binder=lambda conn, cur: conn.bind_scope(cur)))

    def test_committed_original_receipt_reopen_and_canonical_slot(self):
        saved = []
        with TestClient(self.memory_app) as client:
            for kind in ('fact', 'experience', 'preference'):
                raw = self.raw(kind)
                result = self.save(client, raw)
                self.assertEqual(result.status_code, 200, result.text)
                receipt = result.json()['receipt']
                self.assertEqual((receipt['status'], receipt['version']), ('active', 1))
                self.assertEqual(receipt['input_sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(self.receipt(client, raw).json()['receipt'], receipt)
                before = self.counts()
                self.assertEqual(self.save(client, raw).json()['receipt'], receipt)
                self.assertEqual(self.counts(), before)
                self.assertEqual(self.save(client, raw + b' ').status_code, 409)
                self.assertEqual(self.counts(), before)
                saved.append((raw, receipt))
            before = self.counts()
            synonym = self.raw('preference', text='同一 canonical slot 的中文声明')
            self.assertEqual(self.save(client, synonym).status_code, 409)
            self.assertEqual(self.counts(), before)  # no orphan source from the rolled-back attempt
        with TestClient(self.app_from_policy()) as client:
            for raw, receipt in saved:
                detail = client.get('/v1/memory-items', params={'item_id': receipt['item_id']}, headers=self.headers('alice'))
                self.assertEqual(detail.status_code, 200, detail.text)
                item = detail.json()['item']; original = json.loads(raw)
                self.assertEqual(item['command']['text'], original['text'])
                self.assertEqual(item['command']['occurred_at'], original['occurred_at'])
                self.assertEqual(item['command']['source_id'], 'manual-v1:' + hashlib.sha256(raw).hexdigest())
                self.assertEqual((item['version'], item['status'], item['command']['source_version']), (1, 'active', 1))
                self.assertTrue(item['recorded_at'])
                self.assertIsNone(client.get('/v1/memory-items', params={'item_id': receipt['item_id']},
                    headers=self.headers('bob')).json()['item'])
                self.assertIsNone(self.receipt(client, raw, 'bob').json()['receipt'])
            listed = client.get('/v1/memories', params={'limit': 50}, headers=self.headers('alice'))
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertTrue({r['item_id'] for _, r in saved} <= {i['command']['item_id'] for i in listed.json()['items']})
            self.assertEqual(client.get('/v1/memory-groups', headers=self.headers('alice')).status_code, 200)

    def test_candidates_current_scope_and_foreign_context_refusal(self):
        with TestClient(self.memory_app) as client:
            for subject, chat in (('alice', self.chat_a), ('bob', self.chat_b)):
                self.assertEqual(client.put('/v1/conversations', params={'conversation_id': chat},
                                           headers=self.headers(subject)).status_code, 200)
                self.assertEqual(client.get('/v1/memories', params={'limit': 50},
                                            headers=self.headers(subject)).status_code, 200)
            long_raw = self.raw('preference')
            self.assertEqual(self.save(client, long_raw).status_code, 200)
            current_raw = self.raw('preference', extent='current', context_id=self.chat_a, text='Synthetic current override')
            self.assertEqual(self.save(client, current_raw).status_code, 200)
            before = self.counts()
            foreign = self.raw('fact', extent='current', context_id=self.chat_b)
            self.assertEqual(self.save(client, foreign).status_code, 403)
            self.assertEqual(self.counts(), before)
            candidates = []
            for raw in (self.raw('preference', kind='inference'),
                        self.raw('fact', slot=self.slots['ambiguous'])):
                result = self.save(client, raw)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['receipt']['status'], 'candidate')
                candidates.append(result.json()['receipt']['item_id'])
            before = self.counts()
            refused = self.save(client, self.raw('fact', slot=self.slots['blocked']))
            self.assertNotEqual(refused.status_code, 200)
            self.assertEqual(self.counts(), before)
        service = self.service()
        def selected(context): return {i.command.slot: i.command.item_id for i in service.effective('self', context).items}
        self.assertEqual(selected(self.chat_a)[self.slots['preference']], json.loads(current_raw)['item_id'])
        self.assertEqual(selected('other-context')[self.slots['preference']], json.loads(long_raw)['item_id'])
        self.assertFalse(set(candidates) & set(selected(self.chat_a).values()))
        self.assertNotIn(json.loads(long_raw)['item_id'], {i.command.item_id for i in self.service('bob').effective('self').items})

    def test_commit_ack_and_postcommit_authorization_loss_query_original(self):
        original_transaction = Repository.transaction
        with TestClient(self.memory_app) as client:
            raw = self.raw('fact')
            @contextmanager
            def lost_ack(repository):
                with original_transaction(repository) as tx: yield tx
                raise CommitUnknown('synthetic lost ACK after real commit')
            with patch.object(Repository, 'transaction', lost_ack):
                result = self.save(client, raw)
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json()['error']['recovery'], 'reconcile_original')
            self.assertNotIn('receipt', result.json())
            observed = self.receipt(client, raw)
            self.assertEqual(observed.status_code, 200)
            self.assertEqual(observed.json()['receipt']['input_sha256'], hashlib.sha256(raw).hexdigest())
            before = self.counts()
            self.assertEqual(self.save(client, raw).json()['receipt'], observed.json()['receipt'])
            self.assertEqual(self.counts(), before)
            rollback_raw = self.raw('experience')
            @contextmanager
            def before_commit(repository):
                with original_transaction(repository) as tx:
                    yield tx
                    raise Unavailable('synthetic precommit failure')
            with patch.object(Repository, 'transaction', before_commit):
                result = self.save(client, rollback_raw)
            self.assertNotEqual(result.status_code, 200)
            self.assertIsNone(self.receipt(client, rollback_raw).json()['receipt'])
            self.assertEqual(self.counts(), before)
            late_raw = self.raw('experience')
            @contextmanager
            def withdraw_after_commit(repository):
                with original_transaction(repository) as tx: yield tx
                (self.auth/'invited.json').write_text(json.dumps(['bob']))
            try:
                with patch.object(Repository, 'transaction', withdraw_after_commit):
                    result = self.save(client, late_raw)
                self.assertEqual(result.status_code, 503)
                self.assertNotIn('receipt', result.json())
            finally:
                (self.auth/'invited.json').write_text(json.dumps(['alice', 'bob']))
            self.assertEqual(self.receipt(client, late_raw).json()['receipt']['input_sha256'], hashlib.sha256(late_raw).hexdigest())

    def test_runtime_rls_and_transaction_local_scope_never_leak(self):
        with TestClient(self.memory_app) as client:
            for subject in ('alice', 'bob'):
                result = self.save(client, self.raw('preference', text='Synthetic ' + subject), subject)
                self.assertEqual(result.status_code, 200, result.text)
        for subject, other in (('alice', 'bob'), ('bob', 'alice')):
            scope, foreign = scope_for(ISSUER, subject), scope_for(ISSUER, other)
            with self.database.connect(scope) as conn:
                self.assertEqual(conn.execute('SELECT current_user').fetchone()[0], 'cj_m1_runtime')
                for table in TABLES:
                    with self.subTest(subject=subject, table=table):
                        relation = sql.Identifier(table)
                        rows = conn.execute(sql.SQL('SELECT DISTINCT scope FROM {}').format(relation)).fetchall()
                        self.assertEqual(rows, [(scope,)])
                        self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {} WHERE scope=%s').format(relation), (foreign,)).fetchone()[0], 0)
                        flags = conn.execute('SELECT relrowsecurity,relforcerowsecurity,relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) FROM pg_class WHERE oid=%s::regclass', (table,)).fetchone()
                        self.assertEqual(flags, (True, True, False))
                self.assertEqual(conn.execute('UPDATE cj_memory_source SET scope=scope WHERE scope=%s RETURNING scope', (foreign,)).fetchall(), [])
                self.assertEqual(conn.execute('UPDATE cj_memory_scope SET epoch=epoch WHERE scope=%s RETURNING scope', (foreign,)).fetchall(), [])
                conn.rollback()
                for table in TABLES:
                    self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0], 0)
                conn.rollback()
            attempts = [
                ('INSERT INTO cj_memory_scope(scope) VALUES (%s)', (foreign,)),
                ('INSERT INTO cj_memory_source VALUES (%s,%s,1,%s,false,false,false,false,clock_timestamp())', (foreign, 'forbidden', b'{}')),
                ('INSERT INTO cj_memory_item VALUES (%s,%s,1,\'candidate\',\'self\',\'s\',\'long_term\',\'\',\'absent\',1,%s,clock_timestamp())', (foreign, 'forbidden', b'{}')),
                ('INSERT INTO cj_memory_operation VALUES (%s,%s,%s,\'absent\',1,\'candidate\')', (foreign, 'forbidden', b'{}')),
                ('UPDATE cj_memory_item SET status=\'active\' WHERE scope=%s', (foreign,)),
                ('UPDATE cj_memory_operation SET status=\'active\' WHERE scope=%s', (foreign,)),
                ('UPDATE cj_memory_source SET authorized=true WHERE scope=%s', (scope,)),
            ]
            for statement, args in attempts:
                with self.subTest(statement=statement), self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with self.database.connect(scope) as conn: conn.execute(statement, args)
            connection = self.database.connect(scope)
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED'); connection.bind_scope(cursor)
                self.assertGreater(cursor.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0], 0)
            connection.commit()
            self.assertEqual(connection.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0], 0)
            connection.rollback(); connection.close()
            dirty = self.database.connect(scope)
            dirty.execute("SELECT set_config('cj.message_scope',%s,false)", (foreign,)); dirty.commit()
            repository = Repository(lambda: dirty, scope, transaction_binder=lambda c, cur: c.bind_scope(cur))
            with self.assertRaises(CompositionUnavailable):
                Service(repository).list_items()
            self.assertTrue(dirty.closed)

    def test_memory_migration_round_trip_preserves_runtime_data(self):
        # Separate cluster stops at this migration, so later migrations are never
        # rolled back by this historical migration regression.
        sys.path.insert(0, str(ROOT / 'scripts'))
        import migrate
        from pg_suites import cluster
        chain = migrate.load()
        own = next(value for value in chain if value['name'] == 'memory_runtime_rls')
        scope = scope_for(ISSUER, 'migration-fixture')
        with cluster('m226migrate', port=55495, role='cj_memory_migration') as config:
            with psycopg.connect(**config, autocommit=True) as initializer:
                migrate.up(initializer, chain, own['version'])
                runtime = dict(config, user='cj_m1_runtime')
                # Opaque synthetic rows test storage retention only; all business
                # save/consent behavior is tested through signed API above.
                with psycopg.connect(**runtime) as conn:
                    conn.execute("SELECT set_config('cj.message_scope',%s,true)", (scope,))
                    conn.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s)', (scope,))
                    conn.execute("INSERT INTO cj_memory_source VALUES (%s,'source',1,%s,false,false,false,false,clock_timestamp())", (scope, b'synthetic-source'))
                    conn.execute("INSERT INTO cj_memory_item VALUES (%s,'item',1,'candidate','self','slot','long_term','','source',1,%s,clock_timestamp())", (scope, b'synthetic-item'))
                    conn.execute("INSERT INTO cj_memory_operation VALUES (%s,'op',%s,'item',1,'candidate')", (scope, b'synthetic-operation'))
                migrate.down(initializer, chain, own['version'] - 1)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with psycopg.connect(**runtime) as conn:
                        conn.execute("SELECT set_config('cj.message_scope',%s,true)", (scope,))
                        conn.execute('SELECT original_input FROM cj_memory_operation')
                migrate.up(initializer, chain, own['version'])
                with psycopg.connect(**runtime) as conn:
                    conn.execute("SELECT set_config('cj.message_scope',%s,true)", (scope,))
                    self.assertEqual(conn.execute('SELECT original_input FROM cj_memory_operation').fetchone()[0], b'synthetic-operation')
                    self.assertEqual(conn.execute('SELECT original_input FROM cj_memory_item').fetchone()[0], b'synthetic-item')
                    self.assertEqual(conn.execute('SELECT approved_input FROM cj_memory_source').fetchone()[0], b'synthetic-source')

    def test_disabled_policy_and_expiry_do_not_fake_current_memory(self):
        with TestClient(self.app_from_policy(enabled=False)) as client:
            self.assertEqual(self.save(client, self.raw('fact')).status_code, 503)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=8)
        self.policy['expires_at'] = expiry.isoformat(); self.write_policy()
        with TestClient(self.app_from_policy()) as client:
            raw = self.raw('fact')
            result = self.save(client, raw)
            self.assertEqual(result.status_code, 200, result.text)
            receipt = result.json()['receipt']
            old = self.service().effective('self')
            self.assertIn(receipt['item_id'], {item.command.item_id for item in old.items})
            time.sleep(max(0, expiry.timestamp() - time.time()) + .15)
            current = self.service().effective('self')
            self.assertEqual(current.epoch, old.epoch)
            self.assertNotIn(receipt['item_id'], {item.command.item_id for item in current.items})
            with self.service().repository.transaction() as tx, self.assertRaises(Conflict):
                tx.require_current(old, 'self')
            self.assertEqual(self.receipt(client, raw).json()['receipt'], receipt)
            self.assertEqual(self.save(client, raw).json()['receipt'], receipt)  # history only, no expiry renewal
            self.assertNotEqual(self.save(client, self.raw('experience')).status_code, 200)
