import unittest
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from cj_run.core import Binding, Event, Service, Cursor, Conflict, Denied, ResyncRequired, page
from cj_run.fixture import MemoryRepository


class RunTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepository()
        self.b = Binding('fixture-user', 'chat', 'g1', 'm1', 'r1', 1)
        self.s = Service(self.repo, lambda _: True)
        self.s.accept(self.b)

    def event(self, kind, value='', sequence=None, identity=None):
        seq = sequence or self.s.snapshot(self.b).sequence + 1
        return Event(self.b, seq, identity or f'e{seq}', kind, value)

    def start(self):
        self.s.apply(self.event('started'))

    def test_binding_replay_and_conflict(self):
        self.start()
        self.assertEqual(self.s.accept(self.b).status, 'running')
        for b in (replace(self.b, run_id='other'), replace(self.b, message_id='other'),
                  replace(self.b, conversation_id='other')):
            with self.assertRaises(Conflict): self.s.accept(b)

    def test_exact_duplicate(self):
        self.start()
        e = self.event('text_delta', '合成')
        a = self.s.apply(e)
        self.assertEqual(self.s.apply(e), a)
        with self.assertRaises(Conflict): self.s.apply(replace(e, value='different'))

    def test_gap_out_of_order(self):
        with self.assertRaises(ResyncRequired): self.s.apply(self.event('started', sequence=2))
        self.assertEqual(self.s.snapshot(self.b).sequence, 0)
        self.start()
        with self.assertRaises(Conflict): self.s.apply(self.event('text_delta', 'x', sequence=1))

    def test_cancel_preserves_committed(self):
        self.start()
        self.s.apply(self.event('text_delta', 'partial'))
        self.s.apply(self.event('effect_committed', 'fixture-receipt'))
        state = self.s.apply(self.event('cancelled'))
        self.assertEqual(state.effects, ('fixture-receipt',))
        self.assertEqual(state.text, 'partial')
        for kind in ('completed', 'started', 'text_delta'):
            with self.assertRaises(Conflict):
                self.s.apply(self.event(kind, 'late' if kind == 'text_delta' else ''))
        self.assertEqual(self.s.snapshot(self.b), state)

    def test_single_terminal_race(self):
        self.start()
        events = [self.event(k, identity=k) for k in ('completed', 'cancelled')]
        def apply(e):
            try: return self.s.apply(e).status
            except Conflict: return 'rejected'
        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(apply, events))
        self.assertEqual(outcomes.count('rejected'), 1)
        self.assertEqual(self.s.snapshot(self.b).sequence, 2)

    def test_context_checked_each_publish(self):
        self.start()
        self.s.valid = lambda _: False
        for kind, val in [('text_delta', 'x'), ('effect_committed', 'receipt'), ('completed', '')]:
            with self.assertRaises(Denied): self.s.apply(self.event(kind, val))
        self.assertEqual(self.s.apply(self.event('context_invalid')).status, 'context_invalid')

    def test_missing_context_default_denied(self):
        with self.assertRaises(Denied): Service(self.repo).apply(self.event('started'))

    def test_disabled_dispatch(self):
        for kwargs in ({}, {'enabled': True, 'auth': True, 'quota': True, 'context': True}):
            with self.assertRaises(Denied): self.s.dispatch(**kwargs)

    def test_same_chat_order_and_missing_predecessor(self):
        second = replace(self.b, message_id='m2', run_id='r2', message_sequence=2)
        third = replace(second, message_id='m3', run_id='r3', message_sequence=3)
        self.s.accept(third)
        e3 = Event(third, 1, 'start3', 'started')
        with self.assertRaises(Conflict): self.s.apply(e3)
        self.s.accept(second)
        e2 = Event(second, 1, 'start2', 'started')
        with self.assertRaises(Conflict): self.s.apply(e2)
        self.s.apply(self.event('cancelled'))
        self.s.apply(e2)
        with self.assertRaises(Conflict): self.s.apply(e3)
        self.s.apply(Event(second, 2, 'cancel2', 'cancelled'))
        self.assertEqual(self.s.apply(e3).status, 'running')

    def test_rebuilt_service_replay(self):
        self.start()
        e = self.event('text_delta', 'fixture')
        self.s.apply(e)
        rebuilt = Service(self.repo, lambda _: True)
        self.assertEqual(rebuilt.apply(e).text, 'fixture')

    def test_cursor_fixed_highwater_and_expiry(self):
        self.start()
        self.s.apply(self.event('text_delta', 'a'))
        cursor = Cursor(self.b, 'epoch1', 2, 0)
        self.s.apply(self.event('completed'))
        rows, nxt = page(self.s.snapshot(self.b), 'epoch1', cursor, 1)
        self.assertEqual(len(rows), 1)
        rows, end = page(self.s.snapshot(self.b), 'epoch1', nxt, 1)
        self.assertEqual(rows[0].kind, 'text_delta')
        self.assertIsNone(end)
        for c in (replace(cursor, epoch='expired'), replace(cursor, binding=replace(self.b, scope='other')),
                  replace(cursor, through=99), replace(cursor, after=True)):
            with self.assertRaises(ResyncRequired): page(self.s.snapshot(self.b), 'epoch1', c, 1)

    def test_unknown_not_success(self):
        self.start()
        self.assertEqual(self.s.apply(self.event('unknown')).status, 'unknown')
        with self.assertRaises(Conflict): self.s.apply(self.event('completed'))
        b2 = replace(self.b, message_id='m2', run_id='r2', message_sequence=2)
        self.s.accept(b2)
        with self.assertRaises(Conflict): self.s.apply(Event(b2, 1, 'e1', 'started'))

    def test_payload_validation(self):
        for kind, value in [('reasoning', ''), ('completed', 'invented'), ('text_delta', '')]:
            with self.assertRaises(ValueError): self.event(kind, value)
        with self.assertRaises(ValueError): replace(self.b, message_sequence=True)

    def test_transaction_rollback(self):
        with self.assertRaises(RuntimeError):
            with self.repo.transaction() as tx:
                tx.accept(replace(self.b, message_id='m2', run_id='r2', message_sequence=2))
                raise RuntimeError('fixture commit failure')
        self.assertEqual(len(self.repo.rows), 1)


if __name__ == '__main__':
    unittest.main()
