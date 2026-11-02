"""Decision codec only; no user/source authority is created by parsing."""
import json
from pathlib import Path
import unittest

from cj_memory_jobs.candidate import CandidateAction,VERSION
from cj_memory_jobs.codec import InvalidInput


def decision(**changes):
    value=dict(version=VERSION,action_id='decision-1',job_id='job',attempt_id='attempt',
        candidate_id='candidate',expected_candidate_version=1,expected_memory_epoch=2,
        operation='confirm',kind='preference',text='不吃辣',extent='long_term',context=None,
        occurred_at='date unknown')
    value.update(changes)
    return json.dumps(value,ensure_ascii=False).encode()


class CandidateActions(unittest.TestCase):
    def test_frozen_positive_and_negative_examples(self):
        root=Path(__file__).resolve().parents[3]
        examples=json.loads((root/'contracts/memory-jobs/candidate-v1-examples.json').read_bytes())
        for value in examples['positive']:
            raw=json.dumps(value,ensure_ascii=False).encode()
            with self.subTest(value=value):self.assertEqual(CandidateAction.parse(raw).raw,raw)
        for value in examples['negative']:
            with self.subTest(value=value),self.assertRaises(InvalidInput):
                CandidateAction.parse(json.dumps(value).encode())

    def test_exact_original_confirm_and_reject(self):
        raw=decision()+b'\n';value=CandidateAction.parse(raw)
        self.assertEqual(value.raw,raw);self.assertEqual((value.kind,value.context),('preference',None))
        reject=json.loads(decision())
        reject.update(operation='reject')
        for key in ('kind','text','extent','context','occurred_at'):reject.pop(key)
        value=CandidateAction.parse(json.dumps(reject).encode())
        self.assertEqual(value.operation,'reject');self.assertIsNone(value.text)

    def test_no_model_approval_owner_or_inference_promotion(self):
        for extra in ({'owner':'other'},{'confirmed':True},{'authorized':True},{'source_id':'manual:x'}):
            with self.subTest(extra=extra),self.assertRaises(InvalidInput):CandidateAction.parse(decision(**extra))
        with self.assertRaises(InvalidInput):CandidateAction.parse(decision(kind='inference'))

    def test_current_context_is_typed_explicit_and_only_comparison_data(self):
        value=CandidateAction.parse(decision(extent='current',context={'kind':'travel','id':'a'*32,'expected_version':3}))
        self.assertEqual((value.context.id,value.context.expected_version),('a'*32,3))
        for context in (None,{'kind':'legacy','id':'chat','expected_version':1},
                        {'kind':'travel','id':'a'*32,'expected_version':True}):
            with self.assertRaises(InvalidInput):CandidateAction.parse(decision(extent='current',context=context))

    def test_version_bounds_extra_keys_and_duplicates(self):
        for value in (0,True,-1,2**63):
            with self.assertRaises(InvalidInput):CandidateAction.parse(decision(expected_memory_epoch=value))
        raw=decision()
        for bad in (b'null',b'[]',raw[:-1]+b',"operation":"confirm"}',b'\xff',b'x'*32769):
            with self.assertRaises(InvalidInput):CandidateAction.parse(bad)
