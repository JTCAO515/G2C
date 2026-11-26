"""#1727 part 2: LIO-message.2 may carry one chip_ticket; every other version refuses the field."""
import json
import unittest

from cj_message.demo_dialogue import DialogueMessage, LIO_VERSION, LIO_VERSION_V2, LIO_VERSION_V3, LIO_VERSION_V4
from cj_message.domain import InvalidInput

TICKET = 'A' * 43


def parse(version=LIO_VERSION_V2, **extra):
    body = dict(version=version, message_id='m1', text='付不了怎么办', locale='zh', **extra)
    return DialogueMessage.parse(json.dumps(body, ensure_ascii=False).encode(), version=version)


class ChipTicketField(unittest.TestCase):
    def test_a_well_formed_ticket_is_kept_on_v2_only(self):
        self.assertEqual(parse(chip_ticket=TICKET).chip_ticket, TICKET)
        self.assertIsNone(parse().chip_ticket)
        for version in (LIO_VERSION, LIO_VERSION_V3, LIO_VERSION_V4):
            with self.subTest(version=version), self.assertRaises(InvalidInput):
                parse(version, chip_ticket=TICKET)

    def test_a_ticket_that_is_not_shaped_like_one_is_just_not_a_ticket(self):
        for value in ('', 'short', 'a' * 44, 'a' * 42 + '=', ' ' + 'a' * 42, 'é' * 43):
            with self.subTest(value=value):
                message = parse(chip_ticket=value)
                self.assertIsNone(message.chip_ticket)
                self.assertEqual(message.text, '付不了怎么办')

    def test_a_ticket_that_is_not_a_string_is_a_bad_request(self):
        for value in (None, 7, True, ['a' * 43], {'t': TICKET}):
            with self.subTest(value=value), self.assertRaises(InvalidInput):
                parse(chip_ticket=value)

    def test_the_body_hash_covers_the_ticket_so_a_replay_must_be_identical(self):
        self.assertNotEqual(parse(chip_ticket=TICKET).input_sha256, parse().input_sha256)
        self.assertEqual(parse(chip_ticket=TICKET).input_sha256, parse(chip_ticket=TICKET).input_sha256)

    def test_other_unknown_fields_are_still_refused(self):
        for extra in (dict(chip=TICKET), dict(is_followup=True), dict(accepts=['LIO-answer-followups.1'])):
            with self.subTest(extra=extra), self.assertRaises(InvalidInput):
                parse(**extra)


if __name__ == '__main__':
    unittest.main()
