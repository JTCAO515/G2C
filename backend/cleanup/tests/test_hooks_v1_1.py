"""C's legal MEMORY IDs must be selectable without altering frozen V1 behavior."""
import json
import unittest
from cj_cleanup import hooks as v1, hooks_v1_1 as v11
from cj_cleanup.core import Invalid,Conflict


class UnicodeMemoryHookTests(unittest.TestCase):
    def request(self,item,**changes):
        values=dict(operation_id='original',invocation_id='call-1',subject_digest='1'*64,
            registry_digest='2'*64,entry_digest='3'*64,target='business/memory-authoritative',
            domain_scope='synthetic',selection=v11.Selection('memory',item,1,1))
        values.update(changes)
        return v11.make_request(**values)

    def test_current_memory_unicode_long_and_exact_spelling(self):
        for item in ('北京偏好-🙂','  保留原样  ','é','e\u0301','🙂'*4096):
            with self.subTest(item=item[:12]):
                value=self.request(item)
                self.assertEqual(value.selection.item_id,item)
                self.assertEqual(v11.HookRequest.from_bytes(value.original_utf8).selection.item_id,item)
                self.assertEqual(v11.make_receipt(value,'confirmed').request_digest,value.digest)
        self.assertNotEqual(self.request('é').digest,self.request('e\u0301').digest)

    def test_maximum_utf8_and_ascii_escaped_requests(self):
        value=self.request('🙂'*4096,domain_scope='\x01'*4096)
        self.assertGreater(len(value.original_utf8),65536)
        literal=json.dumps(json.loads(value.original_utf8),ensure_ascii=False).encode('utf-8')
        self.assertGreater(len(literal),16384)
        self.assertEqual(v11.HookRequest.from_bytes(literal).selection.item_id,'🙂'*4096)
        self.assertNotEqual(value.digest,v11.HookRequest.from_bytes(literal).digest)

    def test_memory_negative_examples(self):
        for item in ('','  ','中'*4097,'nul\0value','\ud800'):
            with self.subTest(item=repr(item[:12])),self.assertRaises(Invalid):self.request(item)
        with self.assertRaises(Invalid):self.request('合法',operation_id='非法调用ID')

    def test_explicit_version_and_exact_original_receipt_binding(self):
        value=self.request('合法')
        receipt=v11.make_receipt(value,'confirmed')
        with self.assertRaises(Invalid):v1.HookRequest.from_bytes(value.original_utf8)
        with self.assertRaises(Invalid):v1.HookReceipt.from_bytes(receipt.original_utf8,value)
        with self.assertRaises(Invalid):v11.HookReceipt.from_bytes(v1.make_receipt(value,'confirmed').original_utf8,value)
        with self.assertRaises(Conflict):v11.HookReceipt.from_bytes(receipt.original_utf8,self.request('另一个'))
        # Existing V1 grammar remains strict; it is not silently widened.
        old=json.loads(value.original_utf8);old['protocol']=v1.VERSION
        with self.assertRaises(Invalid):v1.HookRequest.from_bytes(json.dumps(old).encode())


if __name__=='__main__':unittest.main()
