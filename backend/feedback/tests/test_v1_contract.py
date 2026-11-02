"""Additive FEEDBACK@1.0 examples use the existing exact-byte Action boundary."""
from pathlib import Path
import json
import unittest
from cj_feedback.domain import Action,InvalidInput

EXAMPLES=Path(__file__).resolve().parents[3]/'contracts/feedback/examples'


class FeedbackV1Examples(unittest.TestCase):
    def test_positive(self):
        for value in json.loads((EXAMPLES/'v1-positive.json').read_text()):
            original=json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.assertEqual(Action(original).original,original)

    def test_negative(self):
        for value in json.loads((EXAMPLES/'v1-negative.json').read_text()):
            with self.subTest(reason=value['reason']),self.assertRaises(InvalidInput):
                Action(json.dumps(value['action']).encode('utf-8'))
