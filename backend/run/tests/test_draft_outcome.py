import unittest
from unittest.mock import Mock
from cj_run.core import Binding, Event, Service, Conflict, DRAFT_OUTCOMES
from cj_run.fixture import MemoryRepository
from cj_agent.worker import RunWorker
from cj_agent.draft import DraftRejected
from cj_agent.provider import ProviderFailed, ProviderUnknown


class DraftOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.binding = Binding('scope', 'chat', 'gen', 'message', 'run', 1)
        self.service = Service(MemoryRepository(), lambda _: True)
        self.service.accept(self.binding)
        self.event('started')

    def event(self, kind, value=''):
        seq = self.service.snapshot(self.binding).sequence + 1
        return self.service.apply(Event(self.binding, seq, str(seq), kind, value))

    def test_payload_boundary(self):
        for value in ('', 'arbitrary', 'published'):
            with self.assertRaises(ValueError):
                Event(self.binding, 2, '2', 'draft_outcome', value)
        for value in DRAFT_OUTCOMES:
            Event(self.binding, 2, '2', 'draft_outcome', value)

    def test_failure_replay_and_both_directions(self):
        event = Event(self.binding, 2, '2', 'draft_outcome', 'validation_failed')
        state = self.service.apply(event)
        self.assertEqual(self.service.apply(event), state)
        for kind, value in [('draft_outcome', 'provider_unknown'), ('effect_committed', 'trip_proposal:p')]:
            with self.assertRaises(Conflict): self.event(kind, value)
        self.event('effect_committed', 'unrelated')
        self.assertEqual(self.event('completed').draft_outcome, 'validation_failed')
        self.setUp()
        self.event('effect_committed', 'trip_proposal:p')
        with self.assertRaises(Conflict): self.event('draft_outcome', 'validation_failed')

    def test_no_calls_after_persisted_failure(self):
        self.event('draft_outcome', 'provider_unknown')
        provider, publisher = Mock(), Mock()
        worker = RunWorker(scope='scope', messages=Mock(), runs=self.service, provider=provider, drafts=publisher)
        with self.assertRaises(Conflict):
            worker._draft(self.binding, self.service.snapshot(self.binding), 'original')
        provider.stream.assert_not_called()
        publisher.publish.assert_not_called()
        invoke = Mock()
        with self.assertRaises(Conflict): worker._step(self.binding, invoke, draft=True)
        invoke.assert_not_called()

    def test_exception_result_returns_updated_sequence(self):
        for exception, outcome in [(DraftRejected, 'validation_failed'), (ProviderFailed, 'provider_failed'),
                                   (ProviderUnknown, 'provider_unknown')]:
            with self.subTest(exception=exception):
                self.setUp()
                def stream(*args, **kwargs):
                    if exception is not DraftRejected: raise exception()
                    yield 'invalid draft'
                provider = Mock(stream=stream)
                publisher = Mock()
                publisher.publish.side_effect = DraftRejected()
                worker = RunWorker(scope='scope', messages=Mock(), runs=self.service, provider=provider, drafts=publisher)
                state, proposal = worker._draft(self.binding, self.service.snapshot(self.binding), 'original')
                self.assertIsNone(proposal)
                self.assertEqual((state.sequence, state.draft_outcome, state.status), (2, outcome, 'running'))
                completed = worker._event(self.binding, state, 'completed')
                self.assertEqual((completed.sequence, completed.status), (3, 'completed'))

    def test_cancel_terminal_rejects_outcome(self):
        self.event('cancelled')
        with self.assertRaises(Conflict): self.event('draft_outcome', 'validation_failed')
