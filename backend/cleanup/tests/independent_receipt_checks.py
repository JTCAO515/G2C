import unittest
import test_cleanup as fixtures
from cj_cleanup.core import Invalid

class IndependentReceiptChecks(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.CleanupTests(); self.f.setUp()
        op = self.f.op(True)
        for step in op.steps[:-1]: op = self.f.settle(op, step.target)
        self.target = op.steps[-1].target
        self.op = self.f.repo.intent(op.scope, op.operation_id, op.revision, self.target, 'last-original-invocation')

    def must_reject_without_settlement(self, raw):
        before = self.f.repo.journal()
        try:
            result = self.f.repo.receipt(self.op.scope, self.op.operation_id, self.op.revision, self.target, raw)
        except Invalid:
            self.assertEqual(self.f.repo.query(self.op.scope, self.op.operation_id), self.op)
            self.assertEqual(self.f.repo.journal(), before)
            return
        self.fail('Invalid protocol receipt accepted; final operation status=' + result.status)

    def test_ambiguous_unknown_and_confirmed_outcomes_cannot_complete(self):
        raw = self.f.result(self.op, self.target)
        self.assertIn(b'"outcome":"confirmed"', raw)
        ambiguous = raw.replace(b'"outcome":"confirmed"', b'"outcome":"unknown","outcome":"confirmed"')
        self.must_reject_without_settlement(ambiguous)

    def test_non_utf8_receipt_cannot_complete(self):
        raw = self.f.result(self.op, self.target).decode('utf-8').encode('utf-16')
        self.assertTrue(raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'))
        self.must_reject_without_settlement(raw)

if __name__ == '__main__': unittest.main(verbosity=2)
