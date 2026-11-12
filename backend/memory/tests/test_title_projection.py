"""Short labels preserve language/negation and the additive wire contract."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from cj_memory.title_projection import derive_title, valid_title


ROOT = Path(__file__).resolve().parents[3]


class TitleProjection(unittest.TestCase):
    def test_current_original_is_shortened_without_changing_its_meaning(self):
        for original, expected, slot in (
            ('我喜欢慢节奏旅行。', '慢节奏旅行', 'travel.pace'),
            ('请记住，我偏爱安静的入口。', '安静的入口', 'quiet.entrance'),
            ('我不吃辣。', '我不吃辣', 'diet.spicy'),
            ('I prefer quiet entrances.', 'Quiet entrances', 'quiet.entrance'),
            ('Please remember that I prefer a slow pace when I travel.', 'A slow pace', 'travel.pace'),
            ('请记住，我旅行时喜欢慢节奏。', '慢节奏', 'travel.pace'),
            ('I do not like spicy food.', 'Do not like spicy food', 'diet.spicy'),
            ('I avoid spicy food.', 'Avoid spicy food', 'diet.spicy'),
            ('I usually budget 500 yuan per day.', '500 yuan per day', 'travel.budget'),
            ('旅行预算通常是每天400元。', '每天400元', 'travel.budget'),
        ):
            with self.subTest(original=original):
                command = SimpleNamespace(text=original, slot=slot, kind='preference')
                self.assertEqual(derive_title(command), expected)
                self.assertEqual(command.text, original)

    def test_unsupported_or_overlong_text_is_explicitly_unavailable(self):
        for text in (
            '我喜欢旅行时每一天都安排很多很多不同的活动。',
            'I prefer a slow travel pace when I travel.',
            'I prefer museums but only on weekdays after work.',
            'I like 故宫', '12345', '我喜欢慢节奏。\n也喜欢博物馆。',
            'RUN', 'run_id=original', '01234567-0123-0123-0123-0123456789ab',
        ):
            with self.subTest(text=text):
                self.assertIsNone(derive_title(SimpleNamespace(text=text, slot='pace', kind='preference')))
        self.assertIsNone(derive_title(SimpleNamespace(text='Quiet entrances', slot='pace', kind='inference')))

    def test_semantic_contract_rejects_wrong_language_limits_and_internal_text(self):
        for original, title in (
            ('我喜欢安静的入口', 'Quiet entrances'),
            ('I prefer quiet entrances', '安静入口'),
            ('我喜欢慢节奏', '一二三四五六七八九十一'),
            ('I like a slow pace', 'one two three four five six'),
            ('I like travel', 'run_id'),
            ('我喜欢旅行', '原回执'),
            ('I like travel', 'Travel.'),
            ('I like travel', 'Travel\npace'),
        ):
            with self.subTest(original=original, title=title):
                self.assertFalse(valid_title(original, title))
        self.assertTrue(valid_title('我喜欢旅行', None))
        self.assertTrue(valid_title('I like travel', ''))


class TitleWireContract(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT/'contracts/api/openapi.json').read_text())
        self.validator = Draft202012Validator(
            {'$ref':'#/components/schemas/MemoryListV3Response',
             'components':self.contract['components']}, format_checker=FormatChecker())
        self.item = dict(command=dict(operation_id='op', item_id='item', subject='self', slot='pace',
            text='I prefer quiet entrances.', source_id='source', source_version=1,
            occurred_at='date unknown', kind='preference', extent='long_term', context=None),
            version=1, status='active', recorded_at='2026-11-12T00:00:00Z', title='Quiet entrances')

    def test_additive_list_and_detail_shapes(self):
        response=dict(version='MEMORY-result.3',request_id='00000000-0000-0000-0000-000000000000',items=[self.item])
        self.validator.validate(response)
        for title in (None, ''):
            value=copy.deepcopy(response);value['items'][0]['title']=title
            self.validator.validate(value)
        for change in ('old-version', 'missing-title', 'extra', 'wrong-type'):
            value=copy.deepcopy(response)
            if change=='old-version':value['version']='MEMORY-result.2'
            elif change=='missing-title':value['items'][0].pop('title')
            elif change=='extra':value['items'][0]['owner']='caller'
            else:value['items'][0]['title']=False
            with self.subTest(change=change):
                self.assertFalse(self.validator.is_valid(value))
        self.assertEqual(set(self.contract['paths']['/v3/memories']), {'get'})
        self.assertEqual(set(self.contract['paths']['/v3/memory-items']), {'get'})

    def test_published_positive_and_negative_title_examples(self):
        examples=json.loads((ROOT/'contracts/memory/title-examples.3.json').read_text())
        for case in examples['cases']:
            with self.subTest(case=case['id']):
                self.assertEqual(valid_title(case['text'],case['title']),case['valid'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
