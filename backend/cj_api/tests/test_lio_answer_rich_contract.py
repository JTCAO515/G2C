"""LIO-answer-rich.1 contract (#1984): schema, examples, the offline checker and the tables it shares with the code."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / 'contracts/message'
sys.path.insert(0, str(CONTRACTS))
import check_lio_answer_rich as rich_check  # noqa: E402

EXAMPLES = json.loads((CONTRACTS / 'lio-answer-rich-examples.1.json').read_text(encoding='utf-8'))


class Examples(unittest.TestCase):
    def test_every_valid_example_passes_and_every_invalid_one_fails(self):
        valid, invalid = rich_check.run_examples()
        self.assertEqual((valid, invalid), (len(EXAMPLES['valid']), len(EXAMPLES['invalid'])))
        self.assertGreaterEqual(valid, 12)

    def test_every_rule_has_a_negative_example(self):
        names = ' | '.join(row['name'] for row in EXAMPLES['invalid'])
        for rule in ('version', 'empty entities', '21 entities', 'start equals end', 'negative offset', 'float offset', 'UTF-16',
                     'overlapping', 'out of order', 'same place linked twice', 'place id in capitals', 'entity type', 'flag emoji',
                     'four cards', 'same card type twice', 'unknown card type', 'not in the table', 'half a destination', '7 decimals',
                     'outside China', 'zero-width', 'bidi', 'transport from equals to', 'currency quote BTC', 'user position',
                     'status pending', 'saved without undo', 'undo available without a target', 'expired with a target', 'not derived',
                     'not saved reason disabled', '15 days', 'count of 100', 'four used memory', 'used_total below', 'prompt granted'):
            self.assertIn(rule, names)

    def test_the_emoji_examples_separate_scalar_offsets_from_utf16_offsets(self):
        # an offset counted in UTF-16 units would land one scalar late after the emoji: the examples must catch that
        for example in EXAMPLES['valid']:
            answer = EXAMPLES['answers'][example['answer']]
            if '😀' not in answer or 'entities' not in example['rich']:
                continue
            after = [row for row in example['rich']['entities'] if row['start'] > answer.index('😀')]
            self.assertTrue(after)
            for row in after:
                self.assertNotEqual(rich_check.utf16_span(answer, row['start'], row['end']), (row['start'], row['end']))

    def test_the_biggest_legal_rich_fits_the_size_limit(self):
        answer = '好' * 200000
        entities = [{'type': 'place', 'start': 40 * i, 'end': 40 * i + 32, 'place_id': 'pl_' + 'bj' + '_' + 'x' * 55 + str(i % 10) + 'y' * (i // 10)}
                    for i in range(20)]
        longest_place = max(len(row['place_id']) for row in entities)
        self.assertLessEqual(longest_place, 64)
        card = EXAMPLES['valid'][[row['name'] for row in EXAMPLES['valid']].index('three cards')]['rich']['cards']
        receipt = EXAMPLES['valid'][[row['name'] for row in EXAMPLES['valid']].index('everything at once')]['rich']['trip_receipt']
        memory = {'prompt': 'consent', 'used': [{'item_id': 'm' * 199 + str(i), 'title': '节' * 40} for i in range(3)], 'used_total': 99}
        value = {'version': 'LIO-answer-rich.1', 'entities': entities, 'cards': card, 'trip_receipt': receipt, 'memory': memory}
        size = len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        self.assertLessEqual(size, rich_check.MAX_RICH_BYTES, size)
        rich_check.check(value, answer)


class Tables(unittest.TestCase):
    def test_card_tools_are_registered_in_the_app(self):
        source = (ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioToolRegistry.swift').read_text(encoding='utf-8')
        registered = set(re.findall(r'LioTool\("([a-z-]+)"\)', source))
        for kind, tool in rich_check.CARD_TOOLS.items():
            self.assertIn(tool, registered, kind)

    def test_transport_cities_in_the_examples_exist_in_the_server_table(self):
        from cj_api.lio_transport import CITIES
        for example in EXAMPLES['valid']:
            for card in example['rich'].get('cards', []):
                if card['type'] == 'transport':
                    self.assertIn(card['open']['parameters']['from'], CITIES)
                    self.assertIn(card['open']['parameters']['to'], CITIES)

    def test_the_undo_target_is_the_trip_history_definition(self):
        schema = json.loads((CONTRACTS / 'lio-answer-rich-schema.1.json').read_text(encoding='utf-8'))
        text = json.dumps(schema)
        self.assertIn('lio-trip-history-schema.4.json#/$defs/UndoTarget', text)

    def test_undo_action_id_is_derived_and_stable(self):
        first = rich_check.undo_action_id('lio-plan-run-5c1f')
        self.assertEqual(first, rich_check.undo_action_id('lio-plan-run-5c1f'))
        self.assertRegex(first, r'^undo-[0-9a-f]{40}$')
        self.assertNotEqual(first, rich_check.undo_action_id('lio-plan-run-5c20'))


if __name__ == '__main__':
    unittest.main()
