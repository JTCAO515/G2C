"""Actual fixed AUTH gate + synthetic facts + actual task-private PG repository."""
import unittest, uuid
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import TrustedPrincipal, VerificationResult, VerificationStatus, CJAccessFacts, Fact
from cj_message.auth_boundary import Boundary, AccessBlocked
from cj_message.postgres import Repository
from check_history_postgres import connect, provision

class HistoryGateTests(unittest.TestCase):
    def setUp(self):
        self.scope='gate-history-'+uuid.uuid4().hex; provision(self.scope)
        self.p=TrustedPrincipal('https://synthetic.invalid','a','synthetic',1,1,100)
        self.invited=Fact.YES; self.calls=0; self.deny_at=None; self.resolved=0
        test=self
        class Verifier:
            def verify(self,token): return VerificationResult(VerificationStatus.VALID,test.p)
        class Access:
            def evaluate(self,p):
                test.calls+=1
                return CJAccessFacts(p,Fact.YES,Fact.YES,Fact.NO if test.calls==test.deny_at else test.invited)
        def resolve(p):
            self.resolved+=1; return Repository(connect,self.scope)
        self.boundary=Boundary(AdmissionChecker(Verifier(),Access(),clock=lambda:50),resolve,lambda:'unused')

    def test_allowed_reads_and_denied_unknown_never_resolve(self):
        self.assertEqual(len(self.boundary.conversations('synthetic')[0]),3)
        self.boundary.save_draft('synthetic','a','g-a',b'private synthetic draft',0)
        self.assertEqual(self.boundary.read_draft('synthetic','a','g-a').revision,1)
        self.assertEqual(self.boundary.message_history('synthetic','a'),([],None))
        count=self.resolved
        for fact in (Fact.NO,Fact.UNKNOWN):
            self.invited=fact
            for fn in (lambda:self.boundary.conversations('synthetic'),
                       lambda:self.boundary.message_history('synthetic','a'),
                       lambda:self.boundary.read_draft('synthetic','a','g-a'),
                       lambda:self.boundary.save_draft('synthetic','a','g-a',b'blocked',1)):
                with self.assertRaises(AccessBlocked): fn()
        self.assertEqual(self.resolved,count)

    def test_commit_boundary_revocation_rolls_back_actual_draft(self):
        self.deny_at=3
        with self.assertRaises(AccessBlocked): self.boundary.save_draft('synthetic','a','g-a',b'blocked',0)
        self.deny_at=None
        self.assertIsNone(self.boundary.read_draft('synthetic','a','g-a'))
