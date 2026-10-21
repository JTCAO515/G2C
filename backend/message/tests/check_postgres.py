"""Explicit isolated PG harness. Never consult an environment DSN. No automatic cleanup."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import unittest
import uuid
import psycopg
from cj_message.domain import Service, CommitUnknown, InputConflict, ResyncRequired
from cj_message.postgres import Repository

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local-pg-01'
SOCKET = PRIVATE / 's'


def connect():
    return psycopg.connect(host=str(SOCKET), port=55439, user='cj009', dbname='postgres',
                           connect_timeout=5, options='-c statement_timeout=10000 -c lock_timeout=5000')


def guard():
    with connect() as c:
        row = c.execute("SELECT current_setting('data_directory'), current_setting('listen_addresses'), current_user, version()").fetchone()
        assert Path(row[0]).resolve() == (PRIVATE/'data').resolve(), 'unexpected cluster'
        assert row[1] == '' and row[2] == 'cj009', 'unexpected network/user'
        return row


def wire(mid='m1', text='你好', cid='chat'):
    return json.dumps(dict(version='MESSAGE-draft.1', conversation_id=cid, message_id=mid,
                           text=text, trip_id=None, creation_intent='none'), ensure_ascii=False).encode()


class Proxy:
    """Real PG connection with explicit post-operation fault injection."""
    def __init__(self, connection, commit_ack=False, delivery=False):
        self.c = connection; self.commit_ack = commit_ack; self.delivery = delivery
    @property
    def autocommit(self): return self.c.autocommit
    def cursor(self):
        actual = self.c.cursor(); parent = self
        class Cursor:
            def execute(self, sql, args=()):
                actual.execute(sql, args)
                if parent.delivery and sql.startswith('INSERT INTO cj_message_delivery'):
                    raise RuntimeError('injected after real delivery INSERT before COMMIT')
            def __getattr__(self, key): return getattr(actual, key)
        return Cursor()
    def commit(self):
        self.c.commit()
        if self.commit_ack: raise OSError('injected response loss AFTER actual PG commit')
    def rollback(self): self.c.rollback()
    def close(self): self.c.close()


class PostgresTests(unittest.TestCase):
    def setUp(self):
        guard()
        self.scope = 'pg-test-' + uuid.uuid4().hex
        with connect() as c:
            c.execute('INSERT INTO cj_message_scope VALUES (%s)', (self.scope,))
            c.execute('INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,%s,%s,0)', (self.scope,'chat','g1'))
        self.service = self.make()
    def make(self, factory=connect):
        return Service(Repository(factory, self.scope), lambda:uuid.uuid4().hex)
    def counts(self):
        with connect() as c:
            return tuple(c.execute('SELECT count(*) FROM '+table+' WHERE scope=%s',(self.scope,)).fetchone()[0]
                         for table in ('cj_message_receipt','cj_message_delivery'))

    def test_real_receipt_delivery_commit_and_exact_duplicate(self):
        r = self.service.receive(wire())
        self.assertEqual(self.counts(), (1,1))
        self.assertEqual(self.make().query('m1').receipt, r)
        self.assertEqual(self.make().receive(wire()), r)
        self.assertEqual(self.make().pending(), [r])
        self.assertEqual(self.make().query('m1').raw, wire())

    def test_real_transaction_rollback_after_both_inserts(self):
        broken = self.make(lambda:Proxy(connect(), delivery=True))
        with self.assertRaises(RuntimeError): broken.receive(wire())
        self.assertEqual(self.counts(), (0,0))
        self.assertIsNone(self.service.query('m1'))
        self.assertEqual(self.service.receive(wire()).sequence, 1)

    def test_actual_commit_then_injected_ack_loss_recovers_original(self):
        uncertain = self.make(lambda:Proxy(connect(), commit_ack=True))
        with self.assertRaises(CommitUnknown): uncertain.receive(wire())
        r = self.service.query('m1').receipt
        self.assertEqual(self.service.receive(wire()), r)
        self.assertEqual(self.service.pending(), [r])
        self.assertEqual(self.counts(), (1,1))
        # Retained for post-restart readback in a separate interpreter.
        (PRIVATE/'restart-receipt.json').write_text(json.dumps({'scope':self.scope,'run_id':r.run_id}))

    def race(self, inputs):
        barrier = threading.Barrier(2)
        def receive(raw):
            barrier.wait(timeout=5)
            try: return ('accepted', self.make().receive(raw))
            except InputConflict: return ('conflict', None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(receive, inputs))

    def test_concurrent_same_id_different_bytes_one_conflict(self):
        results = self.race([wire(text='first'),wire(text='second')])
        self.assertEqual(sorted(x[0] for x in results), ['accepted','conflict'])
        self.assertEqual(self.counts(), (1,1))

    def test_concurrent_duplicate_returns_original_receipt(self):
        results = self.race([wire(),wire()])
        self.assertEqual([x[0] for x in results], ['accepted','accepted'])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(self.counts(), (1,1))

    def test_page_append_epoch_and_recreated_generation(self):
        self.service.receive(wire()); self.service.receive(wire('m2'))
        _, cursor = self.service.page('chat',limit=1)
        self.service.receive(wire('m3'))
        self.assertEqual([r.message_id for r in self.service.page('chat',cursor)[0]],['m2'])
        with connect() as c:
            c.execute('UPDATE cj_message_chat SET epoch=epoch+1 WHERE scope=%s',(self.scope,))
        with self.assertRaises(ResyncRequired): self.service.page('chat',cursor)
        _, current = self.service.page('chat',limit=1)
        with connect() as c:
            c.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(self.scope,))
            # Only this test's new synthetic rows, not a production cleanup implementation.
            for table in ('cj_message_delivery','cj_message_receipt','cj_message_chat'):
                c.execute('DELETE FROM '+table+' WHERE scope=%s',(self.scope,))
            c.execute('INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,%s,%s,0)',(self.scope,'chat','g2'))
        with self.assertRaises(ResyncRequired): self.service.page('chat',current)
        self.assertEqual(self.service.page('chat'),([],None))


if __name__ == '__main__':
    # Refuse inherited libpq configuration rather than using any unknown service/DSN.
    assert not any(k.startswith('PG') for k in os.environ), 'run with clean environment'
    info = guard()
    if sys.argv[1:] == ['setup']:
        sql=(ROOT/'sql/candidate.sql').read_bytes()
        with connect() as c:
            assert c.execute("SELECT to_regclass('cj_message_scope')").fetchone()[0] is None
            c.execute(sql.decode())
        print(json.dumps({'server':info, 'sql_sha256':hashlib.sha256(sql).hexdigest(),
                          'driver':psycopg.__version__, 'python':sys.version},indent=2))
    elif sys.argv[1:] == ['restart-check']:
        saved=json.loads((PRIVATE/'restart-receipt.json').read_text())
        service=Service(Repository(connect,saved['scope']),lambda: (_ for _ in ()).throw(AssertionError('no new run')))
        receipt=service.query('m1').receipt
        assert receipt.run_id==saved['run_id'] and service.pending()==[receipt]
        assert service.receive(wire())==receipt
        print('PASS real PG restart readback: original receipt/run/pending, no new run')
    else:
        unittest.main(verbosity=2)
