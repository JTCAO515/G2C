import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from test_trip import (empty, connect, repo, proposal, action, Boundary, Denied,
                       TrustedPrincipal, AdmissionDecision, AdmissionStatus, AdmissionReason)
from cj_trip.operation import OperationWithheld
from cj_trip import auth_boundary

P=TrustedPrincipal('issuer','subject','audience',1,1,9999999999)
class Checker:
    def __init__(self): self.allowed=True; self.interrupt=None; self.calls=0
    def check(self,token):
        self.calls+=1
        if self.interrupt:raise self.interrupt()
        return (AdmissionDecision(AdmissionStatus.ALLOWED,AdmissionReason.ACCEPTED,P)
                if self.allowed else AdmissionDecision(AdmissionStatus.UNKNOWN,AdmissionReason.FACTS_UNKNOWN))

def boundary(checker=None, factory=connect):
    return Boundary(checker or Checker(),lambda _:(factory,'A'),lambda *args:True)


def test_public_projection_and_metadata():
    r=repo();p=proposal();a=action(r,p);b=boundary()
    def project(ctx):
        assert ctx.metadata.principal==P and ctx.metadata.scope=='A'
        d=ctx.proposal_detail('p1');assert d.candidate_hash==a.candidate_hash
        receipt=ctx.act(a)
        assert ctx.query_action(a.action_id)==receipt
        assert ctx.list_trips()==[ctx.detail('trip1')]
        return json.dumps({'action':receipt.action_id,'version':receipt.committed_version}).encode()
    assert json.loads(b.with_operation('synthetic',project))=={'action':'a1','version':1}


@pytest.mark.parametrize('db_read',[False,True])
def test_final_guard_after_serialization(db_read):
    repo().publish(proposal());checker=Checker();b=boundary(checker)
    def project(ctx):
        if db_read:ctx.proposal_detail('p1')
        raw=b'private encoded data';checker.allowed=False
        return raw
    with pytest.raises(Denied):b.with_operation('synthetic',project)


@pytest.mark.parametrize('stage',['transaction','commit','return'])
@pytest.mark.parametrize('interrupted',[False,True])
def test_caught_guard_failure_is_sticky(stage,interrupted):
    r=repo();a=action(r,proposal());checker=Checker()
    # bind admission=1, operation entry=2, transaction=3, commit=4, return=5.
    failed_at={'transaction':3,'commit':4,'return':5}[stage]
    original=checker.check
    def check(token):
        if checker.calls+1==failed_at:
            checker.calls+=1
            if interrupted:raise asyncio.CancelledError()
            return AdmissionDecision(AdmissionStatus.UNKNOWN,AdmissionReason.FACTS_UNKNOWN)
        return original(token)
    checker.check=check
    def project(ctx):
        try:ctx.act(a)
        except BaseException:pass
        return b'private'
    with pytest.raises(OperationWithheld) as caught:boundary(checker).with_operation('synthetic',project)
    assert caught.value.action_id=='a1'
    assert caught.value.commit_possible==(stage=='return')
    assert caught.value.recovery=='reconcile_original'
    assert (r.query_action('a1') is not None)==(stage=='return')


@pytest.mark.parametrize('error',[ValueError,asyncio.CancelledError,KeyboardInterrupt])
def test_projection_failure_after_commit(error):
    r=repo();a=action(r,proposal())
    def project(ctx):ctx.act(a);raise error('no private result')
    with pytest.raises(OperationWithheld) as caught:boundary().with_operation('synthetic',project)
    assert caught.value.action_id=='a1' and caught.value.commit_possible
    assert r.query_action('a1').committed_version==1


def test_context_expiration_cross_thread_and_nested_request():
    b=boundary();escaped=[]
    assert b.with_operation('synthetic',lambda ctx:(escaped.append(ctx),b'{}')[1])==b'{}'
    with pytest.raises(OperationWithheld):escaped[0].list_trips()
    def project(ctx):
        with ThreadPoolExecutor(1) as pool:
            with pytest.raises(OperationWithheld):pool.submit(ctx.list_trips).result()
        return b'private'
    with pytest.raises(OperationWithheld):b.with_operation('synthetic',project)
    def nested(ctx):
        def child(other):
            with pytest.raises(OperationWithheld):ctx.list_trips()
            return b'{}'
        b.with_operation('synthetic',child)
        return b'private'
    with pytest.raises(OperationWithheld):b.with_operation('synthetic',nested)


def test_async_and_lazy_projection_rejected():
    b=boundary()
    async def async_callback(ctx):return b'private'
    with pytest.raises(TypeError):b.with_operation('synthetic',async_callback)
    with pytest.raises(TypeError):b.with_operation('synthetic',lambda ctx:iter([b'private']))
    with pytest.raises(TypeError):b.with_operation('synthetic',lambda ctx:{'private':'data'})


@pytest.mark.parametrize('change',['scope','connect','confirm','checker','resolver'])
def test_binding_drift_after_projection(monkeypatch,change):
    captured=[];Original=auth_boundary.Repository
    def capture(*args):
        r=Original(*args);captured.append(r);return r
    monkeypatch.setattr(auth_boundary,'Repository',capture)
    b=boundary()
    def project(ctx):
        assert ctx.metadata.scope=='A'
        if change=='scope':captured[0].scope='B'
        elif change=='connect':captured[0].connect=lambda:None
        elif change=='confirm':captured[0].confirm=lambda *args:True
        elif change=='checker':b.checker=Checker()
        else:b.resolve=lambda _:(connect,'B')
        return b'private'
    with pytest.raises(Denied):b.with_operation('synthetic',project)


def test_unknown_commit_preserves_original_and_sticky():
    r=repo();a=action(r,proposal())
    class Lost:
        def __init__(self):self.c=connect()
        def __getattr__(self,name):return getattr(self.c,name)
        def commit(self):self.c.commit();raise asyncio.CancelledError()
    def project(ctx):
        try:ctx.act(a)
        except OperationWithheld:pass
        return b'private'
    with pytest.raises(OperationWithheld) as caught:boundary(factory=Lost).with_operation('synthetic',project)
    assert caught.value.action_id=='a1' and caught.value.commit_possible
    assert r.query_action('a1').committed_version==1
