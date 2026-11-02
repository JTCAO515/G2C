"""CLEANUP@1.0 frozen examples and strict boundary/binding controls."""
from pathlib import Path
import json
import unittest

from cj_cleanup.core import Conflict, Invalid, encode
from cj_cleanup.hooks import HookRequest, HookReceipt, make_receipt

ROOT = Path(__file__).resolve().parents[3] / "contracts/cleanup/examples"


class HookContractTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads((ROOT / "v1-positive.json").read_text())[0]["request"]
        self.raw = encode(self.value)
        self.request = HookRequest.from_bytes(self.raw)

    def test_positive_examples(self):
        for example in json.loads((ROOT / "v1-positive.json").read_text()):
            request = HookRequest.from_bytes(encode(example["request"]))
            for outcome in ("confirmed", "unknown", "failed"):
                result = make_receipt(request, outcome)
                self.assertEqual(result.request_digest, request.digest)
                self.assertEqual(result.outcome, outcome)

    def test_negative_examples(self):
        for example in json.loads((ROOT / "v1-negative.json").read_text()):
            with self.subTest(example["reason"]), self.assertRaises(Invalid):
                HookRequest.from_bytes(encode(example["request"]))

    def test_receipt_bound_to_exact_bytes_scope_selection_and_invocation(self):
        receipt = make_receipt(self.request, "confirmed").original_utf8
        for field, replacement in (("domain_scope", "other-owner"), ("invocation_id", "other-call"), ("operation_id", "other-operation"), ("entry_digest", "4" * 64)):
            changed = HookRequest.from_bytes(encode(dict(self.value, **{field: replacement})))
            with self.subTest(field), self.assertRaises(Conflict):
                HookReceipt.from_bytes(receipt, changed)
        with self.assertRaises(Conflict):
            HookReceipt.from_bytes(receipt, HookRequest.from_bytes(self.raw + b" "))

    def test_request_json_boundary(self):
        for raw in (self.raw.decode().encode("utf-16"), b"\xef\xbb\xbf" + self.raw,
                    self.raw[:-1] + b',"operation_id":"other"}',
                    self.raw.replace(b'"kind":"memory"', b'"kind":"memory","kind":"account"'),
                    b"[]", b"{" + b" " * 16384 + b"}"):
            with self.subTest(raw=raw[:20]), self.assertRaises(Invalid):
                HookRequest.from_bytes(raw)

    def test_receipt_json_boundary(self):
        value = dict(protocol="CLEANUP@1.0", request_digest=self.request.digest, outcome="confirmed")
        for raw in (encode(dict(value, content="private")), encode(dict(value, outcome="accepted")),
                    encode(value)[:-1] + b',"outcome":"confirmed"}', b"\xef\xbb\xbf" + encode(value)):
            with self.assertRaises(Invalid):
                HookReceipt.from_bytes(raw, self.request)

    def test_no_scope_content_in_repr(self):
        self.assertNotIn("synthetic-scope", repr(self.request))


if __name__ == "__main__":
    unittest.main()
