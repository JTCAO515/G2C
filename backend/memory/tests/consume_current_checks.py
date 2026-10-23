"""Focused held-lock consumer tests; always a new task-private empty PG17 cluster."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'auth'), str(ROOT / 'tests')]
from cj_auth.interfaces import TrustedPrincipal
from cj_memory.domain import Service, Conflict, InvalidInput
from cj_memory.operation import OperationWithheld
from cj_memory.postgres import Repository
from pg_checks import command

PG = Path('/opt/homebrew/opt/postgresql@17/bin')
ENV = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
PRIVATE = Path(tempfile.mkdtemp(prefix='consume-', dir=ROOT / '.local'))
SOCKET = Path(tempfile.mkdtemp(prefix='cj011-consume-', dir='/tmp'))
PASSFILE = PRIVATE / 'empty.pgpass'
PASSFILE.touch(mode=0o600)
PORT = 56116


def connect():
    return psycopg.connect(host=str(SOCKET), port=PORT, user='cj011_consume',
                          dbname='postgres', passfile=str(PASSFILE),
                          password='', connect_timeout=3)


def run_pg(*args):
    return subprocess.run([str(PG / args[0]), *args[1:]], env=ENV,
                          check=True, capture_output=True, text=True, timeout=15)


class ObservedRepository(Repository):
    # Test instrumentation ONLY: production consumer gets no tx/connection API.
    @contextmanager
    def transaction(self):
        with super().transaction() as tx:
            self.current_tx = tx
            try:
                yield tx
            finally:
                self.current_tx = None


class Checks(unittest.TestCase):
    def setUp(self):
        self.scope = self._testMethodName
        with connect() as conn:
            conn.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s)', (self.scope,))
        self.repository = ObservedRepository(connect, self.scope)
        self.service = Service(self.repository)
        self.principal = TrustedPrincipal('synthetic', self.scope, 'test', 1, 1, 9999999999)

    def guard(self, stage):
        return self.principal, self.scope

    def seed(self, name, *, slot=None, subject='self', kind='preference', extent='long_term', context_id=None):
        raw = command(name, slot=slot or name, subject=subject, kind=kind,
                      extent=extent, context_id=context_id)
        with connect() as conn:
            conn.execute("INSERT INTO cj_memory_source VALUES (%s,%s,1,%s,true,true,true,true,clock_timestamp()+interval '1 hour')",
                         (self.scope, 'source-' + name, raw))
        return self.service.save(raw)

    def consume(self, callback, *, subject='self', context_id=None, bound=4096, guard=None):
        return self.service.with_operation(guard or self.guard, lambda ctx:
            ctx.consume_current(subject, context_id, callback, max_result_bytes=bound))

    def test_01_canonical_selection_matches_effective(self):
        self.seed('long', slot='pace')
        self.seed('current', slot='pace', extent='current', context_id='chat-1')
        self.seed('companion', subject='companion')
        self.seed('candidate', kind='inference')
        expected = self.service.effective('self', 'chat-1')
        def project(view):
            self.assertEqual(view.items, expected.items)
            self.assertEqual(view.epoch, expected.epoch)
            return json.dumps([i.command.item_id for i in view.items]).encode()
        self.assertEqual(json.loads(self.consume(project, context_id='chat-1')), ['item-current'])
        self.assertEqual(json.loads(self.consume(lambda v: json.dumps([i.command.item_id for i in v.items]).encode())), ['item-long'])

    def test_02_scope_lock_blocks_disable_until_consumer_finishes(self):
        self.seed('lock-item')
        started = threading.Event()
        pids = queue.Queue()
        def disable():
            with connect() as conn:
                pids.put(conn.info.backend_pid)
                started.set()
                conn.execute('SELECT epoch FROM cj_memory_scope WHERE scope=%s FOR UPDATE', (self.scope,))
                conn.execute("UPDATE cj_memory_item SET status='disabled',version=version+1 WHERE scope=%s", (self.scope,))
                conn.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s', (self.scope,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = None
            def consumer(view):
                nonlocal future
                future = pool.submit(disable)
                self.assertTrue(started.wait(2))
                writer_pid = pids.get(timeout=2)
                deadline = time.monotonic() + 2
                blockers = []
                while time.monotonic() < deadline:
                    with connect() as conn:
                        blockers = conn.execute('SELECT pg_blocking_pids(%s)', (writer_pid,)).fetchone()[0]
                    if blockers:
                        break
                    time.sleep(0.01)
                self.assertTrue(blockers, 'writer must actually wait on held scope row')
                self.assertFalse(future.done())
                self.assertEqual(view.items[0].command.item_id, 'item-lock-item')
                return b'current-before-disable'
            self.assertEqual(self.consume(consumer), b'current-before-disable')
            future.result(timeout=3)
        self.assertEqual(self.consume(lambda v: json.dumps(len(v.items)).encode()), b'0')

    def test_03_withdrawal_committed_before_selection_is_excluded(self):
        self.seed('withdraw-item')
        held, release, consumer_started = threading.Event(), threading.Event(), threading.Event()
        def withdraw():
            with connect() as conn:
                conn.execute('SELECT epoch FROM cj_memory_scope WHERE scope=%s FOR UPDATE', (self.scope,))
                held.set()
                if not release.wait(3):
                    raise RuntimeError('test release missing')
                conn.execute('UPDATE cj_memory_source SET active=false,version=version+1 WHERE scope=%s', (self.scope,))
                conn.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s', (self.scope,))
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(withdraw)
            self.assertTrue(held.wait(2))
            def consume_after_lock():
                consumer_started.set()
                return self.consume(lambda v: json.dumps(len(v.items)).encode())
            reader = pool.submit(consume_after_lock)
            self.assertTrue(consumer_started.wait(2))
            self.assertFalse(reader.done())
            release.set()
            writer.result(timeout=3)
            self.assertEqual(reader.result(timeout=3), b'0')

    def test_04_callback_item_source_epoch_fences(self):
        self.seed('fence-item')
        mutations = [
            "UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s",
            "UPDATE cj_memory_item SET version=version+1 WHERE scope=%s",
            "UPDATE cj_memory_item SET status='disabled',version=version+1 WHERE scope=%s",
            "UPDATE cj_memory_source SET active=false WHERE scope=%s",
            "UPDATE cj_memory_source SET version=version+1 WHERE scope=%s",
        ]
        for sql in mutations:
            def callback(view):
                self.repository.current_tx.cur.execute(sql, (self.scope,))
                return b'must-not-escape'
            with self.assertRaises(Conflict):
                self.consume(callback)
            # Same-transaction mutation rolled back; no fixture reset needed.
            self.assertEqual(self.service.detail('item-fence-item').version, 1)
            self.assertEqual(len(self.service.effective('self').items), 1)

    def test_05_source_expiry_during_callback(self):
        self.seed('expiry-item')
        def callback(view):
            # Set a short deadline in this instrumented SAME transaction, then let
            # wall time pass; no second writer or permission-changing API is exposed.
            self.repository.current_tx.cur.execute("UPDATE cj_memory_source SET expires_at=clock_timestamp()+interval '40 milliseconds' WHERE scope=%s", (self.scope,))
            time.sleep(0.08)
            return b'expired'
        with self.assertRaises(Conflict):
            self.consume(callback)

    def test_06_after_fresh_precommit_guard_rechecks_data(self):
        self.seed('after-guard')
        def guard(stage):
            if stage == 'precommit':
                self.repository.current_tx.cur.execute('UPDATE cj_memory_item SET version=version+1 WHERE scope=%s', (self.scope,))
            return self.guard(stage)
        with self.assertRaises(Conflict):
            self.consume(lambda v: b'old', guard=guard)
        self.assertEqual(self.service.detail('item-after-guard').version, 1)

    def test_07_materialized_bytes_and_bound_only(self):
        async def deferred():
            return b'late'
        def closing_generator():
            try:
                yield b'late'
            finally:
                raise asyncio.CancelledError('cancel during close')
        generator = closing_generator()
        next(generator)
        factories = [lambda v: v, lambda v: iter([1]), lambda v: deferred(),
                     lambda v: (x for x in [1]), lambda v: generator,
                     lambda v: b'x' * 17, lambda v: bytearray(b'x')]
        for factory in factories:
            with self.assertRaises((InvalidInput, OperationWithheld)):
                self.consume(factory, bound=16)
        self.assertEqual(self.consume(lambda v: b'x' * 16, bound=16), b'x' * 16)

    def test_08_lifetime_thread_and_explicit_close(self):
        captured = []
        def callback(view):
            captured.append(view)
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(RuntimeError):
                    pool.submit(lambda: view.items).result(timeout=2)
            return b'ok'
        self.consume(callback)
        with self.assertRaises(RuntimeError):
            _ = captured[0].items
        with self.assertRaises(RuntimeError):
            self.consume(lambda v: (v.close(), b'closed')[1])
        with self.assertRaises(RuntimeError):
            self.consume(lambda v: captured[0].items)

    def test_08b_view_expired_before_postcallback_guard(self):
        captured = []
        def callback(view):
            captured.append(view)
            return b'ok'
        def guard(stage):
            if stage == 'precommit':
                with self.assertRaises(RuntimeError):
                    _ = captured[0].items
            return self.guard(stage)
        self.assertEqual(self.consume(callback, guard=guard), b'ok')

    def test_09_cancellation_and_swallowed_consumer_failure_sticky(self):
        for interruption in (asyncio.CancelledError, KeyboardInterrupt):
            def fail(view):
                raise interruption()
            def outer(ctx):
                try:
                    ctx.consume_current('self', None, fail, max_result_bytes=16)
                except BaseException:
                    pass
                return b'pretend-success'
            with self.assertRaises(OperationWithheld) as caught:
                self.service.with_operation(self.guard, outer)
            self.assertFalse(caught.exception.commit_possible)
        def swallowed_bound(ctx):
            try:
                ctx.consume_current('self', None, lambda v: b'overflow', max_result_bytes=1)
            except InvalidInput:
                pass
            return b'pretend-success'
        with self.assertRaises(OperationWithheld):
            self.service.with_operation(self.guard, swallowed_bound)

    def test_10_final_callback_identity_or_repository_replacement(self):
        original_repository = self.repository
        for mode in ('identity', 'repository'):
            self.service.repository = original_repository
            changed = False
            def guard(stage):
                if changed and mode == 'identity':
                    return TrustedPrincipal('synthetic', 'replacement', 'test', 1, 1, 9999999999), self.scope
                return self.guard(stage)
            def outer(ctx):
                nonlocal changed
                result = ctx.consume_current('self', None, lambda v: b'old', max_result_bytes=16)
                changed = True
                if mode == 'repository':
                    self.service.repository = Repository(connect, self.scope)
                return result
            with self.assertRaises(OperationWithheld):
                self.service.with_operation(guard, outer)
        self.service.repository = original_repository

    def test_11_reentrant_operation_rejected_without_second_connection(self):
        def outer(ctx):
            return ctx.consume_current('self', None, lambda v: ctx.groups(), max_result_bytes=16)
        with self.assertRaises(RuntimeError):
            self.service.with_operation(self.guard, outer)

    def test_12_prior_save_failure_keeps_original_reconcile(self):
        raw = command('prior-save', kind='inference')
        with connect() as conn:
            conn.execute("INSERT INTO cj_memory_source VALUES (%s,%s,1,%s,true,false,false,true,clock_timestamp()+interval '1 hour')", (self.scope, 'source-prior-save', raw))
        def outer(ctx):
            ctx.save(raw)
            return ctx.consume_current('self', None, lambda v: b'overflow', max_result_bytes=1)
        with self.assertRaises(OperationWithheld) as caught:
            self.service.with_operation(self.guard, outer)
        self.assertTrue(caught.exception.commit_possible)
        self.assertEqual(caught.exception.operation_id, 'op-prior-save')
        self.assertIsNotNone(self.service.query('op-prior-save'))


def main():
    started = False
    result = None
    try:
        run_pg('initdb', '-D', str(PRIVATE / 'pg'), '-U', 'cj011_consume', '--auth=trust', '--no-locale', '--encoding=UTF8')
        run_pg('pg_ctl', '-D', str(PRIVATE / 'pg'), '-l', str(PRIVATE / 'server.log'), '-o', f"-k {SOCKET} -p {PORT} -c listen_addresses=''", 'start')
        started = True
        with connect() as conn:
            conn.execute((ROOT / 'schema.sql').read_text())
            identity = conn.execute("SELECT current_user,current_database(),current_setting('listen_addresses'),current_setting('port')").fetchone()
        with (PRIVATE / 'test.log').open('w') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
        print((PRIVATE / 'test.log').read_text())
        print(json.dumps({'private': str(PRIVATE), 'socket': str(SOCKET), 'identity': identity,
                          'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors)}))
    finally:
        if started:
            run_pg('pg_ctl', '-D', str(PRIVATE / 'pg'), 'stop', '-m', 'fast')
        print('Private PG stopped; cluster and evidence retained:', PRIVATE)
    return 0 if result is not None and result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
