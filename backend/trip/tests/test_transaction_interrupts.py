"""Real DB controls for Testing's commit_cancel and close_cancel counterexamples."""
import asyncio
import pytest
from test_trip import empty, connect, repo, proposal, action, CommitUnknown, Denied
from test_transaction_faults import state


@pytest.mark.parametrize('interrupt', [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize('mode', ['commit_cancel','close_cancel','precommit','return_cancel','known_success_close','denial_close'])
def test_interruption_outcomes(interrupt,mode,caplog):
    r=repo(); a=action(r,proposal())
    primary=interrupt('synthetic primary interrupt')
    class Interrupted:
        def __init__(self):self.c=connect()
        def __getattr__(self,name):return getattr(self.c,name)
        def commit(self):
            self.c.commit()
            if mode=='commit_cancel':raise primary
            if mode=='close_cancel':raise ConnectionError('synthetic lost ACK')
        def rollback(self):
            self.c.rollback()
            if mode=='precommit':raise interrupt('secondary rollback interrupt')
        def close(self):
            self.c.close()
            if mode in ('close_cancel','precommit','return_cancel','known_success_close','denial_close'):
                raise interrupt('secondary cleanup interrupt')
    denial=Denied('AUTH changed');denial.commit_possible=True
    def guard(stage):
        if stage=='commit' and mode=='precommit':raise primary
        if stage=='return' and mode=='return_cancel':raise primary
        if stage=='return' and mode=='denial_close':raise denial
    expected=CommitUnknown if mode in ('commit_cancel','close_cancel') else Denied if mode=='denial_close' else interrupt
    with pytest.raises(expected) as caught:repo(factory=Interrupted,guard=guard).act(a)
    error=caught.value
    if mode=='commit_cancel':assert error.__cause__ is primary
    if mode=='close_cancel':assert isinstance(error.__cause__,ConnectionError)
    if mode in ('precommit','return_cancel'):assert error is primary
    if mode=='denial_close':assert error is denial
    if mode!='precommit':
        assert error.commit_possible is True
        assert state()==(1,1,'accepted')
        assert r.query_action('a1').committed_version==1
    else:
        assert state()==(0,0,'pending')
        assert r.query_action('a1') is None


def test_logger_interrupt_does_not_replace_primary(monkeypatch):
    from cj_trip import postgres
    r=repo();a=action(r,proposal())
    class Broken:
        def __init__(self):self.c=connect()
        def __getattr__(self,name):return getattr(self.c,name)
        def commit(self):self.c.commit();raise asyncio.CancelledError()
        def close(self):self.c.close();raise KeyboardInterrupt()
    def log(*args):raise SystemExit()
    monkeypatch.setattr(postgres.logger,'warning',log)
    with pytest.raises(CommitUnknown) as caught:repo(factory=Broken).act(a)
    assert isinstance(caught.value.__cause__,asyncio.CancelledError)
    assert caught.value.commit_possible
    assert r.query_action('a1').committed_version==1
