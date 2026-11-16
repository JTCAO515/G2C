"""Actual worker publication fence; local RUN repository, no provider calls."""
from contextlib import contextmanager

import pytest

from cj_agent.provider import FakeProvider
from cj_agent.worker import RunWorker
from cj_needs.domain import Denied
from cj_run.core import Binding, Event, Service
from cj_run.fixture import MemoryRepository
from cj_usage.metered_exit import ExitAdmissionDenied


class Drafts:
    def __init__(self,version,*,deny=False):
        self.content_version=version;self.deny=deny;self.held=False;self.entries=0

    @contextmanager
    def hold_for_publication(self,binding):
        self.entries+=1;self.held=True
        def check():
            if self.deny:raise Denied('original source unavailable')
        try:yield check
        finally:self.held=False


def worker(version='structured.4',*,deny=False):
    binding=Binding('scope','chat','g','m','r',1)
    runs=Service(MemoryRepository(),lambda _:True)
    runs.accept(binding);runs.apply(Event(binding,1,'r:1','started'))
    drafts=Drafts(version,deny=deny)
    value=RunWorker(scope='scope',messages=None,runs=runs,provider=FakeProvider(),drafts=drafts)
    return value,runs,binding,drafts


@pytest.mark.parametrize('version',['structured.2','structured.3','structured.4'])
def test_original_holder_lives_through_actual_publication_and_effect(version):
    value,runs,binding,drafts=worker(version)
    def invoke():
        assert drafts.held
        return 'original-proposal'
    def effect(result):
        assert drafts.held
        return 'trip_proposal:'+result
    state,result=value._step(binding,invoke,effect,draft=True)
    assert result=='original-proposal'and state.effects==('trip_proposal:original-proposal',)
    assert runs.snapshot(binding)==state and drafts.entries==1 and not drafts.held


def test_native4_rejected_source_never_invokes_or_records_an_effect():
    value,runs,binding,drafts=worker(deny=True)
    calls=[];before=runs.snapshot(binding)
    with pytest.raises(Denied):value._step(binding,lambda:calls.append('publish'),lambda _:'unexpected',draft=True)
    assert calls==[]and runs.snapshot(binding)==before and drafts.entries==1 and not drafts.held


def test_streaming_draft_does_not_hold_publication_source_over_provider_io():
    value,runs,binding,drafts=worker()
    state,result=value._step(binding,lambda:'provider-input',draft=True)
    assert result=='provider-input'and state==runs.snapshot(binding)and drafts.entries==0


def test_existing_exit_admission_denial_precedes_publication_holder_and_effect():
    value,runs,binding,drafts=worker();calls=[];before=runs.snapshot(binding)
    class Budget:
        def prepare_publication(self,binding):raise ExitAdmissionDenied('original admission denied')
    value.message_context=object();value.budget_exit=Budget()
    with pytest.raises(ExitAdmissionDenied):
        value._step(binding,lambda:calls.append('publish'),lambda _:'unexpected',draft=True)
    assert calls==[]and drafts.entries==0 and runs.snapshot(binding)==before
