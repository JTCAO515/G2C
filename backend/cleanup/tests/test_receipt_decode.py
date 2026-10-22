"""Affected parser/journal controls; original independent probes kept verbatim separately."""
import json
import unittest
import independent_receipt_checks as original_probes
from cj_cleanup.core import Repository, Invalid, Conflict


class ReceiptDecodeControls(unittest.TestCase):
    def setUp(self):
        self.probe = original_probes.IndependentReceiptChecks()
        self.probe.setUp()
        self.f, self.op, self.target = self.probe.f, self.probe.op, self.probe.target
        self.raw = self.f.result(self.op, self.target)

    def invalid_forms(self):
        yield self.raw.decode().encode('utf-16')
        yield self.raw.decode().encode('utf-32')
        yield b'\xef\xbb\xbf' + self.raw
        yield self.raw.replace(b'confirmed', b'\xff')
        yield self.raw.replace(b'"outcome":"confirmed"', b'"outcome":"unknown","outcome":"confirmed"')
        yield self.raw.replace(b'"outcome":"confirmed"', b'"outcome":"confirmed","outcome":"confirmed"')
        yield self.raw.replace(b'"outcome":"confirmed"', b'"outcome":{"value":1,"value":2}')
        yield self.raw + b' ' * 4096

    def test_invalid_input_leaves_operation_and_journal_unchanged(self):
        for raw in self.invalid_forms():
            with self.subTest(raw_digest_length=len(raw)):
                self.probe.must_reject_without_settlement(raw)

    def test_rebuild_rejects_old_invalid_stored_original_receipts(self):
        journal_before = self.f.repo.journal()
        for raw in self.invalid_forms():
            journal = json.loads(journal_before)
            journal['events'].append(dict(kind='receipt',scope=json.loads(journal_before)['events'][0]['scope'],
                operation_id=self.op.operation_id,revision=self.op.revision,target=self.target,raw=raw.hex()))
            with self.subTest(raw_digest_length=len(raw)), self.assertRaises(Invalid):
                Repository.rebuild(json.dumps(journal).encode())
            self.assertEqual(self.f.repo.journal(),journal_before)
            self.assertEqual(self.f.repo.query(self.op.scope,self.op.operation_id),self.op)

    def test_valid_noncanonical_original_bytes_and_terminal_conflict_preserved(self):
        # Whitespace is legal UTF8 JSON, and exact original bytes must survive replay.
        raw = b'  ' + self.raw + b'\n'
        op = self.f.repo.receipt(self.op.scope,self.op.operation_id,self.op.revision,self.target,raw)
        self.assertEqual(op.status,'complete')
        self.assertEqual(op.steps[-1].receipt_bytes,raw)
        rebuilt = Repository.rebuild(self.f.repo.journal())
        self.assertEqual(rebuilt.query(op.scope,op.operation_id),op)
        same = rebuilt.receipt(op.scope,op.operation_id,op.revision,self.target,raw)
        self.assertEqual(same,op)
        journal = rebuilt.journal()
        with self.assertRaises(Conflict):
            rebuilt.receipt(op.scope,op.operation_id,op.revision,self.target,self.raw)
        self.assertEqual(rebuilt.journal(),journal)


if __name__ == '__main__': unittest.main(verbosity=2)
