import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest
import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'backend/trip'), str(ROOT/'backend/auth')]
from cj_trip.domain import Proposal, Action, Conflict, Denied, CommitUnknown, packed
from cj_trip.postgres import Repository
from cj_trip.auth_boundary import Boundary
from cj_auth.interfaces import TrustedPrincipal, AdmissionDecision, AdmissionStatus, AdmissionReason

# No DSN / ambient PG variables. Test runner explicitly provides task-private socket.
def connect():
    return psycopg.connect(host=os.environ['TRIP_TEST_SOCKET'], port=55435,
                          user='cj015_private', dbname='cj015_test', passfile=str(ROOT/'backend/trip/private-pg/no-password-file'))

@pytest.fixture(autouse=True)
def empty():
    with connect() as c:
        c.execute('TRUNCATE cj_trip_receipt,cj_trip_record,cj_trip_proposal,cj_trip_scope')
        c.execute("INSERT INTO cj_trip_scope VALUES ('A'),('B')")


def proposal(pid='p1', version=0, expires=None):
    return Proposal(pid,'trip1',version,'basis1',expires or int(time.time())+3600,
        packed({'title':'Synthetic fixture only','items':[{'id':'item1','text':'Unverified synthetic activity','verification':'pending','evidence':[]}]}))


def repo(scope='A', confirm=lambda *args: True, guard=None, factory=connect):
    return Repository(factory,scope,confirm,guard)


def action(r,p,aid='a1',kind='accept'):
    return Action(aid,kind,p.proposal_id,r.publish(p),'review1')


def test_accept_same_list_detail_restart():
    r=repo(); p=proposal(); a=action(r,p)
    receipt=r.act(a)
    assert receipt.committed_version == 1
    assert repo().list_trips() == [repo().detail('trip1')]
    assert repo().detail('trip1').content == p.content
    assert b'pending' in repo().detail('trip1').content
    assert repo().query_action(a.action_id) == receipt


def test_duplicates_and_original_version():
    r=repo(); a=action(r,proposal()); first=r.act(a)
    assert r.act(a) == first
    with pytest.raises(Conflict): r.act(replace(a,kind='reject'))
    r.act(action(r,proposal('p2',1),'a2'))
    assert r.detail('trip1').version == 2
    assert r.query_action('a1') == first
    assert r.act(a) == first


def test_wrong_scope_and_unconfigured():
    r=repo(); a=action(r,proposal())
    with pytest.raises(Denied): repo(confirm=None).act(a)
    with pytest.raises(Denied): repo('B').act(a)
    assert repo('B').query_action('a1') is None
    assert repo('B').list_trips() == []
    assert repo('B').detail('trip1') is None
    with pytest.raises(Denied): Boundary().act('never-a-real-token',a)


def test_immutable_hash_and_stale_version():
    r=repo(); p=proposal(); a=action(r,p)
    with pytest.raises(Conflict): r.publish(replace(p,basis_version='basis2'))
    with pytest.raises(Conflict): r.act(replace(a,candidate_hash='0'*64))
    stale=action(r,proposal('stale'),'stale')
    r.act(a)
    with pytest.raises(Conflict): r.act(stale)
    assert r.detail('trip1').version == 1


def test_reject_expire_supersede():
    r=repo(); a=action(r,proposal(),kind='reject')
    assert r.act(a) == r.act(a)
    assert r.list_trips() == []
    with pytest.raises(Conflict): r.act(replace(a,action_id='other',kind='accept'))
    expired=action(r,proposal('expired',expires=int(time.time())-1),'expired')
    r.retire('expired','expired')
    with pytest.raises(Conflict): r.act(expired)
    old=action(r,proposal('old'),'old')
    r.publish(proposal('new')); r.retire('old','superseded','new')
    with pytest.raises(Conflict): r.act(old)


def test_same_and_competing_concurrency():
    r=repo(); a=action(r,proposal())
    with ThreadPoolExecutor(8) as pool:
        receipts=list(pool.map(lambda _:repo().act(a),range(8)))
    assert all(x == receipts[0] for x in receipts)
    assert r.detail('trip1').version == 1
    b=action(r,proposal('p2',1),'a2')
    def run(a):
        try:return repo().act(a).kind
        except Conflict:return 'conflict'
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(run,[b,replace(b,action_id='a3',kind='reject')]))
    assert results.count('conflict') == 1


def test_expiration_acceptance_race():
    r=repo(); p=proposal(expires=int(time.time())-1); a=action(r,p)
    def accept():
        with pytest.raises(Conflict): repo().act(a)
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(accept),pool.submit(repo().retire,'p1','expired')]
        for f in futures:f.result()
    assert r.list_trips() == [] and r.query_action('a1') is None


def test_rollback_after_writes():
    r=repo(); a=action(r,proposal())
    def guard(stage):
        if stage == 'commit': raise RuntimeError('injected precommit failure')
    with pytest.raises(RuntimeError): repo(guard=guard).act(a)
    assert r.detail('trip1') is None and r.query_action('a1') is None
    assert r.act(a).committed_version == 1


def test_commit_ack_unknown():
    r=repo(); a=action(r,proposal())
    class LostAck:
        def __init__(self): self.c=connect()
        def __getattr__(self,name):return getattr(self.c,name)
        def commit(self):
            self.c.commit()
            raise ConnectionError('synthetic lost commit ACK')
    with pytest.raises(CommitUnknown):repo(factory=LostAck).act(a)
    assert repo().query_action('a1').committed_version == 1
    assert repo().detail('trip1').version == 1


def test_confirmation_exact_binding():
    p=proposal(); r=repo(); a=action(r,p)
    expected=(r.scope,a,p)
    checked=repo(confirm=lambda *args: args == expected)
    with pytest.raises(Denied):checked.act(replace(a,confirmation_ref='unseen'))
    assert checked.act(a).committed_version == 1


def test_missing_and_malformed():
    with pytest.raises(TypeError):Proposal('p')
    with pytest.raises(ValueError):replace(proposal(),expected_version=True)
    with pytest.raises(ValueError):replace(proposal(),content=b'{"title":"x","items":[]}')
    with pytest.raises(ValueError):Action('a','accept','p','bad','review')


def test_auth_changes_before_commit_and_after_commit():
    principal=TrustedPrincipal('issuer','subject','audience',1,1,9999999999)
    class Checker:
        def __init__(self,fail):self.calls=0; self.fail=fail
        def check(self,token):
            self.calls+=1
            if self.calls == self.fail:return AdmissionDecision(AdmissionStatus.UNKNOWN,AdmissionReason.FACTS_UNKNOWN)
            return AdmissionDecision(AdmissionStatus.ALLOWED,AdmissionReason.ACCEPTED,principal)
    r=repo(); a=action(r,proposal())
    for fail in (1,2,3):
        b=Boundary(Checker(fail),lambda p:(connect,'A'),lambda *args:True)
        with pytest.raises(Denied):b.act('synthetic',a)
        assert r.detail('trip1') is None
    b=Boundary(Checker(4),lambda p:(connect,'A'),lambda *args:True)
    with pytest.raises(Denied) as e:b.act('synthetic',a)
    assert e.value.commit_possible
    assert r.query_action('a1').committed_version == 1


def test_competing_new_trip_candidates():
    r=repo(); aa=[action(r,proposal('left'),'left'),action(r,proposal('right'),'right')]
    def run(a):
        try:return repo().act(a)
        except Conflict:return None
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(run,aa))
    assert sum(x is not None for x in results) == 1
    assert r.detail('trip1').version == 1
    assert len(r.list_trips()) == 1


def test_unknown_confirmation_is_not_authority():
    r=repo(); a=action(r,proposal())
    for result in (None,False,'true',1,{'viewed':True}):
        with pytest.raises(Denied):repo(confirm=lambda *args:result).act(a)
    assert r.query_action('a1') is None
