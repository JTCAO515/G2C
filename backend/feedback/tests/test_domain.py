import json
import unittest
from cj_feedback import Action, InvalidInput


def raw(aid='one', **changes):
    value = dict(action_id=aid, problem='回答有误 / incorrect answer', expectation='希望提供来源 / sources please', references=[])
    value.update(changes)
    return json.dumps(value, ensure_ascii=False).encode()


class DomainTests(unittest.TestCase):
    def test_original_bytes_not_normalized(self):
        original = raw()
        self.assertEqual(Action(original).original, original)
        self.assertNotEqual(Action(original).digest, Action(b' '+original).digest)

    def test_reject_untrusted_diagnostics_owner_and_content(self):
        for key in ('owner', 'scope', 'model_version', 'rule_version', 'usage', 'duration', 'tool_result', 'failure_stage', 'token', 'chat', 'memory'):
            with self.subTest(key=key), self.assertRaises(InvalidInput):
                Action(raw(**{key:'not-authoritative'}))

    def test_reject_unimplemented_reference_types(self):
        for kind in ('trip', 'memory', 'proposal', 'other'):
            with self.subTest(kind=kind), self.assertRaises(InvalidInput):
                Action(raw(references=[dict(kind=kind,id='one')]))

    def test_only_minimal_known_reference_shapes(self):
        Action(raw(references=[dict(kind='message',id='m1'),dict(kind='run',id='r1')]))
        for refs in ([dict(kind='run',id='r')], [dict(kind='run',id='r',model='claimed')], [dict(kind='run',id='r')]*2, [dict(kind=[],id='r')]):
            with self.assertRaises(InvalidInput): Action(raw(references=refs))

    def test_malformed_and_duplicate_keys(self):
        for value in (b'[]', b'null', b'\xff', raw()+b'x', b'{"action_id":"a","action_id":"b"}', b'['*2000):
            with self.subTest(value=value[:40]), self.assertRaises(InvalidInput): Action(value)

    def test_limits_and_private_repr(self):
        for changes in (dict(problem=' '),dict(problem='\x00'),dict(problem='x'*6001),dict(expectation='\ud800'),dict(action_id='x y')):
            with self.assertRaises((InvalidInput,UnicodeError)): Action(raw(**changes))
        self.assertNotIn('incorrect', repr(Action(raw())))
