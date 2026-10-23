"""Fixed NEEDS4cc9 strict reader -> CJ035 entry, real NEW private noTCP PG.

Reuse only the old test fixture setup; explicit tests below exercise new entry.
No replay of the old 12 methods or solver/route suites.
"""
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from cj_needs.protected_read import ProtectedReader, ReadConfiguration
from cj_auth.read_context import ProtectedReadBoundary
from cj_auth.interfaces import Fact
from cj_feasibility.current_read import ReadLimits, ReadWithheld
from cj_feasibility.protected_current import CurrentNeedsRead
from test_current_read import PrivateReadTests, LIMITS, known


class ProtectedCurrentTests(unittest.TestCase):
    setUpClass=classmethod(PrivateReadTests.setUpClass.__func__)
    run_pg=classmethod(PrivateReadTests.run_pg.__func__)
    raw_connect=classmethod(PrivateReadTests.raw_connect.__func__)
    stop_cluster=classmethod(PrivateReadTests.stop_cluster.__func__)
    seed=PrivateReadTests.seed

    def setUp(self):
        PrivateReadTests.setUp(self)
        self.remapped=False
        def resolve(principal,environment):
            if environment!='synthetic-env':raise RuntimeError('unconfigured synthetic environment')
            return self.connect,self.scope_a if principal.subject=='synthetic-a' and not self.remapped else self.scope_b
        self.strict=ProtectedReader(self.auth,resolve,configuration=ReadConfiguration(
            'synthetic-env','synthetic-cj035','cj-read-test',LIMITS.max_output_bytes))
        self.entry=CurrentNeedsRead(self.strict,LIMITS)
    def read(self,needs_id='synthetic-needs',limits=LIMITS,observer=None):
        if observer is not None:raise ValueError('no request projector hook')
        return CurrentNeedsRead(self.strict,limits).read('synthetic-only',needs_id)
    def test_new_success_current_history_exact_bytes_and_bilingual(self):
        before=None
        with self.raw_connect() as conn:
            before=conn.execute('SELECT count(*) FROM cj_needs_revision').fetchone()
        raw=self.entry.read('synthetic-only','synthetic-needs')
        self.assertIs(type(raw),bytes)
        body=json.loads(raw)
        self.assertEqual((body['status'],body['overall'],body['revision']),('CONFLICT','UNKNOWN',2))
        self.assertEqual([s['revision'] for s in body['sources']],[1,2])
        self.assertTrue(all(c['zh'] and c['en'] for c in body['checks']))
        self.assertEqual(self.opened,4);self.assertEqual(self.closed,4)
        with self.raw_connect() as conn:self.assertEqual(before,conn.execute('SELECT count(*) FROM cj_needs_revision').fetchone())
    def test_original_close_exception_fail_now_withholds_at_first_close(self):
        self.close_error=True
        with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(self.opened,1);self.assertEqual(self.closed,1)
    def test_original_close_scope_remap_fail_now_withholds_at_first_close(self):
        self.close_hook=lambda count:setattr(self,'remapped',True)
        with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(self.opened,1);self.assertEqual(self.closed,1)
    def test_close_configuration_environment_change_withheld_first_close(self):
        self.close_hook=lambda count:setattr(self.strict,'configuration',replace(self.strict.configuration,environment='changed-env'))
        with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(self.closed,1)
    def test_new_history_and_input_output_bounds(self):
        for limits,code in [(ReadLimits(1,1000000,100000),'REVISION_BOUND_EXCEEDED'),
                            (ReadLimits(10,1,100000),'INPUT_BOUND_EXCEEDED'),
                            (ReadLimits(10,1000000,1),'OUTPUT_BOUND_EXCEEDED')]:
            with self.subTest(code=code):
                with self.assertRaises(ReadWithheld) as failure:self.read(limits=limits)
                self.assertEqual(failure.exception.code,code)
    def test_version_advance_during_history_is_withheld(self):
        def correct(count):
            if count==3:
                self.close_hook=None
                self.seed({'party_size':known(4)},version=2)
        self.close_hook=correct
        with self.assertRaises(ReadWithheld) as failure:self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(failure.exception.code,'CURRENT_RECORD_OR_BINDING_CHANGED')

    def test_new_missing_chain_withheld(self):
        with self.raw_connect() as conn:conn.execute('DELETE FROM cj_needs_revision WHERE scope=%s AND version=1',(self.scope_a,))
        with self.assertRaises(ReadWithheld) as failure:self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(failure.exception.code,'REVISION_CHAIN_UNAVAILABLE')
    def test_new_wrong_owner_and_absence_same_refusal(self):
        with self.assertRaises(ReadWithheld) as absent:self.entry.read('synthetic-only','absent')
        self.identity.subject='synthetic-b'
        with self.assertRaises(ReadWithheld) as other:self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(absent.exception.code,other.exception.code)
    def test_default_and_unknown_configuration_closed_before_io(self):
        with self.assertRaises(ReadWithheld):CurrentNeedsRead().read('synthetic-only','synthetic-needs')
        self.identity.fact=Fact.UNKNOWN
        with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(self.opened,0)
    def test_final_canonical_admission_revocation_withholds_after_encoding(self):
        # Arm only after project_current returned complete bytes. Two guards from
        # serialized_return surround its resolver; the third is AUTH final check.
        from cj_feasibility import protected_current
        original=protected_current.project_current
        original_evaluate=self.identity.evaluate
        armed={'value':False,'calls':0}
        def project(*args,**kwargs):
            result=original(*args,**kwargs)
            armed['value']=True
            return result
        def facts(principal):
            if armed['value']:
                armed['calls']+=1
                if armed['calls']==3:self.identity.fact=Fact.NO
            return original_evaluate(principal)
        self.identity.evaluate=facts
        with patch.object(protected_current,'project_current',project):
            with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(armed['calls'],3);self.assertEqual(self.closed,4)
    def test_final_auth_callback_configuration_change_not_released(self):
        from cj_feasibility import protected_current
        original=protected_current.project_current;original_evaluate=self.identity.evaluate
        armed={'value':False,'calls':0}
        def project(*args,**kwargs):
            result=original(*args,**kwargs);armed['value']=True;return result
        def facts(principal):
            if armed['value']:
                armed['calls']+=1
                if armed['calls']==3:self.strict.configuration=replace(self.strict.configuration,max_response_bytes=1)
            return original_evaluate(principal)
        self.identity.evaluate=facts
        with patch.object(protected_current,'project_current',project):
            with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
        self.assertEqual(armed['calls'],3);self.assertEqual(self.closed,4)
    def test_producer_and_outer_caps_apply_to_full_projection(self):
        self.strict.configuration=replace(self.strict.configuration,max_response_bytes=1)
        with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')
        self.strict.configuration=replace(self.strict.configuration,max_response_bytes=LIMITS.max_output_bytes)
        self.strict.auth=ProtectedReadBoundary(self.checker,max_response_bytes=1)
        with self.assertRaises(Exception):self.entry.read('synthetic-only','synthetic-needs')


if __name__=='__main__':unittest.main()
