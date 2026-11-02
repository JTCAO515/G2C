import unittest
from cj_cleanup.capabilities import Issuer,CapabilityUnavailable


class CleanupCapabilities(unittest.TestCase):
    def setUp(self):
        self.now=1000
        self.issuer=Issuer(keys={'test-key':b'synthetic-test-key-material-00000'},active_key_id='test-key',
            lifetime_seconds=60,clock=lambda:self.now)
        self.values=dict(subject_digest='1'*64,operation_id='original',binding_id='device1',purpose='progress')

    def test_exact_original_and_purpose(self):
        token=self.issuer.issue(**self.values)
        claim=self.issuer.verify(token,purpose='progress',operation_id='original',binding_id='device1')
        self.assertEqual(claim.subject_digest,'1'*64)
        for changes in ({'purpose':'device'},{'operation_id':'other'},{'binding_id':'other'}):
            with self.assertRaises(CapabilityUnavailable):
                self.issuer.verify(token,**dict(purpose='progress',operation_id='original',binding_id='device1',**{})|changes)

    def test_tamper_expired_wrong_key_and_future(self):
        token=self.issuer.issue(**self.values)
        with self.assertRaises(CapabilityUnavailable):self.issuer.verify(token[:-2]+'AA',purpose='progress')
        wrong=Issuer(keys={'test-key':b'other-synthetic-test-key-00000000'},active_key_id='test-key',lifetime_seconds=60,clock=lambda:self.now)
        with self.assertRaises(CapabilityUnavailable):wrong.verify(token,purpose='progress')
        self.now=1060
        with self.assertRaises(CapabilityUnavailable):self.issuer.verify(token,purpose='progress')
        self.now=999
        with self.assertRaises(CapabilityUnavailable):self.issuer.verify(token,purpose='progress')

    def test_device_receipt_bound_to_original_invocation(self):
        token=self.issuer.issue(**(self.values|dict(purpose='device_receipt',invocation_id='call1')))
        self.issuer.verify(token,purpose='device_receipt',operation_id='original',binding_id='device1',invocation_id='call1')
        with self.assertRaises(CapabilityUnavailable):self.issuer.verify(token,purpose='device_receipt',invocation_id='call2')
