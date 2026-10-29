"""Cancellation regressions through the existing worker; synthetic storage only."""
import hashlib
import json
from types import SimpleNamespace

from cj_agent.worker import RunWorker
from cj_message.domain import Receipt, Stored
from cj_run.core import Binding, Service
from cj_run.fixture import MemoryRepository


class Messages:
    def __init__(self, intent='none'):
        raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id='chat', message_id='m',
                              text='original', trip_id=None, creation_intent=intent,
                              expected_generation='g', expected_sequence=0)).encode()
        self.receipt = Receipt('m', 'chat', 'g', 1, 'r', hashlib.sha256(raw).hexdigest())
        self.stored = Stored(raw, self.receipt)
        self.acknowledged = []
    def pending(self, limit): return [] if self.acknowledged else [self.receipt]
    def query(self, mid): return self.stored if mid == 'm' else None
    def acknowledge(self, receipt): self.acknowledged.append(receipt)


class Drafts:
    content_version = 'legacy'
    def __init__(self): self.calls = 0
    def publish(self, run_id, reply):
        self.calls += 1
        return SimpleNamespace(proposal_id='p-r')


def fixture(provider_factory, intent='none'):
    messages = Messages(intent)
    binding = Binding('scope', 'chat', 'g', 'm', 'r', 1)
    runs = Service(MemoryRepository(), lambda _: True)
    provider = provider_factory(runs, binding)
    drafts = Drafts()
    return RunWorker(scope='scope', messages=messages, runs=runs, provider=provider, drafts=drafts), runs, binding, provider, drafts


class CancelsDuringAnswer:
    def __init__(self, runs, binding): self.runs, self.binding, self.calls, self.closed = runs, binding, 0, False
    def stream(self, messages, system=None):
        self.calls += 1
        try:
            yield 'committed answer ' * 3
            self.runs.cancel(self.binding)
            yield 'late output must not publish'
        finally: self.closed = True


class CancelsBetweenCalls(CancelsDuringAnswer):
    def stream(self, messages, system=None):
        self.calls += 1
        if system is None:
            yield 'committed answer ' * 3
            self.runs.cancel(self.binding)
        else:
            yield '{"title":"late","items":["late"]}'


class CancelsDuringDraft(CancelsDuringAnswer):
    def stream(self, messages, system=None):
        self.calls += 1
        if system is None: yield 'committed answer ' * 3
        else:
            try:
                yield '{"title":"late",'
                self.runs.cancel(self.binding)
                yield '"items":["late"]}'
            finally: self.closed = True


def test_cancel_before_worker_dispatch_has_no_provider_call():
    worker, runs, binding, provider, drafts = fixture(CancelsDuringAnswer)
    stopped = runs.cancel(binding)
    assert worker.process()[0].status == 'cancelled'
    assert provider.calls == drafts.calls == 0
    assert runs.snapshot(binding) == stopped
    assert worker.messages.acknowledged == [worker.messages.receipt]


def test_cancel_during_answer_keeps_committed_text_and_closes_stream():
    worker, runs, binding, provider, drafts = fixture(CancelsDuringAnswer, 'consider_trip')
    outcome = worker.process()[0]
    assert outcome.status == 'cancelled'
    state = runs.snapshot(binding)
    assert state.text == 'committed answer ' * 3
    assert state.effects == ()
    assert provider.calls == 1 and provider.closed and drafts.calls == 0
    assert worker.messages.acknowledged == [worker.messages.receipt]


def test_cancel_after_answer_before_draft_prevents_second_provider_call():
    worker, runs, binding, provider, drafts = fixture(CancelsBetweenCalls, 'consider_trip')
    assert worker.process()[0].status == 'cancelled'
    assert provider.calls == 1 and drafts.calls == 0
    assert runs.snapshot(binding).text == 'committed answer ' * 3


def test_cancel_in_existing_draft_call_prevents_publication():
    worker, runs, binding, provider, drafts = fixture(CancelsDuringDraft, 'consider_trip')
    assert worker.process()[0].status == 'cancelled'
    assert provider.calls == 2 and provider.closed and drafts.calls == 0
    assert runs.snapshot(binding).effects == ()


def test_cancellation_reentered_from_start_guard_prevents_provider_outflow():
    worker, runs, binding, provider, drafts = fixture(CancelsDuringAnswer)
    calls = 0
    def valid(original):
        nonlocal calls
        calls += 1
        if calls == 2: runs.cancel(original)  # after RUN start, before provider outflow
        return True
    runs.valid = valid
    assert worker.process()[0].status == 'cancelled'
    assert provider.calls == 0
    assert runs.snapshot(binding).status == 'cancelled'
