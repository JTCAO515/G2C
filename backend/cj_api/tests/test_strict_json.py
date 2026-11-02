"""Shared duplicate-key hook keeps each boundary's own failure."""
import json
import unittest

from cj_strict_json import reject_duplicates


class Refused(Exception):
    pass


class RejectDuplicatesTests(unittest.TestCase):
    def test_unique_members_decode_unchanged(self):
        hook = reject_duplicates(Refused, 'duplicate')
        self.assertEqual(json.loads('{"a":1,"b":{"c":[{"a":2}]}}', object_pairs_hook=hook),
                         {'a': 1, 'b': {'c': [{'a': 2}]}})

    def test_repeated_key_raises_the_callers_failure(self):
        hook = reject_duplicates(Refused, 'duplicate')
        for raw in ('{"a":1,"a":2}', '{"x":{"a":1,"a":1}}', '[{"a":1,"a":2}]'):
            with self.assertRaises(Refused) as caught:
                json.loads(raw, object_pairs_hook=hook)
            self.assertEqual(caught.exception.args, ('duplicate',))

    def test_failure_without_message(self):
        with self.assertRaises(Refused) as caught:
            json.loads('{"a":1,"a":2}', object_pairs_hook=reject_duplicates(Refused))
        self.assertEqual(caught.exception.args, ())

    def test_failures_are_not_shared_between_raises(self):
        hook = reject_duplicates(Refused, 'duplicate')
        seen = []
        for _ in range(2):
            with self.assertRaises(Refused) as caught:
                json.loads('{"a":1,"a":2}', object_pairs_hook=hook)
            seen.append(caught.exception)
        self.assertIsNot(*seen)
