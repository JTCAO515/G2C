"""#1474: Lio answers carry concrete, scannable detail instead of fixed short caps."""
import unittest

from cj_message.lio_context import ANSWER_DETAIL, PERSONA, answer_prompt
from runtime_adapter.profiles import ANSWER_STYLE

# Intake requests reuse PERSONA next to large schemas under the 32768-byte wire bound.
PERSONA_BYTES_BEFORE_1474 = 2757


class AnswerStyle(unittest.TestCase):
    def test_old_short_caps_are_gone(self):
        for clause in ('80 characters or 50 words', '150 characters or 90 words', 'at most 3 list items',
                       'omit tables, headings and raw links',
                       'Give the complete answer, then end with one specific question'):
            with self.subTest(clause=clause):
                self.assertNotIn(clause, PERSONA)
                self.assertNotIn(clause, ANSWER_DETAIL)

    def test_answers_are_sized_by_scenario(self):
        self.assertIn('at most 40 Chinese characters or 25 English words', PERSONA)
        for clause in ('120–300 Chinese characters or 80–180 English words',
                       'up to 500 characters or 300 words',
                       'up to 1000 characters or 600 words in total',
                       'Concise means no filler, not thin'):
            with self.subTest(clause=clause):
                self.assertIn(clause, ANSWER_DETAIL)

    def test_concrete_elements_and_structure_are_requested(self):
        for clause in ('numbered steps', 'bold short headings', 'metro line or station', 'approximate ranges'):
            with self.subTest(clause=clause):
                self.assertIn(clause, ANSWER_DETAIL)
        self.assertIn('never use tables', PERSONA)

    def test_fixed_greeting_is_only_for_pure_greetings(self):
        self.assertIn('only when the traveler only greets you', PERSONA)
        self.assertIn('Do not start with a greeting, a self-introduction or a restatement of the question', PERSONA)
        self.assertIn('End with at most one specific question, only when there is a useful next step', PERSONA)

    def test_live_facts_and_red_lines_stay(self):
        self.assertIn('Never invent prices, opening hours, or transport facts.', PERSONA)
        self.assertIn('Live prices, ticket availability and whether a place is open today stay without numbers',
                      ANSWER_DETAIL)
        self.assertIn('In emergencies lead with 110 (police) or 120 (ambulance)', PERSONA)
        self.assertIn('Do not offer to book tickets or take payment.', PERSONA)

    def test_detail_only_where_a_reply_is_written(self):
        self.assertLessEqual(len(PERSONA.encode()), PERSONA_BYTES_BEFORE_1474)
        self.assertNotIn(ANSWER_DETAIL, answer_prompt('zh', '去成都'))
        for locale, ending in (('zh', ' Reply in Chinese.'), ('en', ' Reply in English.')):
            self.assertEqual(answer_prompt(locale, 'Q', detailed=True), PERSONA + ANSWER_DETAIL + ending)
        self.assertEqual(answer_prompt('zh', detailed=True).count(ANSWER_STYLE), 1)
        self.assertNotIn(ANSWER_STYLE, ANSWER_DETAIL)

    def test_answer_and_discussion_paths_request_detail(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        # The answer path also drops the greeting example (bare greetings are answered in code).
        self.assertIn("answer_prompt(lio_locale,question=messages[-1]['content'],detailed=True,greeting_example=False,",
                      (root / 'real_services.py').read_text())
        self.assertIn('answer_prompt(locale, turns[-1].text, detailed=True) + DISCUSSION_PROMPT',
                      (root / 'local_lio_planning.py').read_text())
        self.assertIn('answer_prompt(locale,question=text,detailed=True)',
                      (root.parent / 'agent/cj_agent/worker.py').read_text())


if __name__ == '__main__':
    unittest.main()


class OneScreenLayout(unittest.TestCase):
    """JT 2026-11-25 "all A": one screen, the rest on tap (docs/lio-voice.md §3.2, §4.2).

    The layout is an explicit argument only; the contract PR (S line) passes 'one-screen'
    when the switch, the subject list and the app declaration all agree.
    """

    def combos(self):
        for locale in ('zh', 'en'):
            for question in (None, '外国游客在中国怎么用支付宝？', 'Where does your information come from?'):
                for detailed in (False, True):
                    for greeting in (False, True):
                        yield dict(locale=locale, question=question, detailed=detailed, greeting_example=greeting)

    def test_flat_is_byte_identical_to_the_call_without_a_layout(self):
        from cj_message.lio_context import ONE_SCREEN_DETAIL
        for kwargs in self.combos():
            with self.subTest(**kwargs):
                locale = kwargs.pop('locale')
                flat = answer_prompt(locale, **kwargs, layout='flat')
                self.assertEqual(flat, answer_prompt(locale, **kwargs))
                self.assertNotIn(ONE_SCREEN_DETAIL, flat)

    def test_one_screen_swaps_detail_bands_and_closing_question(self):
        from cj_message.lio_context import CLOSING_QUESTION, NO_CLOSING_QUESTION, ONE_SCREEN_DETAIL
        self.assertIn(CLOSING_QUESTION, PERSONA)
        for kwargs in self.combos():
            with self.subTest(**kwargs):
                locale = kwargs.pop('locale')
                prompt = answer_prompt(locale, **kwargs, layout='one-screen')
                self.assertEqual(prompt.count(ONE_SCREEN_DETAIL), 1)
                self.assertNotIn(ANSWER_DETAIL, prompt)
                self.assertNotIn('120–300 Chinese characters', prompt)
                self.assertNotIn(CLOSING_QUESTION, prompt)
                self.assertIn(NO_CLOSING_QUESTION, prompt)
                # Red line, emergency lead and live-fact rules stay untouched.
                self.assertIn('keep internal identifiers, coordinates, providers and interfaces out of the answer.', prompt)
                self.assertIn('In emergencies lead with 110 (police) or 120 (ambulance), without length limits;', prompt)
                self.assertTrue(prompt.endswith(' Reply in Chinese.' if locale == 'zh' else ' Reply in English.'))

    def test_one_screen_detail_follows_the_confirmed_bands(self):
        from cj_message.lio_context import ONE_SCREEN_DETAIL
        for clause in ('first sentence answers', 'at most three short points', 'one best pick and two alternatives',
                       '80–150 Chinese characters or 50–90 English words', '80–130', '120–180', '120–200', '50–100',
                       'keep every life-saving step', 'approximate ranges'):
            with self.subTest(clause=clause):
                self.assertIn(clause, ONE_SCREEN_DETAIL)
        # Preview 2026-11-25: a capped route answer rambled ("不对，其实……"); route facts come from tools.
        self.assertIn('never correct yourself mid-answer', ONE_SCREEN_DETAIL)

    def test_unknown_layout_is_rejected(self):
        with self.assertRaises(ValueError):
            answer_prompt('en', layout='compact')


class TwoBubbleSplit(unittest.TestCase):
    """JT 2026-11-25 (via coordination): one-screen answers show as at most two bubbles. The
    server still sends one message; the app splits at the first blank line when layout=split."""

    def test_first_paragraph_is_the_answer_or_the_action(self):
        from cj_message.lio_context import ONE_SCREEN_DETAIL
        for clause in ('The first paragraph is only the direct answer',
                       'at most 35 Chinese characters or 20 English words',
                       'no line break inside it',
                       'then one blank line',
                       'any assumption you made, such as party size, pace or season, goes after it',
                       'In an emergency the first paragraph is only the action, such as calling 110 or 120'):
            with self.subTest(clause=clause):
                self.assertIn(clause, ONE_SCREEN_DETAIL)
        self.assertEqual(ONE_SCREEN_DETAIL.count('blank line'), 1)

    def test_flat_still_has_no_paragraph_rule(self):
        for locale in ('zh', 'en'):
            with self.subTest(locale=locale):
                self.assertNotIn('first paragraph', answer_prompt(locale, detailed=True))


class OneScreenEntryFacts(unittest.TestCase):
    """Preview 2026-11-25: a capped transit-visa answer invented "不得跨市旅行". Under one-screen,
    entry rules come only from supplied official facts (docs/lio-voice.md §4.3 item 9)."""

    def test_entry_answers_give_the_conclusion_and_where_to_confirm(self):
        from cj_message.lio_context import ONE_SCREEN_DETAIL
        for clause in ('For visa, entry and transit questions',
                       'only from supplied official facts',
                       'never state rule details such as permitted areas, ports or eligible countries from memory',
                       'say where to confirm',
                       'If no official facts are supplied, say that the rule depends on the passport and trip'):
            with self.subTest(clause=clause):
                self.assertIn(clause, ONE_SCREEN_DETAIL)
