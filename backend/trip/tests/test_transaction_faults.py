"""Regression controls for de4e independent Review/Testing transaction findings."""
import time
import pytest
import psycopg
from test_trip import (empty, connect, repo, proposal, action, Denied, Conflict,
                       CommitUnknown, TrustedPrincipal, AdmissionDecision,
                       AdmissionStatus, AdmissionReason, Boundary)


def state():
    with connect() as c:
        return (c.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],
                c.execute('SELECT count(*) FROM cj_trip_receipt').fetchone()[0],
                c.execute("SELECT status FROM cj_trip_proposal WHERE proposal_id='p1'").fetchone()[0])


@pytest.mark.parametrize('mode', ['autocommit','active','unknown'])
def test_reject_connection_before_cursor(mode):
    r=repo(); a=action(r,proposal()); calls=[]
    class Invalid:
        def __init__(self):
            self.c=connect()
            if mode == 'autocommit': self.c.autocommit=True
            if mode == 'active': self.c.execute('SELECT 1')
        def __getattr__(self,name):
            if name == 'info' and mode == 'unknown': return None
            return getattr(self.c,name)
        def cursor(self): calls.append('cursor');return self.c.cursor()
        def rollback(self): calls.append('rollback');return self.c.rollback()
    with pytest.raises(Denied):repo(factory=Invalid).act(a)
    assert calls == []
    assert state() == (0,0,'pending')


@pytest.mark.parametrize('autocommit', [False,True])
def test_real_receipt_trigger_failure(autocommit):
    r=repo(); a=action(r,proposal())
    with connect() as c:
        c.execute("CREATE FUNCTION reject_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic receipt fault'; END $$")
        c.execute('CREATE TRIGGER reject_receipt BEFORE INSERT ON cj_trip_receipt FOR EACH ROW EXECUTE FUNCTION reject_receipt()')
    def factory():
        c=connect();c.autocommit=autocommit;return c
    try:
        with pytest.raises(Denied if autocommit else psycopg.errors.RaiseException):repo(factory=factory).act(a)
        assert state() == (0,0,'pending')
    finally:
        with connect() as c:
            c.execute('DROP TRIGGER reject_receipt ON cj_trip_receipt')
            c.execute('DROP FUNCTION reject_receipt()')


@pytest.mark.parametrize('kind', ['accept','reject'])
def test_expiry_after_slow_admission(kind):
    r=repo(); p=proposal(expires=int(time.time())+2); a=action(r,p,kind=kind)
    principal=TrustedPrincipal('issuer','subject','audience',1,1,9999999999)
    class SlowChecker:
        calls=0
        def check(self,token):
            self.calls+=1
            if self.calls==3:
                while time.time() <= p.expires_at+.05: time.sleep(.01)
            return AdmissionDecision(AdmissionStatus.ALLOWED,AdmissionReason.ACCEPTED,principal)
    with pytest.raises(Conflict):Boundary(SlowChecker(),lambda _:(connect,'A'),lambda *args:True).act('synthetic',a)
    assert state() == (0,0,'pending')


@pytest.mark.parametrize('outcome', ['success','lost_ack','return_denied','rollback'])
def test_cleanup_preserves_outcome(outcome,caplog):
    r=repo(); a=action(r,proposal())
    class CloseFailure:
        def __init__(self):self.c=connect()
        def __getattr__(self,name):return getattr(self.c,name)
        def commit(self):
            self.c.commit()
            if outcome=='lost_ack':raise ConnectionError('synthetic ACK loss')
        def close(self):
            self.c.close();raise OSError('sensitive details must not appear')
    def guard(stage):
        if stage=='return' and outcome=='return_denied':
            e=Denied('AUTH changed');e.commit_possible=True;raise e
        if stage=='commit' and outcome=='rollback':raise Denied('AUTH changed')
    if outcome=='success':
        result=repo(factory=CloseFailure,guard=guard).act(a)
        assert result == r.query_action('a1')
    else:
        with pytest.raises(CommitUnknown if outcome=='lost_ack' else Denied) as error:
            repo(factory=CloseFailure,guard=guard).act(a)
        if outcome=='return_denied':assert error.value.commit_possible
        if outcome=='lost_ack':assert isinstance(error.value.__cause__,ConnectionError)
    assert state() == ((0,0,'pending') if outcome=='rollback' else (1,1,'accepted'))
    assert 'cleanup failed: close' in caplog.text
    assert 'sensitive details' not in caplog.text
