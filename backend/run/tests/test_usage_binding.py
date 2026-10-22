import hashlib
import json
import unittest
from dataclasses import replace
from cj_run.core import Binding, Service, Conflict
from cj_run.fixture import MemoryRepository
from cj_run.usage_binding import UsageBinding


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.input=b'{ "fixture" : "original" }\n'
        self.values=dict(attempt_id='a',operation_id='o',run_id='r',kind='model',
                         input_digest=hashlib.sha256(self.input).hexdigest(),reserve=2,output_limit=3)
        self.usage=UsageBinding(json.dumps(self.values).encode(),self.input)
        self.b=Binding('scope','chat','g','m','r',1)
        self.s=Service(MemoryRepository())

    def test_atomic_binding_and_exact_replay(self):
        state=self.s.accept_with_usage(self.b,self.usage)
        self.assertEqual(state.usage.command_bytes,self.usage.command_bytes)
        self.assertEqual(state.usage.input_bytes,self.input)
        self.assertEqual(self.s.accept_with_usage(self.b,self.usage),state)
        with self.assertRaises(Conflict): self.s.accept_with_usage(self.b,self.usage,require_new=True)

    def test_old_unbound_cannot_backfill(self):
        self.s.accept(self.b)
        with self.assertRaises(Conflict): self.s.accept_with_usage(self.b,self.usage)
        self.assertIsNone(self.s.snapshot(self.b).usage)

    def test_changed_fields_and_original_bytes_rejected(self):
        self.s.accept_with_usage(self.b,self.usage)
        for key,value in [('attempt_id','new'),('operation_id','new'),('kind','tool'),('reserve',4),('output_limit',4)]:
            with self.subTest(key=key):
                changed=UsageBinding(json.dumps(dict(self.values,**{key:value})).encode(),self.input)
                with self.assertRaises(Conflict): self.s.accept_with_usage(self.b,changed)
        changed_input=self.input+b' '
        changed=UsageBinding(json.dumps(dict(self.values,input_digest=hashlib.sha256(changed_input).hexdigest())).encode(),changed_input)
        with self.assertRaises(Conflict): self.s.accept_with_usage(self.b,changed)
        # Same values but different stored command encoding also cannot overwrite bytes.
        changed=UsageBinding(json.dumps(self.values,indent=2).encode(),self.input)
        with self.assertRaises(Conflict): self.s.accept_with_usage(self.b,changed)

    def test_digest_run_and_format_validation(self):
        with self.assertRaises(ValueError): UsageBinding(self.usage.command_bytes,self.input+b' ')
        with self.assertRaises(ValueError): self.s.accept_with_usage(replace(self.b,run_id='different'),self.usage)
        for key,value in [('attempt_id',''),('operation_id','x'*201),('reserve',True),('output_limit',0),('input_digest','A'*64)]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError): UsageBinding(json.dumps(dict(self.values,**{key:value})).encode(),self.input)
        raw=self.usage.command_bytes[:-1]+b', "attempt_id": "a"}'
        with self.assertRaises(ValueError): UsageBinding(raw,self.input)
