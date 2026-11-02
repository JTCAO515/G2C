"""Frozen examples test grammar only; no example establishes collection authority."""
import json
from pathlib import Path
import unittest

from cj_memory_jobs.codec import InvalidInput
from cj_memory_jobs.consent import ConsentAction, EnqueueCommand


class PGContract(unittest.TestCase):
    def test_positive_and_negative_examples(self):
        root=Path(__file__).resolve().parents[3]
        examples=json.loads((root/'contracts/memory-jobs/pg-v1-examples.json').read_bytes())
        codecs={'consent':ConsentAction.parse,'enqueue':EnqueueCommand.parse}
        for case in examples['positive']:
            raw=json.dumps(case['value'],ensure_ascii=False).encode()
            with self.subTest(case=case):
                self.assertEqual(codecs[case['codec']](raw).raw,raw)
        for case in examples['negative']:
            with self.subTest(case=case), self.assertRaises(InvalidInput):
                codecs[case['codec']](json.dumps(case['value']).encode())
