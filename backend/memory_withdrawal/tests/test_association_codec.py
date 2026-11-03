"""External persisted association validation, not cleanup authority fixtures."""
import json,unittest
from hashlib import sha256

from cj_cleanup.core import Denied,encode
from cj_cleanup.hooks_v1_1 import Selection,make_request
from cj_memory_withdrawal.association_codec import VERSION,parse_original


class AssociationCodecTests(unittest.TestCase):
    def setUp(self):
        self.scope='trusted-scope'
        self.request=make_request(operation_id='original',invocation_id='original-step',subject_digest='a'*64,
            registry_digest='b'*64,entry_digest='c'*64,target='business/message',domain_scope=self.scope,
            selection=Selection('memory','原条目',3,5))
        self.value=dict(version=VERSION,operation_id='original',subject_digest='a'*64,
            memory_scope_digest=sha256(self.scope.encode()).hexdigest(),selection=self.request.selection.to_dict(),
            original_selection=dict(item_id='原条目',item_version=2,scope_epoch=4),
            source_refs=[dict(source_id='source',source_version=1)],operation_refs=[dict(operation_id='save',input_sha256='d'*64)],
            message_refs=[dict(conversation_id='chat',generation='generation',sequence=1,message_id='message',input_sha256='e'*64)],
            job_refs=[dict(job_id='job',attempt_id='attempt',original_input_sha256='f'*64,state='unknown')],
            decision_source_sha256s=['1'*64],derived_range=dict(kind='owned_trip_derived_scope',precise_item_match=False,preserve_formal_trips=True))

    def test_original_binding_and_complete_reference_coordinates(self):
        raw=encode(self.value)
        self.assertEqual(parse_original(raw,self.request,self.scope),self.value)
        for change in (dict(operation_id='other'),dict(subject_digest='0'*64),dict(memory_scope_digest='0'*64),
                       dict(version='MEMORY-ERASURE-ASSOCIATION-DRAFT@2'),dict(source_refs=[]),
                       dict(derived_range=dict(kind='whole_account')),dict(unapproved_actor=True)):
            with self.subTest(change=change),self.assertRaises(Denied):
                parse_original(encode(dict(self.value,**change)),self.request,self.scope)

    def test_corrupt_partial_duplicate_or_implicit_reference_is_denied(self):
        for field,rows in (
            ('message_refs',[dict(self.value['message_refs'][0],input_sha256='not-original')]),
            ('message_refs',[dict(self.value['message_refs'][0],sequence=True)]),
            ('message_refs',[dict(conversation_id='chat')]),
            ('source_refs',self.value['source_refs']*2),
            ('operation_refs',[dict(operation_id='save',input_sha256='A'*64)]),
            ('job_refs',[dict(self.value['job_refs'][0],state='success')]),
            ('decision_source_sha256s',['1'*64,'1'*64]),
        ):
            with self.subTest(field=field,rows=rows),self.assertRaises(Denied):
                parse_original(encode(dict(self.value,**{field:rows})),self.request,self.scope)
        with self.assertRaises(Denied):parse_original(b'{"version":1,"version":2}',self.request,self.scope)
        with self.assertRaises(Denied):parse_original(b' '*1_000_001,self.request,self.scope)

    def test_documented_association_bound_exceeds_command_decoder_bound(self):
        value=dict(self.value,source_refs=[dict(source_id=str(i)+'x'*400,source_version=1) for i in range(100)])
        raw=encode(value);self.assertGreater(len(raw),32768)
        self.assertEqual(parse_original(raw,self.request,self.scope),value)


if __name__=='__main__':unittest.main()
