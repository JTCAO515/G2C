"""Opaque wire refs decode back to exact original evidence, never authority."""
from dataclasses import replace
import hashlib,json
import unittest

from cj_memory_jobs.extraction import CollectionPolicy,InvalidExtraction,publication_identity,parse_output as parse_v1
from cj_memory_jobs.model_v2 import reference,parse_output,decode_output
from test_extraction_boundary import source_message


class OpaqueModelOutput(unittest.TestCase):
    def setUp(self):
        self.scope='scope'
        self.message=source_message('不吃辣 / no spicy food')
        self.policy=CollectionPolicy(frozenset({'self'}),frozenset({'diet.spicy'}),5,4096,
            lambda entry:True,lambda entry,rows:entry.text=='不吃辣')
        self.entry=dict(subject='self',slot='diet.spicy',kind='preference',text='不吃辣',extent='long_term',
            occurred_at='date unknown',evidence=[dict(ref=reference(self.scope,self.message),quote='不吃辣')])

    def raw(self,entry=None,**changes):
        value=dict(version='MEMORY-EXTRACT@2',entries=[self.entry if entry is None else entry]);value.update(changes)
        return json.dumps(value,ensure_ascii=False).encode()

    def test_wire_reference_maps_to_original_identity_across_versions(self):
        current=parse_output(self.raw(),(self.message,),self.policy,self.scope)[0]
        old=dict(self.entry,evidence=[dict(message_id=self.message.receipt.message_id,quote='不吃辣')])
        legacy=parse_v1(json.dumps(dict(version='MEMORY-EXTRACT@1',entries=[old]),ensure_ascii=False).encode(),(self.message,),self.policy)[0]
        self.assertEqual(current,legacy)
        self.assertEqual(publication_identity(self.scope,current.entry,(self.message,),None),
                         publication_identity(self.scope,legacy.entry,(self.message,),None))

    def test_no_legacy_fallback_or_masked_foreign_reference(self):
        for evidence in ([dict(message_id=self.message.receipt.message_id,quote='不吃辣')],
                         [dict(ref='message-v2:'+'0'*64,quote='不吃辣')]):
            with self.assertRaises(InvalidExtraction):parse_output(self.raw(dict(self.entry,evidence=evidence)),(self.message,),self.policy,self.scope)
        with self.assertRaises(InvalidExtraction):parse_output(self.raw(version='MEMORY-EXTRACT@1'),(self.message,),self.policy,self.scope)
        with self.assertRaises(InvalidExtraction):parse_output(self.raw(),(),self.policy,self.scope)
        with self.assertRaises(InvalidExtraction):decode_output(self.raw(),(self.message,),self.scope+'-other')

    def test_original_large_id_is_not_recounted_as_model_output(self):
        identifier='原'*9000
        original=json.loads(self.message.original_utf8);original['message_id']=identifier
        original_bytes=json.dumps(original,ensure_ascii=False).encode()
        row=replace(self.message,original_utf8=original_bytes,
            receipt=replace(self.message.receipt,message_id=identifier,input_sha256=hashlib.sha256(original_bytes).hexdigest()))
        entry=dict(self.entry,evidence=[dict(ref=reference(self.scope,row),quote='不吃辣')])
        raw=self.raw(entry)
        self.assertLess(len(raw),16384)
        value=parse_output(raw,(row,),self.policy,self.scope)[0]
        self.assertEqual(value.entry.evidence[0].message_id,row.receipt.message_id)

    def test_data_decode_does_not_create_confirmation_or_scope(self):
        value=decode_output(self.raw(dict(self.entry,kind='inference')),(self.message,),self.scope)[0]
        self.assertEqual(value.kind,'inference')
        for extra in ({'owner':'other'},{'confirmed':True},{'context':{'id':'other'}}):
            with self.assertRaises(InvalidExtraction):parse_output(self.raw(dict(self.entry,**extra)),(self.message,),self.policy,self.scope)
