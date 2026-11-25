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
