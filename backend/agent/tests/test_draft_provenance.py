"""L0 publication admission/cancellation checks; no real database or provider."""
from dataclasses import replace
import json

import pytest

from cj_agent.draft import DraftPublisher, DraftRejected, trip_scope_for
from cj_agent.provider import FakeProvider
from cj_agent.worker import RunWorker
from cj_draft.provenance import SourceObservationBatch
from cj_run.core import Binding, Service
from cj_run.fixture import MemoryRepository
from test_worker_cancel import Messages


class Repository:
    scope = trip_scope_for('scope')

    def __init__(self): self.published = []

    def publish(self, proposal):
        self.published.append(proposal)
        return proposal.digest(self.scope)


def setup(monkeypatch, source_reader=None):
    monkeypatch.setenv('CJ_ENV', 'local')
    messages = Messages('consider_trip')
    binding = Binding('scope', 'chat', 'g', 'm', 'r', 1)
    repository = Repository()
    publisher = DraftPublisher(repository, clock=lambda: 1800000000,
                               content_version='provenance.1', source_reader=source_reader,
                               max_source_age_seconds=60 if source_reader else None)
    return messages, binding, repository, publisher


def test_explicit_activation_required_and_legacy_publish_cannot_drop_sources(monkeypatch):
    monkeypatch.delenv('CJ_DRAFT_CONTENT_VERSION', raising=False)
    assert DraftPublisher(Repository()).content_version == 'legacy'
    monkeypatch.setenv('CJ_DRAFT_CONTENT_VERSION', 'invalid')
    with pytest.raises(ValueError): DraftPublisher(Repository())
    monkeypatch.setenv('CJ_ENV', 'production')
    with pytest.raises(ValueError): DraftPublisher(Repository(), content_version='provenance.1')
    _, _, repository, publisher = setup(monkeypatch)
    with pytest.raises(DraftRejected): publisher.publish('r', '{"title":"x","items":["a"]}')
    assert repository.published == []


@pytest.mark.parametrize('change', ['scope', 'run', 'message', 'missing'])
def test_wrong_or_changed_source_cannot_publish(monkeypatch, change):
    messages, binding, repository, publisher = setup(monkeypatch)
    original, current = messages.stored, messages.stored
    if change == 'scope': binding = replace(binding, scope='other-user')
    elif change == 'run': binding = replace(binding, run_id='other-run')
    elif change == 'message': current = replace(current, raw=current.raw.replace(b'original', b'changed'))
    else: current = None
    with pytest.raises(DraftRejected):
        publisher.publish_for_message(binding, original, current, '{"title":"x","items":["a"]}', SourceObservationBatch(binding, ()))
    assert repository.published == []


def test_worker_publishes_original_message_and_unverified_model_text(monkeypatch):
    messages, binding, repository, publisher = setup(monkeypatch)
    runs = Service(MemoryRepository(), lambda _: True)
    worker = RunWorker(scope='scope', messages=messages, runs=runs, provider=FakeProvider(), drafts=publisher)
    outcome = worker.process()[0]
    assert (outcome.status, outcome.proposal_id) == ('completed', 'p-r')
    document = json.loads(repository.published[0].content)
    assert document['items'][0]['text'] == 'original'
    assert document['items'][0]['source_category'] == 'user_provided'
    assert {i['source_category'] for i in document['items'][1:]} == {'unknown'}
    assert all(i['verification'] == 'pending' and i['evidence'] == [] for i in document['items'])


@pytest.mark.parametrize('change', ['cancel', 'source-change'])
def test_publication_fence_rechecks_after_source_acquisition(monkeypatch, change):
    messages, binding, repository, publisher = setup(monkeypatch)
    runs = Service(MemoryRepository(), lambda _: True)
    def sources(actual):
        assert actual == binding
        if change == 'cancel': runs.cancel(binding)
        else: messages.stored = replace(messages.stored, raw=messages.stored.raw.replace(b'original', b'changed'))
        return SourceObservationBatch(actual, ())
    publisher.source_reader = sources
    publisher.max_source_age_seconds = 60
    worker = RunWorker(scope='scope', messages=messages, runs=runs, provider=FakeProvider(), drafts=publisher)
    outcome = worker.process()[0]
    assert outcome.proposal_id is None
    assert outcome.status == ('cancelled' if change == 'cancel' else 'completed')
    assert repository.published == []
    assert runs.snapshot(binding).effects == ()


def test_source_batch_from_another_account_cannot_publish(monkeypatch):
    messages, binding, repository, publisher = setup(monkeypatch)
    foreign = SourceObservationBatch(replace(binding, scope='other-account'), ())
    with pytest.raises(DraftRejected):
        publisher.publish_for_message(binding, messages.stored, messages.stored,
                                      '{"title":"x","items":["a"]}', foreign)
    assert repository.published == []
