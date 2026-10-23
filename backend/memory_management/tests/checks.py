"""Real PG lifecycle checks; receives only a new private fixture config file."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import unittest

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'memory')]
from cj_memory.domain import Command, Conflict, InvalidInput, Service as Memory, Unavailable
from cj_memory.postgres import Repository as MemoryRepository
from cj_memory_management.domain import Action
from cj_memory_management.postgres import Repository
from cj_memory_management.service import ActionUnknown, Service

CONFIG = json.loads(Path(sys.argv.pop(1)).read_text())
for key in tuple(os.environ):
    if key.startswith('PG'):
        del os.environ[key]


def connect():
    return psycopg.connect(**CONFIG)


def memory(scope='A', factory=connect):
    return Memory(MemoryRepository(factory, scope))


def management(scope='A', factory=connect):
    return Service(Repository(factory, scope))


def seed(name, *, scope='A', **changes):
    obj = dict(operation_id='save-' + name, item_id=name, subject='self',
               slot=name, kind='preference', text='不吃辣 / no spicy food',
               extent='long_term', context_id=None, source_id='source-' + name,
               source_version=1, occurred_at='reported; exact date unknown')
    obj.update(changes)
    raw = json.dumps(obj, ensure_ascii=False).encode()
    with connect() as conn:
        conn.execute('''INSERT INTO cj_memory_source VALUES
            (%s,%s,1,%s,true,true,true,true,clock_timestamp()+interval '1 hour')''',
                     (scope, obj['source_id'], raw))
    memory(scope).save(raw)
    return raw


def action(name, operation='pause', version=1, source_version=1, aid=None):
    return json.dumps(dict(action_id=aid or operation + '-' + name,
                           operation=operation, item_id=name,
                           expected_version=version,
                           expected_source_version=source_version),
                      ensure_ascii=False, indent=2).encode() + b'\n'


def ids(scope='A', context=None, subject='self'):
    return {i.command.item_id for i in memory(scope).effective(subject, context).items}


def epoch(scope='A'):
    with connect() as conn:
        return conn.execute('SELECT epoch FROM cj_memory_scope WHERE scope=%s',
                            (scope,)).fetchone()[0]


class Checks(unittest.TestCase):
    def test_01_pause_resume_current_reads_and_provenance(self):
        for kind in ('fact', 'experience', 'preference'):
            name = 'k-' + kind
            original = seed(name, kind=kind)
            before = memory().detail(name)
            e = epoch()
            paused = management().apply(action(name))
            self.assertEqual((paused.version, paused.status), (2, 'disabled'))
            self.assertEqual(epoch(), e + 1)
            self.assertNotIn(name, ids())
            self.assertEqual(memory().detail(name).command.raw, original)
            resumed = management().apply(action(name, 'resume', 2))
            self.assertEqual((resumed.version, resumed.status), (3, 'active'))
            self.assertEqual(epoch(), e + 2)
            self.assertIn(name, ids())
            after = memory().detail(name)
            self.assertEqual(after.command, before.command)
            self.assertEqual(after.recorded_at, before.recorded_at)
            self.assertEqual(memory().query('save-' + name).version, 1)
            self.assertIn(name, {i.command.item_id for i in memory().list_items()})

    def test_02_two_writers_same_version_only_one_commits(self):
        seed('race')
        barrier = threading.Barrier(8)
        start = epoch()
        def write(n):
            barrier.wait(timeout=5)
            try:
                return management().apply(action('race', aid='race-' + str(n)))
            except Conflict:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(write, range(8)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(memory().detail('race').version, 2)
        self.assertEqual(epoch(), start + 1)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM cj_memory_management_action WHERE item_id='race'").fetchone()[0], 1)

    def test_03_original_bytes_replay_and_changed_bytes_conflict(self):
        seed('replay')
        raw = action('replay')
        receipt = management().apply(raw)
        e = epoch()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: management().apply(raw), range(8)))
        self.assertEqual(set(results), {receipt})
        self.assertEqual(epoch(), e)
        self.assertEqual(receipt.input_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt, management().query('pause-replay'))
        with self.assertRaises(Conflict):
            management().apply(raw + b' ')
        management().apply(action('replay', 'resume', 2))
        # The original receipt is historical; replay cannot disable the new version.
        self.assertEqual(management().apply(raw), receipt)
        self.assertEqual(memory().detail('replay').version, 3)
        self.assertIn('replay', ids())

    def test_04_stale_item_source_and_old_context_rejected(self):
        seed('stale')
        context = memory().effective('self')
        management().apply(action('stale'))
        with self.assertRaises(Conflict):
            management().apply(action('stale', aid='stale-new-id'))
        with self.assertRaises(Conflict):
            with MemoryRepository(connect, 'A').transaction() as tx:
                tx.require_current(context, 'self')
        with connect() as conn:
            conn.execute("SELECT epoch FROM cj_memory_scope WHERE scope='A' FOR UPDATE")
            conn.execute("UPDATE cj_memory_source SET version=2 WHERE source_id='source-stale' AND scope='A'")
            conn.execute("UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope='A'")
        for expected in (1, 2):
            with self.assertRaises(Conflict):
                management().apply(action('stale', 'resume', 2, expected))
        self.assertNotIn('stale', ids())

    def test_05_scope_isolation_with_identical_item_and_action_ids(self):
        seed('isolation', scope='A')
        seed('isolation', scope='B', text='另一个账号 / other user')
        b_epoch = epoch('B')
        raw = action('isolation')
        management('A').apply(raw)
        self.assertIsNone(management('B').query('pause-isolation'))
        self.assertEqual(epoch('B'), b_epoch)
        self.assertIn('isolation', ids('B'))
        self.assertNotIn('isolation', ids('A'))
        management('B').apply(raw)
        self.assertEqual(memory('B').detail('isolation').version, 2)
        seed('only-A')
        with self.assertRaises(Unavailable):
            management('B').apply(action('only-A'))
        with self.assertRaises(Unavailable):
            management('B').apply(action('not-present'))

    def test_06_resume_never_renews_invalid_or_expired_source(self):
        fields = {'authorized': 'false', 'confirmed': 'false',
                  'semantic_resolved': 'false', 'active': 'false',
                  'expires_at': "clock_timestamp()-interval '1 second'"}
        for field, value in fields.items():
            name = 'invalid-' + field
            seed(name)
            management().apply(action(name))
            with connect() as conn:
                conn.execute("SELECT epoch FROM cj_memory_scope WHERE scope='A' FOR UPDATE")
                # Only test-owned field names/constants; never input-derived SQL.
                conn.execute('UPDATE cj_memory_source SET ' + field + '=' + value + ' WHERE scope=%s AND source_id=%s', ('A', 'source-' + name))
                conn.execute("UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope='A'")
            e = epoch()
            with self.assertRaises(Unavailable):
                management().apply(action(name, 'resume', 2))
            self.assertEqual(memory().detail(name).status, 'disabled')
            self.assertEqual(epoch(), e)
            self.assertIsNone(management().query('resume-' + name))
            self.assertNotIn(name, ids())

    def test_07_candidate_withdrawn_and_foreign_disabled_never_promoted(self):
        seed('candidate', kind='inference')
        with self.assertRaises(Conflict):
            management().apply(action('candidate'))
        for name, status in [('foreign-disabled', 'disabled'), ('withdrawn', 'withdrawn')]:
            seed(name)
            with connect() as conn:
                conn.execute("SELECT epoch FROM cj_memory_scope WHERE scope='A' FOR UPDATE")
                conn.execute('UPDATE cj_memory_item SET status=%s,version=2 WHERE scope=%s AND item_id=%s', (status, 'A', name))
                conn.execute("UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope='A'")
            with self.assertRaises((Unavailable, Conflict)):
                management().apply(action(name, 'resume', 2))
            self.assertNotIn(name, ids())

    def test_08_resume_slot_collision_does_not_overwrite_new_save(self):
        seed('slot-old', slot='canonical-slot')
        management().apply(action('slot-old'))
        seed('slot-new', slot='canonical-slot', text='New fact')
        e = epoch()
        with self.assertRaises(Conflict):
            management().apply(action('slot-old', 'resume', 2))
        self.assertEqual(epoch(), e)
        self.assertIn('slot-new', ids())
        self.assertNotIn('slot-old', ids())
        self.assertIsNone(management().query('resume-slot-old'))

    def test_09_commit_ack_unknown_and_cancellation_preserve_original_action(self):
        for failure in (OSError, asyncio.CancelledError, KeyboardInterrupt):
            for committed in (True, False):
                name = 'ack-' + failure.__name__ + str(committed)
                seed(name)
                class Fault:
                    def __init__(self):
                        self.conn = connect()
                    def __getattr__(self, key):
                        return getattr(self.conn, key)
                    def commit(self):
                        if committed:
                            self.conn.commit()
                        raise failure('synthetic commit ACK fault')
                with self.assertRaises(ActionUnknown) as caught:
                    management(factory=Fault).apply(action(name))
                self.assertEqual(caught.exception.action_id, 'pause-' + name)
                self.assertTrue(caught.exception.commit_possible)
                self.assertEqual(caught.exception.recovery, 'reconcile_original')
                receipt = management().query(caught.exception.action_id)
                self.assertEqual(receipt is not None, committed)
                self.assertEqual(memory().detail(name).version, 2 if committed else 1)

    def test_10_cancel_after_mutation_before_commit_rolls_back(self):
        seed('cancel-body')
        e = epoch()
        class Cursor:
            def __init__(self, cursor):
                self.cursor = cursor
            def __getattr__(self, key):
                return getattr(self.cursor, key)
            def execute(self, sql, args=None):
                result = self.cursor.execute(sql, args)
                if 'INSERT INTO cj_memory_management_action' in sql:
                    raise asyncio.CancelledError('synthetic after receipt SQL, before commit')
                return result
        class Cancel:
            def __init__(self):
                self.conn = connect()
            def __getattr__(self, key):
                return getattr(self.conn, key)
            def cursor(self):
                return Cursor(self.conn.cursor())
        with self.assertRaises(asyncio.CancelledError):
            management(factory=Cancel).apply(action('cancel-body'))
        self.assertEqual(memory().detail('cancel-body').version, 1)
        self.assertEqual(epoch(), e)
        self.assertIsNone(management().query('pause-cancel-body'))

    def test_11_scope_lock_serializes_with_original_publication_transaction(self):
        seed('locked')
        context = memory().effective('self')
        entered, finished = threading.Event(), threading.Event()
        def pause():
            entered.set()
            try:
                return management().apply(action('locked'))
            finally:
                finished.set()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with MemoryRepository(connect, 'A').transaction() as tx:
                tx.require_current(context, 'self')
                future = pool.submit(pause)
                self.assertTrue(entered.wait(2))
                self.assertFalse(finished.wait(0.15))
                tx.require_current(context, 'self')
            self.assertEqual(future.result(timeout=5).status, 'disabled')
        with self.assertRaises(Conflict):
            with MemoryRepository(connect, 'A').transaction() as tx:
                tx.require_current(context, 'self')

    def test_12_temporary_companion_and_long_term_stay_scoped(self):
        seed('long', slot='pace')
        seed('temporary', slot='pace', extent='current', context_id='trip-1')
        seed('companion', slot='pace', subject='companion-1')
        self.assertIn('temporary', ids(context='trip-1'))
        management().apply(action('temporary'))
        self.assertIn('long', ids(context='trip-1'))
        self.assertIn('long', ids(context='trip-2'))
        self.assertIn('companion', ids(subject='companion-1'))
        management().apply(action('temporary', 'resume', 2))
        self.assertIn('temporary', ids(context='trip-1'))
        self.assertNotIn('temporary', ids(context='trip-2'))

    def test_13_shape_errors_and_no_client_authority(self):
        raw = action('shape')
        obj = json.loads(raw)
        bad = [b'[]', b'null', b'\xff', b'{', raw.replace(b'"pause"', b'"edit"')]
        for key, value in [('owner', 'A'), ('expected_version', True),
                           ('expected_source_version', 0), ('item_id', ' '),
                           ('text', 'new text')]:
            changed = dict(obj)
            changed[key] = value
            bad.append(json.dumps(changed).encode())
        bad.append(raw.replace(b'"operation":', b'"operation":"resume","operation":'))
        for invalid in bad:
            with self.assertRaises(InvalidInput):
                management().apply(invalid)

    def test_14_durable_restart_fixtures(self):
        seed('restart-paused')
        seed('restart-resumed')
        management().apply(action('restart-paused'))
        management().apply(action('restart-resumed'))
        management().apply(action('restart-resumed', 'resume', 2))


def restart():
    assert memory().detail('restart-paused').status == 'disabled'
    assert memory().detail('restart-resumed').version == 3
    assert 'restart-paused' not in ids()
    assert 'restart-resumed' in ids()
    for name in ('restart-paused', 'restart-resumed'):
        raw = action(name)
        original = management().query('pause-' + name)
        assert original is not None
        assert original.input_sha256 == hashlib.sha256(raw).hexdigest()
        assert management().apply(raw) == original
    assert management('B').query('pause-restart-paused') is None
    print('PASS restart: pause/resume current reads, original receipt/hash/replay, scope isolation')


if __name__ == '__main__':
    if '--restart' in sys.argv:
        restart()
    else:
        unittest.main(verbosity=2)
