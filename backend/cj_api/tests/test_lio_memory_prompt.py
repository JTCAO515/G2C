"""The first-time memory consent prompt (#1999, M-1): the cue table, the marker, and the `rich.memory.prompt` read."""
import os
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from cj_api import lio_memory_prompt as prompt
from cj_api.lio_dialogue_routes import RICH_VERSION, _message
from cj_message.lio_context import LioLayout

STATEMENTS = ('我不喜欢辣的，帮我推荐北京的晚饭', '我平时喜欢慢节奏的旅行，三天怎么排', '我的预算是每晚1000元，推荐酒店', '我带着孩子，想轻松一点',
              '我一个人去成都玩', '我只会说英语，怎么点菜', 'I prefer slow trips, plan 3 days in Beijing', "I usually like quiet hotels",
              'My budget is around 800 yuan a day', "I'm travelling with my kids", 'I only speak English, how do I order?', "I don't like crowds, any tips?")
PLAIN = ('故宫怎么走', '北京天气怎么样', '地铁几点停运', 'How do I get from the airport to the city center?', 'Is the Great Wall open today?', '你好', '')
REVIEW_FALSE_POSITIVES = ('我有孕在身，想要慢节奏', '我腿不好，想要轻松一点', '我经常头疼', '我身体不好想要慢节奏', '我有心脏问题，节奏慢一点',
                          '我不吃早饭，因为在做化疗', '我需要无障碍通道', '带着孩子去，他有自闭症', '我喜欢念经', "I don't eat meat on Fridays",
                          '我需要打车', '我需要厕所', '我想要一杯咖啡', '我经常出差', '我爱你')
SENSITIVE = ('我对花生过敏，不吃辣', '我是穆斯林，我喜欢清真食物', 'I am allergic to peanuts and I prefer quiet places', 'I keep kosher, I like museums',
             '我有糖尿病，预算每晚1000', '我坐轮椅，喜欢慢节奏')


class Consent:
    def __init__(self, recorded=False, state='withdrawn', fail=False):
        self.recorded, self.state, self.fail = recorded, state, fail

    def current(self, scope):
        if self.fail:
            raise RuntimeError('unreadable')
        return dict(recorded=self.recorded, state=self.state, consent_text_version=None, changed_at=None)


class Cues(unittest.TestCase):
    def test_statements_about_the_traveler_match(self):
        for text in STATEMENTS:
            with self.subTest(text=text):
                self.assertTrue(prompt.matches(text))

    def test_plain_questions_do_not(self):
        for text in PLAIN:
            with self.subTest(text=text):
                self.assertFalse(prompt.matches(text))

    def test_health_and_religion_never_match(self):
        for text in SENSITIVE:
            with self.subTest(text=text):
                self.assertFalse(prompt.matches(text))

    def test_the_review_false_positives_do_not_match(self):
        for text in REVIEW_FALSE_POSITIVES:
            with self.subTest(text=text):
                self.assertFalse(prompt.matches(text))

    def test_odd_input_is_no_match(self):
        for value in (None, 5, b'x', ['a'], 'x' * 5000, ' '):
            self.assertFalse(prompt.matches(value))


class Marker(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop('CJ_LIO_MEMORY_CONSENT_REQUIRED', None)

    def test_off_by_default(self):
        self.assertIsNone(prompt.effect(STATEMENTS[0], Consent(), 's'))

    def test_only_for_an_account_that_never_chose(self):
        os.environ['CJ_LIO_MEMORY_CONSENT_REQUIRED'] = '1'
        self.assertEqual(prompt.effect(STATEMENTS[0], Consent(), 's'), 'lio_memory_prompt:consent')
        self.assertIsNone(prompt.effect(STATEMENTS[0], Consent(recorded=True, state='granted'), 's'))
        self.assertIsNone(prompt.effect(STATEMENTS[0], Consent(recorded=True, state='withdrawn'), 's'))   # a withdrawal is respected
        self.assertIsNone(prompt.effect(STATEMENTS[0], Consent(fail=True), 's'))                           # unreadable: not sent
        self.assertIsNone(prompt.effect(STATEMENTS[0], None, 's'))
        self.assertIsNone(prompt.effect(PLAIN[0], Consent(), 's'))
        self.assertIsNone(prompt.effect(SENSITIVE[0], Consent(), 's'))

    def test_the_extraction_object_asks_the_accounts_own_consent_store(self):
        from cj_api.local_lio_memory import LioMemoryExtraction
        os.environ['CJ_LIO_MEMORY_CONSENT_REQUIRED'] = '1'
        extraction = LioMemoryExtraction(None, None, None)
        binding = SimpleNamespace(scope='scope-a')
        with mock.patch('cj_api.lio_memory_consent.ConsentStore', lambda database: Consent()):
            self.assertEqual(extraction.consent_prompt(binding, STATEMENTS[0]), 'lio_memory_prompt:consent')
            self.assertIsNone(extraction.consent_prompt(binding, PLAIN[0]))
        with mock.patch('cj_api.lio_memory_consent.ConsentStore', lambda database: Consent(recorded=True, state='granted')):
            self.assertIsNone(extraction.consent_prompt(binding, STATEMENTS[0]))

    def test_a_bad_switch_value_is_a_configuration_error(self):
        os.environ['CJ_LIO_MEMORY_CONSENT_REQUIRED'] = 'yes'
        with self.assertRaises(ValueError):
            prompt.effect(STATEMENTS[0], Consent(), 's')


def item():
    return SimpleNamespace(message_id='m1', text='我不喜欢辣的', locale='zh')


def state(text, *effects):
    return SimpleNamespace(status='completed', text=text, effects=tuple(effects), draft_outcome=None, budget_exhausted_stage='none')


SPLIT = LioLayout('split').effect()


class Row(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {'CJ_LIO_ANSWER_RICH': 'on'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def row(self, declared='rich', open_=True, *effects):
        return _message(item(), state('好的。\n\n推荐这几家。', SPLIT, *effects), declared=declared,
                        prompt_open=(lambda: open_) if open_ is not None else None)

    def test_the_marker_gives_memory_prompt_only_while_the_account_has_not_chosen(self):
        self.assertEqual(self.row('rich', True, prompt.PROMPT_EFFECT)['rich'], dict(version=RICH_VERSION, memory=dict(prompt='consent')))
        self.assertNotIn('rich', self.row('rich', False, prompt.PROMPT_EFFECT))            # chose meanwhile
        self.assertNotIn('rich', self.row('rich', None, prompt.PROMPT_EFFECT))
        self.assertNotIn('rich', self.row('rich', True))                                    # no marker
        with mock.patch.dict(os.environ, {'CJ_LIO_ANSWER_RICH': 'off'}):                    # rich off: the check is not even run
            calls = []
            row = _message(item(), state('好的。\n\n再看看。', SPLIT, prompt.PROMPT_EFFECT), declared='rich', prompt_open=lambda: calls.append(1) or True)
            self.assertNotIn('rich', row)
            self.assertEqual(calls, [])

    def test_never_for_a_poll_that_did_not_declare_rich(self):
        for declared in (False, True):
            self.assertNotIn('rich', self.row(declared, True, prompt.PROMPT_EFFECT))

    def test_a_lookalike_effect_is_not_the_marker(self):
        for value in ('lio_memory_prompt:consent ', 'lio_memory_prompt:granted', 'lio_memory_prompt:'):
            self.assertNotIn('rich', self.row('rich', True, value))

    def test_the_check_runs_only_for_a_row_with_the_marker(self):
        calls = []
        _message(item(), state('好的。\n\n再看看。', SPLIT), declared='rich', prompt_open=lambda: calls.append(1) or True)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()


class PageCheck(unittest.TestCase):
    def test_the_consent_table_is_read_once_per_page(self):
        from cj_api.lio_dialogue_routes import _prompt_open
        reads = []

        class Store:
            def current(self, scope):
                reads.append(scope)
                return dict(recorded=False)
        with mock.patch.dict(os.environ, {'CJ_LIO_MEMORY_CONSENT_REQUIRED': '1'}):
            check = _prompt_open(SimpleNamespace(consent=Store()), SimpleNamespace(scope='s'))
            self.assertTrue(check() and check() and check())
        self.assertEqual(reads, ['s'])
