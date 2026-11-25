"""Offline tests for the entry-facts model judge (JT 2026-11-26 approved model review)."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from eval.lio_entry_judge import (ENTRY_CASES, JudgeUnavailable, country_rules, judge_request, main, parse_verdict,
                                  score_answers, validate)


class EntryJudge(unittest.TestCase):
    def test_country_rules_come_from_the_landing_mode_file(self):
        uk, us = country_rules('GB'), country_rules('US')
        self.assertIn('30', uk) and self.assertIn('transit-240h', uk)
        self.assertIn('65', us)
        self.assertNotIn('uk-canada-visa-free-2026', us)
        self.assertEqual(ENTRY_CASES, {'transit-visa-zh': 'US', 'visa-uk-en': 'GB'})

    def test_request_carries_rules_and_answer_but_no_key(self):
        body = judge_request('GB', 'A plain 10-day trip needs a visa.')
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertEqual(body['temperature'], 0)
        system, user = body['messages'][0]['content'], body['messages'][1]['content']
        self.assertIn('contradicts', system)
        self.assertIn('uk-canada-visa-free-2026', user)
        self.assertIn('A plain 10-day trip needs a visa.', user)
        self.assertNotIn('Authorization', json.dumps(body))

    def test_verdict_parsing_is_strict(self):
        self.assertEqual(parse_verdict('{"contradicts": true, "sentence": "x"}'), (True, 'x'))
        self.assertEqual(parse_verdict('{"contradicts": false, "sentence": ""}'), (False, ''))
        for raw in ('', 'yes', '{"contradicts": "true"}', '{"sentence": "x"}', '[1]'):
            with self.subTest(raw=raw), self.assertRaises(JudgeUnavailable):
                parse_verdict(raw)

    def test_validate_reports_accuracy_false_alarms_and_misses(self):
        rows = [dict(country='GB', text='ok', correct=True), dict(country='GB', text='bad', correct=False),
                dict(country='US', text='ok2', correct=True), dict(country='US', text='bad2', correct=False)]
        verdicts = {'ok': False, 'bad': True, 'ok2': True, 'bad2': False}
        result = validate(rows, lambda country, text: (verdicts[text], ''))
        self.assertEqual((result['total'], result['accuracy'], result['false_alarms'], result['misses']), (4, 0.5, 1, 1))
        self.assertEqual(result['false_alarm_rows'], [dict(country='US', text='ok2')])

    def test_score_answers_judges_only_entry_cases(self):
        seen = []
        def judge(country, text):
            seen.append(country)
            return ('needs a visa' in text, 'needs a visa' if 'needs a visa' in text else '')
        answers = {'visa-uk-en': 'A plain 10-day trip needs a visa.', 'transit-visa-zh': dict(text='可以跨省。'),
                   'alipay-zh': '绑卡。'}
        result = score_answers(answers, judge)
        self.assertEqual(sorted(seen), ['GB', 'US'])
        self.assertEqual(result['entry_facts'], {'transit-visa-zh': True, 'visa-uk-en': False})
        self.assertEqual(result['rate'], 0.5)

    def test_cli_requires_the_key_and_never_prints_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'answers.json')
            with open(path, 'w') as handle:
                json.dump({'visa-uk-en': 'x'}, handle)
            env = dict(os.environ)
            env.pop('CJ_MODEL_API_KEY', None)
            from unittest.mock import patch
            with patch.dict(os.environ, env, clear=True), self.assertRaises(SystemExit):
                main(['score', path])


if __name__ == '__main__':
    unittest.main()
