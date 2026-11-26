"""W2-5 (#1732): one answer prompt template; the old stacked prompt stays until the switch is on."""
import json
import os
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cj_message import lio_prompt
from cj_message.lio_context import ANSWER_DETAIL, PERSONA, answer_prompt
from cj_message.lio_prompt import render, template_enabled
from cj_api.real_services import TOOL_SYSTEM

ON = {'CJ_LIO_PROMPT_TEMPLATE': '1'}


def sentences(text):
    return [part.strip() for part in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', text) if part.strip()]


class Template(unittest.TestCase):
    def all_variants(self):
        for locale in ('zh', 'en'):
            for layout in ('flat', 'one-screen'):
                for detailed in (False, True):
                    for flags in ({}, dict(sources=True, traveler_question=True, tools=True, transit=True,
                                           dates=('2026-12-01', '2026-12-02'), destination=('成都市', '510100'))):
                        yield (locale, layout, detailed, flags), render(locale, layout=layout, detailed=detailed, **flags)

    def test_switch_is_off_by_default_and_accepts_only_zero_or_one(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CJ_LIO_PROMPT_TEMPLATE', None)
            self.assertFalse(template_enabled())
        with patch.dict(os.environ, ON):
            self.assertTrue(template_enabled())
        with patch.dict(os.environ, {'CJ_LIO_PROMPT_TEMPLATE': 'on'}), self.assertRaises(ValueError):
            template_enabled()

    def test_switch_off_keeps_the_old_prompt_byte_for_byte(self):
        os.environ.pop('CJ_LIO_PROMPT_TEMPLATE', None)
        for locale, ending in (('zh', ' Reply in Chinese.'), ('en', ' Reply in English.')):
            self.assertEqual(answer_prompt(locale, 'Q', detailed=True), PERSONA + ANSWER_DETAIL + ending)

    def test_switch_on_uses_the_template_for_every_answer_prompt(self):
        with patch.dict(os.environ, ON):
            for locale in ('zh', 'en'):
                for layout in ('flat', 'one-screen'):
                    self.assertEqual(answer_prompt(locale, 'Q', detailed=True, layout=layout),
                                     render(locale, layout=layout, detailed=True))

    def test_every_sentence_appears_once(self):
        for key, text in self.all_variants():
            with self.subTest(key=key):
                parts = sentences(text)
                self.assertEqual(len(parts), len(set(parts)), [part for part in parts if parts.count(part) > 1])

    def test_contradictions_of_the_stacked_prompt_are_gone(self):
        for key, text in self.all_variants():
            with self.subTest(key=key):
                for removed in ('Date changing facts', 'bold short headings', 'Only cite links supplied',
                                '你好！准备去哪儿玩？', 'Hey! Where are you off to?', 'Reply in English.',
                                'Reply in Chinese.', 'Answer in the requested language', 'M4 real external tools'):
                    self.assertNotIn(removed, text)
                self.assertEqual(text.count('Never invent prices'), 1)
                locale, layout = key[0], key[1]
                self.assertEqual('End with at most one specific question' in text, layout == 'flat')
                self.assertEqual('Do not end with a question or an offer' in text, layout == 'one-screen')
                self.assertEqual('Write the whole answer in English' in text, locale == 'en')
                self.assertEqual('address the traveler as 你' in text, locale == 'zh')

    def test_safety_trust_and_saving_rules_are_kept(self):
        tool_rules = TOOL_SYSTEM.removeprefix('M4 real external tools. ')
        for key, text in self.all_variants():
            with self.subTest(key=key):
                for kept in ('110 (police)', '120 (ambulance)', 'no length limit', 'Never invent prices',
                             'Live prices, ticket availability and whether a place is open today get no numbers',
                             'never infer a traveler\'s personal eligibility', 'eligible countries from memory',
                             'taps Remember', 'Do not offer to book tickets or take payment',
                             'keep internal identifiers, coordinates, providers and interfaces out of the answer',
                             'Never invent personal facts', 'never fill missing planning fields'):
                    self.assertIn(kept, text)
                self.assertEqual(tool_rules in text, bool(key[3].get('tools')))

    def test_optional_sections_only_when_asked(self):
        plain = render('zh')
        for section in (lio_prompt.SOURCES, lio_prompt.TRAVELER_UNKNOWN, lio_prompt.TRANSIT, lio_prompt.TOOLS):
            self.assertNotIn(section, plain)
        self.assertIn(lio_prompt.BRIEF, plain)
        self.assertNotIn(lio_prompt.LENGTH['flat'], plain)
        self.assertIn(lio_prompt.LENGTH['flat'], render('zh', detailed=True))
        self.assertIn(lio_prompt.NO_DESTINATION, render('en', no_destination=True))
        self.assertIn('Use Beijing calendar dates for legacy weather.', render('en', legacy_weather=True))
        self.assertTrue(render('zh', scene=' SCENE-DATA').endswith(' SCENE-DATA'))
        with self.assertRaises(ValueError):render('fr')
        with self.assertRaises(ValueError):render('zh', layout='cards')


class RealAnswerPath(unittest.TestCase):
    def system_for(self, question, locale, *, switch):
        from test_m4_real_services import KEY, Boundaries, sse
        from cj_api.local_app import ISSUER, scope_for
        from cj_api.real_services import RealServices, RealTools
        fixture = Boundaries('test_native_tool_and_original_receipt')
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        provider = fixture.provider(sse())
        subject = 'm4-synthetic-one'
        subjects = frozenset({subject})
        tools = RealTools(RealServices(provider, KEY, subjects, demo_subjects=subjects, national_subjects=subjects))
        binding = SimpleNamespace(scope=scope_for(ISSUER, subject), run_id='template-original')
        systems = []

        class Worker:
            lio_planning = None
            def _model_history(self, *args): pass
            def _registered_stream(self, original, key, registration, argument, **kwargs):
                systems.append(argument.system)
                yield json.dumps(dict(version='MODEL-tool-turn.1', kind='answer', answer=dict(zh='好。', en='OK.'), calls=[]))
        worker = Worker()
        worker.provider = provider
        with patch.dict(os.environ, {'CJ_LIO_PROMPT_TEMPLATE': switch}):
            list(tools.answer(worker, binding, [dict(role='user', content=question)], lio_locale=locale))
        return systems[0]

    def test_real_answer_system_is_one_render_when_the_switch_is_on(self):
        for question, locale in (('外国游客在中国怎么用支付宝？', 'zh'), ('Can I use Google in China?', 'en')):
            with self.subTest(locale=locale):
                old = self.system_for(question, locale, switch='0')
                new = self.system_for(question, locale, switch='1')
                self.assertIn(PERSONA.split(' Date changing facts.')[0], old)
                self.assertNotIn('Date changing facts', new)
                self.assertTrue(new.startswith(lio_prompt.ROLE + ' ' + lio_prompt.TOOLS))
                self.assertIn(lio_prompt.NO_DESTINATION, new)
                self.assertIn('In China, today is ', new)
                self.assertEqual(len(sentences(new)), len(set(sentences(new))))


if __name__ == '__main__':
    unittest.main()
