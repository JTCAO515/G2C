"""Stored result grammar is not authority; mutable model/source use is elsewhere."""
import hashlib,json
import unittest

from cj_memory_jobs.codec import Unavailable
from cj_memory_jobs.postgres import JobStatus
from cj_memory_jobs.publication_result import encode_result,decode_result


class PublicationResults(unittest.TestCase):
    def setUp(self):
        self.status=JobStatus('job','attempt','completed',1,'a'*64)
        self.output=b'{"version":"MEMORY-EXTRACT@1","entries":[]}'
        self.raw=encode_result(self.status,'b'*64,hashlib.sha256(self.output).hexdigest(),())

    def test_exact_original_hashes_and_empty_no_change(self):
        value=decode_result(self.raw,self.status,self.output)
        self.assertEqual(value['receipts'],[])
        self.assertEqual(value['enqueue_input_sha256'],self.status.input_sha256)
        self.assertEqual(value['model_output_sha256'],hashlib.sha256(self.output).hexdigest())

    def test_corrupt_version_identity_hash_and_fields_are_unavailable(self):
        original=json.loads(self.raw)
        for change in ({'version':'MEMORY-EXTRACT@1'},{'job_id':'other'},{'attempt_id':'replacement'},
                       {'enqueue_input_sha256':'c'*64},{'prepared_input_sha256':'bad'},
                       {'model_output_sha256':'d'*64},{'owner':'other'},{'receipts':{}}):
            with self.subTest(change=change),self.assertRaises(Unavailable):
                decode_result(json.dumps(dict(original,**change)).encode(),self.status,self.output)
        with self.assertRaises(Unavailable):decode_result(self.raw,self.status,self.output+b' ')

    def test_receipt_bounds_unique_ids_and_concrete_states(self):
        original=json.loads(self.raw)
        receipt=dict(operation_id='op',item_id='item',version=1,status='candidate',input_sha256='c'*64)
        for receipts in ([dict(receipt,version=True)],[dict(receipt,status='unknown')],
                         [dict(receipt,input_sha256='bad')],[dict(receipt,item_id='\0')],[receipt,receipt]):
            with self.subTest(receipts=receipts),self.assertRaises(Unavailable):
                decode_result(json.dumps(dict(original,receipts=receipts)).encode(),self.status,self.output)

    def test_bounded_durable_result_does_not_truncate(self):
        with self.assertRaises(ValueError):encode_result(self.status,'b'*64,'c'*64,[{'text':'x'*16384}])
