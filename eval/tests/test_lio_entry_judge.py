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
        uk, us = json.loads(country_rules('GB')), json.loads(country_rules('US'))
        self.assertEqual([p['id'] for p in uk['policies']], ['uk-canada-visa-free-2026', 'transit-240h'])
        self.assertEqual([p['id'] for p in us['policies']], ['transit-240h'])
        self.assertEqual(us['otherwise'], 'visa_required')
        self.assertIn('complete', us['note'])
        self.assertIn('57', json.dumps(us['policies'][0]['sources'], ensure_ascii=False))
        self.assertEqual(ENTRY_CASES, {'transit-visa-zh': 'US', 'visa-uk-en': 'GB'})

    def test_request_carries_rules_and_answer_but_no_key(self):
        body = judge_request('GB', 'A plain 10-day trip needs a visa.')
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertEqual(body['temperature'], 0)
        system, user = body['messages'][0]['content'], body['messages'][1]['content']
        self.assertIn('contradicts', system)
        self.assertIn('complete set', system)
        self.assertIn('144', system)
        # Acceptance run on c8faf430 (S, 2026-11-26): misses on going back to the origin
        # country, false alarms mixing visa-free entry with transit.
        self.assertIn('third country or region', system)
        self.assertIn('back to the country the trip started from', system)
        self.assertIn('separate policies', system)
        # #1675 review: the complete-set premise covers mainland stays only, and the
        # third-country condition belongs to the transit-240h policy.
        self.assertIn('stays in mainland China', system)
        self.assertIn('airside', system)
        self.assertIn('Hong Kong', system)
        self.assertIn('The transit-240h policy requires', system)
        self.assertIn('uk-canada-visa-free-2026', user)
        self.assertIn('<answer>\nA plain 10-day trip needs a visa.\n</answer>', user)
        self.assertNotIn('Authorization', json.dumps(body))

    def test_verdict_parsing_is_strict(self):
        self.assertEqual(parse_verdict('{"contradicts": true, "sentence": "x"}'), (True, 'x'))
        self.assertEqual(parse_verdict('{"contradicts": false, "sentence": ""}'), (False, ''))
        for raw in ('', 'yes', '{"contradicts": "true"}', '{"sentence": "x"}', '[1]', '{"contradicts": true, "sentence": 5}'):
            with self.subTest(raw=raw), self.assertRaises(JudgeUnavailable):
                parse_verdict(raw)

    def test_validate_reports_accuracy_false_alarms_and_misses(self):
        rows = [dict(country='GB', text='ok', correct=True), dict(country='GB', text='bad', correct=False),
                dict(country='US', text='ok2', correct=True), dict(country='US', text='bad2', correct=False)]
        verdicts = {'ok': False, 'bad': True, 'ok2': True, 'bad2': False}
        result = validate(rows, lambda country, text: (verdicts[text], ''))
        self.assertEqual((result['total'], result['accuracy'], result['false_alarms'], result['misses']), (4, 0.5, 1, 1))
        self.assertEqual(result['false_alarm_rows'], [dict(country='US', text='ok2')])
        # A failed call is counted apart, never as a pass, and does not stop the run.
        def flaky(country, text):
            if text == 'bad':
                raise JudgeUnavailable('judge output is not JSON')
            return verdicts[text], ''
        partial = validate(rows, flaky)
        # A malformed verdict is the judge's own failure: counted apart from call failures.
        self.assertEqual((partial['judged'], partial['malformed'], partial['unavailable']), (3, 1, 0))
        def offline(country, text):
            import httpx
            if text == 'bad':
                raise httpx.ConnectError('EOF', request=httpx.Request('POST', 'https://x'))
            return verdicts[text], ''
        down = validate(rows, offline)
        self.assertEqual((down['judged'], down['malformed'], down['unavailable']), (3, 0, 1))

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
        self.assertEqual(score_answers({'alipay-zh': 'x'}, judge)['missing'], ['transit-visa-zh', 'visa-uk-en'])

    def test_model_calls_retry_transient_failures(self):
        import httpx
        from unittest.mock import patch
        from eval.lio_entry_judge import model_judge
        calls = []
        ok = httpx.Response(200, json={'choices': [{'message': {'content': '{"contradicts": false, "sentence": ""}'}}]},
                            request=httpx.Request('POST', 'https://x'))
        def post(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise httpx.ConnectError('EOF', request=httpx.Request('POST', 'https://x'))
            return ok
        with patch('httpx.post', post), patch('time.sleep', lambda seconds: None):
            self.assertEqual(model_judge('k')('GB', 'ok'), (False, ''))
        self.assertEqual(len(calls), 3)
        calls.clear()
        def always(*args, **kwargs):
            calls.append(1)
            raise httpx.ConnectError('EOF', request=httpx.Request('POST', 'https://x'))
        with patch('httpx.post', always), patch('time.sleep', lambda seconds: None), self.assertRaises(httpx.ConnectError):
            model_judge('k')('GB', 'ok')
        self.assertEqual(len(calls), 3)
        # 5xx retries; 4xx and read errors (the request may already be billed) do not.
        for status, expected in ((500, 3), (503, 3), (400, 1), (401, 1), (429, 1)):
            calls.clear()
            def reply(*args, status=status, **kwargs):
                calls.append(1)
                return httpx.Response(status, request=httpx.Request('POST', 'https://x'))
            with self.subTest(status=status), patch('httpx.post', reply), patch('time.sleep', lambda seconds: None):
                with self.assertRaises(httpx.HTTPStatusError):
                    model_judge('k')('GB', 'ok')
                self.assertEqual(len(calls), expected)
        calls.clear()
        def read_error(*args, **kwargs):
            calls.append(1)
            raise httpx.ReadTimeout('slow', request=httpx.Request('POST', 'https://x'))
        with patch('httpx.post', read_error), patch('time.sleep', lambda seconds: None), self.assertRaises(httpx.ReadTimeout):
            model_judge('k')('GB', 'ok')
        self.assertEqual(len(calls), 1)

    def test_cli_requires_the_key(self):
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
