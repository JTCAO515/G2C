import copy
import hashlib
import json
import unittest

from eval.lio_voice import BANDS, ROOT, SCENARIOS, calibration, check_answer, count_units, load_cases, summarize


class VoiceChecks(unittest.TestCase):
    def setUp(self):
        self.case = dict(locale='en', scenario='practical', length_band='default', names=[], pinyin=[])

    def check(self, text, **changes):
        return check_answer(dict(self.case, **changes), text)

    def test_frozen_natural_dataset_coverage(self):
        doc, digest = load_cases()
        self.assertEqual(len(digest), 64)
        for locale in ('zh', 'en'):
            rows = [c for c in doc['cases'] if c['locale'] == locale]
            self.assertEqual({c['scenario'] for c in rows}, set(SCENARIOS))
            self.assertEqual(len(rows), 15)
        self.assertTrue(all('不要保存' not in c['question'] and '不要猜' not in c['question'] for c in doc['cases']))

    def test_prompt_comparison_is_explicit_preparation_not_admission(self):
        comparison = json.loads((ROOT / 'lio_voice_prompt_comparison.v1.json').read_bytes())
        self.assertEqual(comparison['dataset_sha256'], load_cases()[1])
        self.assertEqual(comparison['state'], 'ACCEPTED_SOURCE_PINS_NOT_DISPATCH_QUALIFICATION')
        self.assertEqual(comparison['final_new_source'], comparison['new_accepted']['source_commit'])
        self.assertTrue(comparison['merged_pr842'])
        self.assertEqual(comparison['comparison'], 'UNRUN')
        for arm in ('old', 'new_candidate', 'new_accepted'):
            prompt = comparison[arm]['persona_utf8']
            self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), comparison[arm]['persona_sha256'])
            self.assertEqual(len(prompt.split()), comparison[arm]['persona_whitespace_words'])
        self.assertNotEqual(comparison['old']['persona_sha256'], comparison['new_candidate']['persona_sha256'])
        self.assertEqual(comparison['final_new_prompt_sha256'], comparison['new_accepted']['persona_sha256'])

    def test_length_boundaries_both_languages_all_bands(self):
        for band, limits in BANDS.items():
            for locale, maximum in limits.items():
                with self.subTest(band=band, locale=locale):
                    text = ('字' if locale == 'zh' else 'word ') * (maximum or 200)
                    self.assertEqual(self.check(text, locale=locale, length_band=band)['checks']['length'], 'PASS')
                    if maximum:
                        text += '字' if locale == 'zh' else 'word'
                        self.assertEqual(self.check(text, locale=locale, length_band=band)['checks']['length'], 'FAIL')

    def test_word_count_chinese_pinyin_and_question_included(self):
        self.assertEqual(count_units('Say thank you (**谢谢** xièxie). Ready?', 'en'), 4)
        self.assertEqual(count_units('Say thank you (**谢谢** xie xie). Ready?', 'en', ['xie xie']), 4)
        self.assertEqual(count_units('Try Kung Pao chicken (**宫保鸡丁**). Mild or spicy?', 'en'), 7)
        self.assertEqual(count_units('A café near **故宫**. Ready?', 'en'), 4)
        self.assertEqual(count_units('A (**故宫** café). Ready?', 'en'), 3)
        self.assertEqual(count_units('Say thank you (**谢谢** xie xie). Ready?', 'en'), 4)
        self.assertEqual(count_units('你好？', 'zh'), 3)

    def test_one_final_question_and_real_exceptions(self):
        for text in ('Ready?', '准备去哪儿？', 'Ready?**'):
            self.assertEqual(self.check(text)['checks']['closing_question'], 'PASS')
        for text in ('Ready.', 'Ready? Where?', 'Where? Here.'):
            self.assertEqual(self.check(text)['checks']['closing_question'], 'FAIL')
        self.assertEqual(self.check('Call 110 now.', scenario='emergency')['checks']['closing_question'], 'PASS')
        self.assertEqual(self.check('Have a lovely trip!', scenario='greeting', farewell=True)['checks']['closing_question'], 'PASS')
        self.assertEqual(self.check('Hello!', scenario='greeting')['checks']['closing_question'], 'FAIL')

    def test_names_are_not_covered_by_unrelated_chinese(self):
        names = [dict(aliases=['Forbidden City'], chinese='故宫'), dict(aliases=['Kung Pao chicken'], chinese='宫保鸡丁')]
        self.assertEqual(self.check('Try Kung Pao chicken (**宫保鸡丁**). Mild?', names=names)['checks']['chinese_names'], 'PASS')
        self.assertEqual(self.check('Try Kung Pao chicken. **你好**?', names=names)['checks']['chinese_names'], 'FAIL')
        self.assertEqual(self.check('Forbidden City (**故宫**) then Kung Pao chicken. Ready?', names=names)['checks']['chinese_names'], 'FAIL')
        self.assertEqual(self.check('故宫怎么走？', locale='zh', names=names)['checks']['chinese_names'], 'PASS')

    def test_format_positive_and_negative(self):
        self.assertEqual(self.check('Tea or coffee?')['checks']['no_tables'], 'PASS')
        for text, key in [('| A | B |\n| --- | --- |\n| 1 | 2 |', 'no_tables'),
                          ('<table><tr><td>x</td></tr></table>', 'no_tables'),
                          ('# Nearby\nReady?', 'no_headings'), ('**Nearby**\nReady?', 'no_headings'),
                          ('Nearby\n===\nReady?', 'no_headings'), ('<h2>Nearby</h2>', 'no_headings'),
                          ('See https://example.com', 'no_links'), ('[Go](https://example.com)', 'no_links'),
                          ('See www.example.com', 'no_links'), ('See example.com/visit', 'no_links')]:
            with self.subTest(text=text):
                self.assertEqual(self.check(text)['checks'][key], 'FAIL')
        for marker in ('-', '1.'):
            self.assertEqual(self.check('\n'.join([marker+' choice']*3))['checks']['list_limit'], 'PASS')
            self.assertEqual(self.check('\n'.join([marker+' choice']*4))['checks']['list_limit'], 'FAIL')
        self.assertEqual(self.check('- Hello?', length_band='short')['checks']['list_limit'], 'FAIL')

    def test_system_terms_and_no_false_transport_hit(self):
        for text in ('您可以坐地铁。', '本轮未调用工具。', 'This turn is UNKNOWN.', 'The provider API returned a result.'):
            self.assertEqual(self.check(text)['checks']['system_language'], 'FAIL')
        for text in ('交通工具很多，坐地铁2号线？', 'Subway line 2 is an option. Ready?'):
            self.assertEqual(self.check(text)['checks']['system_language'], 'PASS')
        self.assertEqual(self.check('Luggage storage is an option. Ready?')['checks']['system_language'], 'PASS')

    def test_chinese_and_unicode_four_item_lists_are_not_missed(self):
        for text in ('• 茶\n• 饭\n• 面\n• 汤', '一、茶\n二、饭\n三、面\n四、汤'):
            with self.subTest(text=text):
                self.assertEqual(self.check(text)['checks']['list_limit'], 'FAIL')

    def test_code_redlines_do_not_claim_semantic_safety(self):
        for text in ('Coordinates 39.9042, 116.4074. Ready?', 'run_id is abc. Ready?',
                     'https://restapi.amap.com/v3/place', 'Keep calm.'):
            with self.subTest(text=text):
                self.assertTrue(self.check(text, scenario='emergency')['redline_signals'])
        result = self.check('Call 110 and move somewhere safe.', scenario='emergency')
        self.assertEqual(result['redline_signals'], [])
        self.assertTrue(result['semantic_review'].startswith('UNKNOWN'))

    def test_missing_outputs_and_unreviewed_redlines_cannot_pass(self):
        cases = [dict(self.case, id=str(i)) for i in range(10)]
        self.assertEqual(summarize(cases, {})['stage1_gate'], 'UNKNOWN')
        observations = {str(i): dict(status='completed', answer='Ready?', run_id=str(i), evidence_ref='synthetic:test', first_paragraph_seconds=i) for i in range(10)}
        result = summarize(cases, observations)
        self.assertEqual(result['stage1_gate'], 'UNKNOWN')
        self.assertEqual(result['first_paragraph']['p95'], 9)
        for r in observations.values():
            r['redline_review'] = dict(outcome='PASS', kind='model', independent=True,
                                      run_id=r['run_id'], ref='synthetic:review')
        self.assertEqual(summarize(cases, observations)['stage1_gate'], 'UNKNOWN')
        for r in observations.values():
            r['redline_review']['kind'] = 'program'
        self.assertEqual(summarize(cases, observations)['stage1_gate'], 'UNKNOWN')
        fixture = summarize(cases, observations, evidence_kind='fixture')
        self.assertEqual(fixture['fixture_or_unqualified_control_gate'], 'PASS')
        self.assertEqual(fixture['stage1_gate'], 'UNRUN')
        with self.assertRaises(ValueError): summarize(cases, observations, evidence_kind='real_service')
        observations.pop('9')
        result = summarize(cases, observations)
        self.assertEqual(result['check_rates']['length']['denominator'], 10)
        self.assertEqual(result['check_rates']['length']['numerator'], 9)
        self.assertEqual(result['stage1_gate'], 'UNKNOWN')
        observations['0']['answer'] = 'abc'
        observations['1']['answer'] = 'abc'
        self.assertEqual(summarize(cases, observations)['fixture_or_unqualified_control_gate'], 'FAIL')
        self.assertEqual(summarize(cases, observations)['stage1_gate'], 'UNKNOWN')

    def test_calibration_requires_real_labels_and_counts_missing(self):
        samples = json.loads((ROOT / 'lio_voice_calibration.v1.json').read_bytes())
        self.assertTrue(all(v['status'] == 'UNRUN' and v['agreement']['value'] is None for v in calibration(samples, {}).values()))
        samples = copy.deepcopy(samples)
        models = {}
        for row in samples['samples']:
            row.update(human_reviewer='fixture human', human_label_ref='synthetic:label')
            row['human_labels'] = dict.fromkeys(row['human_labels'], 'PASS')
            models[row['id']] = dict.fromkeys(row['human_labels'], 'PASS')
        models['cal-01']['direct_answer'] = 'FAIL'
        self.assertEqual(calibration(samples, models)['direct_answer']['agreement']['value'], .95)
        samples['samples'][0]['human_label_ref'] = None
        with self.assertRaises(ValueError):
            calibration(samples, models)

    def test_model_rates_require_original_answer_binding(self):
        case = dict(self.case, id='test')
        row = dict(status='completed', answer='Ready?', run_id='original-run', evidence_ref='synthetic:answer')
        result = summarize([case], {'test': row})
        self.assertEqual(result['model_check_rates']['direct_answer']['status'], 'UNRUN')
        row['model_review'] = dict(run_id='original-run', answer_sha256=hashlib.sha256(b'Ready?').hexdigest(),
            prompt_sha256=hashlib.sha256((ROOT / 'lio_voice_judge_prompts.md').read_bytes()).hexdigest(),
            ref='synthetic:review', reviewer='fixture-model', verdicts=dict(direct_answer='PASS', useful_question='FAIL'))
        result = summarize([case], {'test': row})
        self.assertEqual(result['model_check_rates']['direct_answer']['pass_rate']['value'], 1)
        self.assertEqual(result['model_check_rates']['useful_question']['fail_n'], 1)
        self.assertEqual(result['model_check_rates']['useful_uncertainty']['missing_n'], 1)
        row['answer'] = 'Different answer?'
        with self.assertRaises(ValueError):
            summarize([case], {'test': row})


if __name__ == '__main__':
    unittest.main()
