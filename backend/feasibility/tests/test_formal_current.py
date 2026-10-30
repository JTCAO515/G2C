"""Canonical component/owner-PG probes, not B305 signed runtime-role acceptance."""
import json
import unittest

from cj_needs.protected_read import ProtectedReader,ReadConfiguration
from cj_feasibility.current_read import ReadLimits,ReadWithheld
from cj_feasibility.formal_current import CurrentFormalNeedsRead,FormalReadLimits,VERSION
from cj_auth.interfaces import Fact
import test_current_read as read_fixture
from test_current_read import LIMITS,known

FORMAL_LIMITS=FormalReadLimits(LIMITS,2_000_000)


class FormalCurrentChecks(unittest.TestCase):
    setUpClass=classmethod(read_fixture.PrivateReadTests.setUpClass.__func__)
    run_pg=classmethod(read_fixture.PrivateReadTests.run_pg.__func__)
    raw_connect=classmethod(read_fixture.PrivateReadTests.raw_connect.__func__)
    stop_cluster=classmethod(read_fixture.PrivateReadTests.stop_cluster.__func__)
    seed=read_fixture.PrivateReadTests.seed

    def setUp(self):
        read_fixture.PrivateReadTests.setUp(self)
        def resolve(principal,environment):
            if environment!='synthetic-env':raise RuntimeError('fixed synthetic environment required')
            return self.connect,self.scope_a if principal.subject=='synthetic-a' else self.scope_b
        self.strict=ProtectedReader(self.auth,resolve,configuration=ReadConfiguration(
            'synthetic-env','synthetic-cj035','cj-read-test',LIMITS.max_output_bytes))
        self.entry=CurrentFormalNeedsRead(self.strict,FORMAL_LIMITS)

    def test_formal_current_preserves_original_history_and_bilingual_conflict(self):
        raw=self.entry.read('synthetic-only','synthetic-needs')
        value=json.loads(raw)
        self.assertEqual(value['version'],VERSION)
        self.assertEqual(value['evaluator_version'],'FEASIBILITY@1.0')
        self.assertEqual(value['input_profile'],'CJ-FEASIBILITY-FORMAL-INPUTS@1')
        self.assertEqual((value['status'],value['overall'],value['revision']),('CONFLICT','UNKNOWN',2))
        self.assertEqual([r['revision'] for r in value['sources']],[1,2])
        self.assertTrue(all(c['zh'] and c['en'] for c in value['checks']))
        self.assertEqual((self.opened,self.closed),(4,4))

    def test_formal_bounds_and_missing_configuration_cannot_succeed_empty(self):
        with self.assertRaises(ReadWithheld):CurrentFormalNeedsRead().read('synthetic-only','synthetic-needs')
        for limits in (FormalReadLimits(ReadLimits(1,1_000_000,100_000),2_000_000),
                       FormalReadLimits(LIMITS,1),FormalReadLimits(ReadLimits(10,1_000_000,1),2_000_000)):
            with self.subTest(limits=limits),self.assertRaises(ReadWithheld):
                CurrentFormalNeedsRead(self.strict,limits).read('synthetic-only','synthetic-needs')

    def test_source_advance_during_history_never_returns_old_current_report(self):
        def correct(count):
            if count==3:
                self.close_hook=None
                self.seed({'party_size':known(4)},version=2)
        self.close_hook=correct
        with self.assertRaises(ReadWithheld):self.entry.read('synthetic-only','synthetic-needs')

    def test_final_auth_revocation_or_close_failure_withholds_private_bytes(self):
        self.close_error=True
        with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
        self.close_error=False
        def revoke(count):self.identity.fact=Fact.UNKNOWN
        self.close_hook=revoke
        with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
