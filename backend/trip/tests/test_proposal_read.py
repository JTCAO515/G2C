from dataclasses import replace
import time
import pytest
from test_trip import (empty, repo, proposal, action, connect, Boundary, Denied,
                       TrustedPrincipal, AdmissionDecision, AdmissionStatus, AdmissionReason)


def test_exact_read_does_not_authorize():
    r=repo();p=proposal();digest=r.publish(p)
    detail=r.proposal_detail('p1')
    assert detail.proposal == p and detail.candidate_hash == digest and detail.status=='pending'
    a=action(r,p)
    with pytest.raises(Denied):repo(confirm=None).act(a)
    assert r.query_action(a.action_id) is None


def test_wrong_scope_and_absent_are_same():
    repo().publish(proposal())
    messages=[]
    for r,pid in [(repo('B'),'p1'),(repo(),'absent')]:
        with pytest.raises(Denied) as err:r.proposal_detail(pid)
        messages.append(str(err.value))
    assert messages==['candidate unavailable']*2


@pytest.mark.parametrize('status',['accepted','rejected','expired','superseded','elapsed_pending'])
def test_terminal_and_expiry_snapshot(status):
    r=repo();p=proposal(expires=int(time.time())-1 if status in ('expired','elapsed_pending') else None)
    a=action(r,p)
    if status in ('accepted','rejected'):r.act(replace(a,kind='accept' if status=='accepted' else 'reject'))
    if status=='expired':r.retire('p1','expired')
    if status=='superseded':r.publish(proposal('p2'));r.retire('p1','superseded','p2')
    d=r.proposal_detail('p1')
    assert d.proposal==p and d.candidate_hash==a.candidate_hash
    assert d.status==('pending' if status=='elapsed_pending' else status)
    if status in ('expired','elapsed_pending'):assert d.proposal.expires_at < time.time()


@pytest.mark.parametrize('fail',[1,2,3,4])
def test_fresh_auth_read_guards(fail):
    repo().publish(proposal())
    p=TrustedPrincipal('issuer','subject','audience',1,1,9999999999)
    class Checker:
        calls=0
        def check(self,token):
            self.calls+=1
            if self.calls==fail:return AdmissionDecision(AdmissionStatus.UNKNOWN,AdmissionReason.FACTS_UNKNOWN)
            return AdmissionDecision(AdmissionStatus.ALLOWED,AdmissionReason.ACCEPTED,p)
    with pytest.raises(Denied):Boundary(Checker(),lambda _:(connect,'A')).proposal_detail('synthetic','p1')


def test_list_cursor_order_and_bounds():
    r=repo();ids=['z','A','a','a-1','a_1','Z']
    for i,tid in enumerate(ids):r.act(action(r,replace(proposal('p'+str(i)),trip_id=tid),'a'+str(i)))
    seen=[];after=''
    while True:
        page=r.list_trips(after,2)
        if not page:break
        seen.extend(t.trip_id for t in page);after=page[-1].trip_id
    assert seen==sorted(ids)
    assert repo('B').list_trips()==[]
    assert len(r.list_trips('not-a-record',2))<=2
    for cursor in (None,0,False,[]):
        with pytest.raises(ValueError):r.list_trips(cursor)
    for limit in (0,101,True):
        with pytest.raises(ValueError):r.list_trips(limit=limit)
