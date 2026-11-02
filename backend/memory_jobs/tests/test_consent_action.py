"""Strict explicit user intent, not an authorization/PG acceptance claim."""
from dataclasses import FrozenInstanceError
import json
import unittest

from cj_memory_jobs.consent import ConsentAction, VERSION
from cj_memory_jobs.codec import InvalidInput


def action(**changes):
    value = dict(version=VERSION, action_id='original', operation='enable',
                 conversation_id='chat', expected_generation='generation',
                 expected_epoch=0, expected_source_version=0)
    value.update(changes)
    return json.dumps(value, ensure_ascii=False).encode()


class ConsentActions(unittest.TestCase):
    def test_explicit_conversation_and_original_bytes(self):
        raw = action(conversation_id='会话') + b'\n'
        parsed = ConsentAction.parse(raw)
        self.assertEqual(parsed.raw, raw)
        self.assertEqual(parsed.conversation_id, '会话')
        self.assertEqual((parsed.expected_epoch, parsed.expected_source_version), (0, 0))
        self.assertEqual(ConsentAction.parse(action(operation='disable')).operation, 'disable')
        with self.assertRaises(FrozenInstanceError):
            parsed.operation = 'enable'

    def test_no_owner_manual_source_or_boolean_authorization(self):
        for extra in ({'owner': 'other'}, {'scope': 'other'}, {'enabled': True},
                      {'source_id': 'manual-v1:foo'}, {'all_history': True}):
            with self.subTest(extra=extra), self.assertRaises(InvalidInput):
                ConsentAction.parse(action(**extra))
        for operation in ('manual_save', 'all', True, None):
            with self.assertRaises(InvalidInput):
                ConsentAction.parse(action(operation=operation))

    def test_integer_bounds_and_boolean_refusal(self):
        for key in ('expected_epoch', 'expected_source_version'):
            for value in (True, -1, 2**63, 1.0, None):
                with self.subTest(key=key, value=value), self.assertRaises(InvalidInput):
                    ConsentAction.parse(action(**{key: value}))

    def test_strict_json_and_exact_key_set(self):
        raw = action()
        for invalid in (raw[:-1]+b',"operation":"enable"}', b'{}', b'[]',
                        raw.decode().replace('"operation": "enable", ', '').encode(),
                        raw.decode().encode('utf-16'), b'\xff', b' ' * 32769):
            with self.assertRaises(InvalidInput):
                ConsentAction.parse(invalid)

    def test_identity_bounds_do_not_normalize_or_admit_surrogates(self):
        self.assertNotEqual(ConsentAction.parse(action(conversation_id='é')).conversation_id,
                            ConsentAction.parse(action(conversation_id='e\u0301')).conversation_id)
        self.assertEqual(ConsentAction.parse(action(conversation_id=' chat ')).conversation_id, ' chat ')
        for change in ({'action_id': ''}, {'conversation_id': ' '},
                       {'conversation_id': 'x' * 257}, {'expected_generation': 'x' * 1025},
                       {'action_id': '\0'}, {'action_id': '\ud800'}):
            # JSON can legally carry escaped invalid Unicode; the boundary refuses it.
            raw = json.loads(action())
            raw.update(change)
            with self.subTest(change=change), self.assertRaises(InvalidInput):
                ConsentAction.parse(json.dumps(raw).encode())
