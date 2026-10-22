"""Regression: callback commits must survive stale outer transaction rejection."""
import unittest
from cj_run.core import Binding, Event, Service, Conflict, Denied
from cj_run.fixture import MemoryRepository


class ReentryTests(unittest.TestCase):
    def setUp(self):
        self.repo=MemoryRepository()
        self.b=Binding('fixture','chat','g','m','r',1)
        self.s=Service(self.repo,lambda _:True)
        self.s.accept(self.b)

    def test_cancel_during_start_preserved(self):
        def valid(b):
            self.assertEqual(self.s.apply(Event(b,1,'cancel','cancelled')).status,'cancelled')
            return True
        self.s.valid=valid
        with self.assertRaises(Conflict): self.s.apply(Event(self.b,1,'start','started'))
        state=self.s.snapshot(self.b)
        self.assertEqual((state.status,tuple(e.event_id for e in state.events)),('cancelled',('cancel',)))

    def test_cancel_during_append_and_finish_preserved(self):
        for kind,val in [('text_delta','stale'),('effect_committed','stale-receipt'),('completed','')]:
            with self.subTest(kind=kind):
                self.setUp()
                self.s.apply(Event(self.b,1,'start','started'))
                def valid(b):
                    self.s.apply(Event(b,2,'cancel','cancelled'))
                    return True
                self.s.valid=valid
                with self.assertRaises(Conflict): self.s.apply(Event(self.b,2,'outer',kind,val))
                state=self.s.snapshot(self.b)
                self.assertEqual((state.status,state.text,state.effects),('cancelled','',()))
                self.assertEqual(state.events[-1].event_id,'cancel')

    def test_callback_committed_event_survives_stale_outer(self):
        self.s.apply(Event(self.b,1,'start','started'))
        def valid(b):
            self.s.valid=lambda _:True
            self.s.apply(Event(b,2,'effect','effect_committed','receipt'))
            return True
        self.s.valid=valid
        with self.assertRaises(Conflict): self.s.apply(Event(self.b,2,'outer','completed'))
        state=self.s.snapshot(self.b)
        self.assertEqual((state.status,state.effects),('running',('receipt',)))

    def test_cancel_survives_hook_false_and_exception(self):
        for result in ('false','throw'):
            with self.subTest(result=result):
                self.setUp()
                def valid(b):
                    self.s.apply(Event(b,1,'cancel','cancelled'))
                    if result=='throw': raise RuntimeError('hook')
                    return False
                self.s.valid=valid
                with self.assertRaises((Denied,RuntimeError)):
                    self.s.apply(Event(self.b,1,'start','started'))
                self.assertEqual(self.s.snapshot(self.b).status,'cancelled')

    def test_read_only_reentry_is_allowed(self):
        self.s.valid=lambda b:self.s.snapshot(b).status=='queued'
        self.assertEqual(self.s.apply(Event(self.b,1,'start','started')).status,'running')
