"""Explicit isolated PG harness. Never consult an environment DSN. No automatic cleanup."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
import uuid
import psycopg
from cj_message.domain import (Service, CommitUnknown, InputConflict, ResyncRequired,
                               SequenceConflict, Command, InvalidInput, Unavailable)
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


def wire(mid='m1', text='你好', cid='chat', sequence=0, generation='g1'):
    return json.dumps(dict(version='MESSAGE-send.1', conversation_id=cid, message_id=mid,
                           text=text, trip_id=None, creation_intent='none',
                           expected_generation=generation, expected_sequence=sequence), ensure_ascii=False).encode()


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
            except SequenceConflict: return ('sequence_conflict', None)
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

    def test_same_head_competitors_accept_exactly_one_and_stale_never_accepts(self):
        results = self.race([wire('a'), wire('b')])
        self.assertEqual(sorted(x[0] for x in results), ['accepted', 'sequence_conflict'])
        winner = next(value for kind, value in results if kind == 'accepted')
        self.assertEqual(winner.sequence, 1)
        for mid in ('late-1', 'late-2', 'late-3'):
            with self.assertRaises(SequenceConflict): self.make().receive(wire(mid))
        self.assertEqual(self.counts(), (1,1))
        self.assertEqual(self.service.send_status('chat').head.last_sequence, 1)

    def test_repeated_original_status_and_single_delivery(self):
        receipt = self.service.receive(wire())
        for _ in range(5):
            self.assertEqual(self.make().receive(wire()), receipt)
            status = self.make().send_status('chat', 'm1')
            self.assertEqual(status.stored.receipt, receipt)
            self.assertEqual(status.head.last_sequence, 1)
        self.assertEqual(self.counts(), (1,1))
        self.assertEqual(self.service.pending(), [receipt])

    def test_status_and_receive_are_serialized_in_both_orders(self):
        for reader_first in (True, False):
            with self.subTest(reader_first=reader_first):
                if not reader_first:
                    self.setUp()
                entered, release, connected = threading.Event(), threading.Event(), threading.Event()
                waiting_pid = []
                prefix = 'SELECT raw_input' if reader_first else 'INSERT INTO cj_message_delivery'
                class PausedConnection(Proxy):
                    def cursor(self):
                        actual = self.c.cursor()
                        class Cursor:
                            def execute(self, sql, args=()):
                                actual.execute(sql, args)
                                if sql.startswith(prefix):
                                    entered.set()
                                    if not release.wait(5):
                                        raise AssertionError('test did not release transaction')
                            def __getattr__(self, name): return getattr(actual, name)
                        return Cursor()
                def waiting_connect():
                    c = connect()
                    waiting_pid.append(c.info.backend_pid)
                    connected.set()
                    return c
                first = self.make(lambda: PausedConnection(connect()))
                second = self.make(waiting_connect)
                def read(service): return service.send_status('chat', 'm1')
                def write(service): return service.receive(wire())
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    first_future = pool.submit(read if reader_first else write, first)
                    try:
                        self.assertTrue(entered.wait(5))
                        second_future = pool.submit(write if reader_first else read, second)
                        self.assertTrue(connected.wait(5))
                        deadline = time.monotonic() + 3
                        blocked = False
                        with connect() as c:
                            while time.monotonic() < deadline:
                                blocked = bool(c.execute('SELECT pg_blocking_pids(%s)', (waiting_pid[0],)).fetchone()[0])
                                if blocked: break
                                time.sleep(.01)
                        self.assertTrue(blocked, 'competing operation must wait on the scope lock')
                    finally:
                        release.set()
                    first_result, second_result = first_future.result(), second_future.result()
                status = first_result if reader_first else second_result
                if reader_first:
                    self.assertIsNone(status.stored)
                    self.assertEqual(status.head.last_sequence, 0)
                else:
                    self.assertEqual(status.stored.receipt, first_result)
                    self.assertEqual(status.head.last_sequence, 1)
                self.assertEqual(self.counts(), (1,1))

    def test_foreign_status_is_indistinguishable_from_absent(self):
        self.service.receive(wire())
        other_scope = self.scope + '-B'
        with connect() as c:
            c.execute('INSERT INTO cj_message_scope(scope) VALUES (%s)', (other_scope,))
        other = Service(Repository(connect, other_scope), lambda: 'unused')
        self.assertEqual(other.send_status('chat', 'm1'), other.send_status('absent', 'absent'))
        self.assertIsNone(other.query('m1'))
        self.assertEqual(other.conversations(), ([], None))
        with self.assertRaises(Unavailable): other.message_history('chat')
        self.assertIsNone(self.service.send_status('another-chat', 'm1').stored)

    def test_closed_head_keeps_original_receipt_but_never_reactivates(self):
        receipt = self.service.receive(wire())
        with connect() as c:
            c.execute('UPDATE cj_message_chat SET active=false WHERE scope=%s', (self.scope,))
        self.assertEqual(self.service.receive(wire()), receipt)
        status = self.service.send_status('chat', 'm1')
        self.assertEqual(status.stored.receipt, receipt)
        self.assertIsNone(status.head)
        with self.assertRaises(Unavailable): self.service.receive(wire('new', sequence=1))
        with self.assertRaises(psycopg.errors.RaiseException):
            with connect() as c:
                c.execute('UPDATE cj_message_chat SET active=true WHERE scope=%s', (self.scope,))
        self.assertIsNone(self.service.send_status('chat').head)

    def test_legacy_stored_bytes_readable_but_never_writeable(self):
        self.service.receive(wire())
        self.service.receive(wire('m2', sequence=1))
        legacy = json.loads(wire())
        legacy['version'] = 'MESSAGE-draft.1'
        del legacy['expected_generation'], legacy['expected_sequence']
        raw = json.dumps(legacy, ensure_ascii=False).encode()
        with connect() as c:
            c.execute('UPDATE cj_message_receipt SET raw_input=%s,input_sha256=%s WHERE scope=%s AND message_id=%s',
                      (raw, hashlib.sha256(raw).hexdigest(), self.scope, 'm1'))
        self.assertEqual(self.service.query('m1').raw, raw)
        self.assertEqual(self.service.send_status('chat', 'm1').stored.raw, raw)
        history, _ = self.service.message_history('chat')
        self.assertEqual([row.original_utf8 for row in history], [raw, wire('m2', sequence=1)])
        self.assertEqual(Command.parse_stored(raw).message_id, 'm1')
        with self.assertRaises(InvalidInput): self.service.receive(raw)
        self.assertEqual(self.counts(), (2,2))

    def test_page_append_epoch_and_recreated_generation(self):
        self.service.receive(wire()); self.service.receive(wire('m2', sequence=1))
        _, cursor = self.service.page('chat',limit=1)
        self.service.receive(wire('m3', sequence=2))
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
            c.execute((ROOT.parent/'migrations/0012_message_active_one_way.sql').read_text())
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
