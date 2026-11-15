"""Outer calendar wire stays distinct from canonical MESSAGE and old versions."""
from hashlib import sha256
import json
import unittest

from cj_message.demo_dialogue import DialogueMessage, LIO_VERSION, LIO_VERSION_V2, LIO_VERSION_V3
from cj_message.domain import InvalidInput


class CalendarWire(unittest.TestCase):
    def test_exact_outer_bytes_and_digest_are_retained(self):
        raw = b'{ "version": "LIO-message.3", "message_id":"calendar-wire", "text":"Plan 3 days in Chengdu", "locale":"en", "new_conversation":true }'
        command = DialogueMessage.parse(raw, version=LIO_VERSION_V3)
        self.assertEqual(command.wire_input, raw)
        self.assertEqual(command.input_sha256, sha256(raw).hexdigest())
        self.assertTrue(command.new_conversation)
        self.assertEqual(command.protocol, LIO_VERSION_V3)
        for old in (LIO_VERSION, LIO_VERSION_V2):
            with self.subTest(old=old), self.assertRaises(InvalidInput):
                DialogueMessage.parse(raw, version=old)

    def test_new_wire_retains_original_envelope_bounds(self):
        base = dict(version=LIO_VERSION_V3, message_id='calendar-wire', text='规划成都三天', locale='zh')
        for extra in ({'day_count': 3}, {'locale': 'fr'}, {'new_conversation': False},
                      {'conversation_id': 'foreign'}, {'text': 'x' * 12001},
                      {'new_conversation': True, 'conversation_id': 'lio-dialogue-' + 'a' * 32}):
            with self.subTest(extra=extra), self.assertRaises(InvalidInput):
                DialogueMessage.parse(json.dumps(dict(base, **extra)).encode(), version=LIO_VERSION_V3)
        duplicate = json.dumps(base)[:-1] + ',"locale":"en"}'
        with self.assertRaises(InvalidInput):
            DialogueMessage.parse(duplicate.encode(), version=LIO_VERSION_V3)


if __name__ == '__main__':
    unittest.main()
