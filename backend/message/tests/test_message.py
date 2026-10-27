import copy
import json
import unittest
from contextlib import contextmanager
from dataclasses import replace
from cj_message.domain import (Service, Chat, Cursor, Command, InvalidInput, Receipt,
                               InputConflict, CommitUnknown, ResyncRequired, Unavailable)
from cj_message.postgres import Repository, Transaction


def wire(mid='m1', cid='c1'):
    return json.dumps(dict(version='MESSAGE-draft.1', conversation_id=cid,
                           message_id=mid, text='你好', trip_id=None,
                           creation_intent='consider_trip'), ensure_ascii=False).encode()


class FakeRepository:
    """Injected transaction test double, NOT PostgreSQL or durable evidence."""
    scope = 'test-partition'

    def __init__(self):
        self.chats = {'c1': Chat('g1', 0, 0), 'c2': Chat('g2', 0, 0)}
        self.rows, self.jobs = {}, {}
        self.fail_enqueue = self.lose_commit_ack = False

    @contextmanager
    def transaction(self):
        old = copy.deepcopy((self.chats, self.rows, self.jobs))
        try:
            yield self
        except BaseException:
            self.chats, self.rows, self.jobs = old
            raise
        if self.lose_commit_ack:
            raise CommitUnknown()

    def lock_scope(self):
        pass

    def chat(self, cid, generation=None):
        c = self.chats.get(cid)
        if c is None or (generation is not None and c.generation != generation):
            raise Unavailable()
        return c

    def find(self, mid):
        return self.rows.get(mid)

    def insert(self, stored):
        r = stored.receipt
        self.rows[r.message_id] = stored
        self.chats[r.conversation_id] = replace(self.chats[r.conversation_id], last_sequence=r.sequence)

    def enqueue(self, r):
        if self.fail_enqueue:
            raise RuntimeError('injected delivery insert failure')
        self.jobs[r.run_id] = r

    def page(self, cid, generation, after, through, limit):
        return sorted([s.receipt for s in self.rows.values()
                       if s.receipt.conversation_id == cid and s.receipt.generation == generation
                       and after < s.receipt.sequence <= through], key=lambda r:r.sequence)[:limit]

    def pending(self, limit):
        return [r for r in self.jobs.values() if r.run_id not in self.acked][:limit]

    acked = frozenset()

    def acknowledge(self, mid, run_id):
        self.acked = self.acked | {run_id}

    inactive = frozenset()

    def open_chat(self, cid, generation):
        if cid in self.chats or cid in self.inactive:
            return None
        self.chats[cid] = Chat(generation, 0, 0)
        return self.chats[cid]


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepository()
        self.ids = iter(['run1', 'run2', 'run3'])
        self.service = Service(self.repo, lambda: next(self.ids))

    def test_duplicate_and_exact_bytes_conflict(self):
        original = self.service.receive(wire())
        self.assertEqual(original, self.service.receive(wire()))
        for raw in (wire() + b' ', wire(cid='c2')):
            with self.assertRaises(InputConflict): self.service.receive(raw)
        self.assertEqual(len(self.repo.jobs), 1)

    def test_enqueue_failure_rolls_back_message_and_sequence(self):
        self.repo.fail_enqueue = True
        with self.assertRaises(RuntimeError): self.service.receive(wire())
        self.assertEqual(self.repo.rows, {})
        self.assertEqual(self.repo.jobs, {})
        self.assertEqual(self.repo.chats['c1'].last_sequence, 0)

    def test_commit_ack_unknown_query_original_and_pending_same_run(self):
        self.repo.lose_commit_ack = True
        with self.assertRaises(CommitUnknown): self.service.receive(wire())
        self.repo.lose_commit_ack = False
        receipt = self.service.query('m1').receipt
        self.assertEqual(receipt.run_id, 'run1')
        self.assertEqual(self.service.receive(wire()), receipt)
        self.assertEqual(self.service.pending(), [receipt])
        self.assertEqual(self.service.pending(), [receipt])
        self.assertIsNone(self.service.query('never-submitted'))

    def test_invalid_input_never_writes(self):
        p = json.loads(wire()); p['owner'] = 'forged'
        trip = json.loads(wire()); trip['trip_id'] = 'unverified'
        for raw in (b'\xff', b'null', b'{"text":"x","text":"y"}',
                    json.dumps(p).encode(), json.dumps(trip).encode(), bytearray(wire())):
            with self.assertRaises(InvalidInput): self.service.receive(raw)
        self.assertEqual(self.repo.rows, {})

    def test_snapshot_append_and_generation_epoch_scope_fences(self):
        self.service.receive(wire()); self.service.receive(wire('m2'))
        _, cursor = self.service.page('c1', limit=1)
        self.service.receive(wire('m3'))
        tail, nxt = self.service.page('c1', cursor)
        self.assertEqual([r.message_id for r in tail], ['m2']); self.assertIsNone(nxt)
        for changed in (replace(cursor, generation='other'), replace(cursor, epoch=3),
                        replace(cursor, scope='foreign'), ('legacy',)):
            with self.assertRaises(ResyncRequired): self.service.page('c1', changed)
        self.repo.chats['c1'] = Chat('new-generation', 0, 0)
        with self.assertRaises(ResyncRequired): self.service.page('c1', cursor)
        self.assertEqual(self.service.page('c1'), ([], None))

    def test_history_hole_rejects_not_empty_success(self):
        self.service.receive(wire()); self.service.receive(wire('m2'))
        _, cursor = self.service.page('c1', limit=1)
        del self.repo.rows['m2']
        with self.assertRaises(ResyncRequired): self.service.page('c1', cursor)

    def test_open_conversation_is_idempotent_and_never_reactivates(self):
        first = self.service.open_conversation('new-chat')
        self.assertEqual(self.service.open_conversation('new-chat'), first)
        receipt = self.service.receive(wire(cid='new-chat'))
        self.assertEqual((receipt.conversation_id, receipt.generation, receipt.sequence), ('new-chat', first.generation, 1))
        self.repo.inactive = frozenset({'archived'})
        with self.assertRaises(Unavailable): self.service.open_conversation('archived')
        for bad in ('', '  ', 'a\x00b', 'x' * 257, None):
            with self.assertRaises(InvalidInput): self.service.open_conversation(bad)

    def test_acknowledge_removes_only_the_exact_delivery(self):
        receipt = self.service.receive(wire())
        self.assertEqual(self.service.pending(), [receipt])
        with self.assertRaises(InputConflict):
            self.service.acknowledge(Receipt(receipt.message_id, 'c1', 'g1', 1, 'other-run', receipt.input_sha256))
        self.service.acknowledge(receipt)
        self.service.acknowledge(receipt)  # idempotent
        self.assertEqual(self.service.pending(), [])

    def test_missing_chat_and_stale_receipt_unavailable(self):
        with self.assertRaises(Unavailable): self.service.receive(wire(cid='foreign'))
        self.service.receive(wire())
        self.repo.chats['c1'] = Chat('recreated', 0, 0)
        with self.assertRaises(Unavailable): self.service.receive(wire())


class RecordingConnection:
    """DB-API protocol double; SQL is recorded, NOT executed by a database."""
    autocommit = False
    rowcount = 1

    def __init__(self):
        self.calls, self.commits, self.rollbacks, self.closes = [], 0, 0, 0
        self.lose_ack = False
        self.row = ('test-partition',)

    def cursor(self): return self
    def execute(self, sql, params=()): self.calls.append((sql, params))
    def fetchone(self): return self.row
    def fetchall(self): return []
    def close(self): self.closes += 1
    def rollback(self): self.rollbacks += 1
    def commit(self):
        self.commits += 1
        if self.lose_ack: raise OSError('commit response lost')


class AdapterTests(unittest.TestCase):
    def test_commit_and_close_after_yield(self):
        c = RecordingConnection()
        with Repository(lambda:c, 'test-partition').transaction() as tx:
            tx.lock_scope()
            self.assertEqual(c.commits, 0)
        self.assertEqual((c.commits, c.rollbacks, c.closes), (1, 0, 2))
        self.assertIn('READ COMMITTED', c.calls[0][0])
        self.assertIn('FOR UPDATE', c.calls[1][0])

    def test_failure_rollback_not_commit(self):
        c = RecordingConnection()
        with self.assertRaises(RuntimeError):
            with Repository(lambda:c, 'test-partition').transaction():
                raise RuntimeError('statement failure')
        self.assertEqual((c.commits, c.rollbacks), (0, 1))

    def test_commit_unknown_never_retries(self):
        c = RecordingConnection(); c.lose_ack = True
        with self.assertRaises(CommitUnknown):
            with Repository(lambda:c, 'test-partition').transaction(): pass
        self.assertEqual((c.commits, c.rollbacks), (1, 0))

    def test_autocommit_rejected_and_scope_parameterized(self):
        c = RecordingConnection(); c.autocommit = True
        with self.assertRaises(ValueError):
            with Repository(lambda:c, 'test-partition').transaction(): pass
        c = RecordingConnection()
        attack = "x'; DROP TABLE example; --"
        c.row = None
        Transaction(c, attack).find(attack)
        self.assertNotIn(attack, c.calls[0][0])
        self.assertEqual(c.calls[0][1], (attack, attack))

    def test_service_uses_one_sql_transaction_for_receipt_and_delivery(self):
        c = RecordingConnection()
        answers = iter([('test-partition',), None, ('generation-1', 0, 0)])
        c.fetchone = lambda: next(answers)
        service = Service(Repository(lambda:c, 'test-partition'), lambda:'original-run')
        receipt = service.receive(wire())
        self.assertEqual(receipt.run_id, 'original-run')
        writes = [(sql, args) for sql, args in c.calls if sql.startswith('INSERT')]
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0][1][-1], wire())
        self.assertEqual(writes[0][1][5], writes[1][1][2])
        self.assertEqual((c.commits, c.rollbacks), (1, 0))

    def test_delivery_sql_failure_rolls_back_whole_connection(self):
        c = RecordingConnection()
        answers = iter([('test-partition',), None, ('generation-1', 0, 0)])
        c.fetchone = lambda: next(answers)
        record = c.execute
        def execute(sql, args=()):
            record(sql, args)
            if sql.startswith('INSERT INTO cj_message_delivery'):
                raise RuntimeError('injected SQL execution failure')
        c.execute = execute
        service = Service(Repository(lambda:c, 'test-partition'), lambda:'original-run')
        with self.assertRaises(RuntimeError): service.receive(wire())
        self.assertEqual((c.commits, c.rollbacks), (0, 1))

    def test_page_generation_and_pending_scope_are_parameters(self):
        c = RecordingConnection(); tx = Transaction(c, 'scope-a')
        tx.page('chat', 'generation', 1, 3, 2)
        self.assertEqual(c.calls[-1][1], ('scope-a', 'chat', 'generation', 1, 3, 2))
        tx.pending(2)
        self.assertEqual(c.calls[-1][1], ('scope-a', 2))
        self.assertIn('c.active', c.calls[-1][0])


if __name__ == '__main__': unittest.main(verbosity=2)
