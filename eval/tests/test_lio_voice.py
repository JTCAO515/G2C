import copy
import hashlib
import json
import unittest

from eval.lio_voice import (BANDS, ROOT, SCENARIOS, calibration, check_answer, compare,
                            count_units, digest, load_cases, scope_digest, strict_json, summarize)


def original_row(case, identity, prompt='fixture persona'):
    """Synthetic association controls, never actual provider or capture evidence."""
    answer = 'Call 110 now.' if case['scenario'] == 'emergency' else 'Ready?'
    if case.get('expects_chinese') and case['locale'] == 'en':
        answer = '中 ' + answer
    row = dict(status='completed', answer=answer, run_id=identity, operation_id=identity,
               attempt_id=identity+'-attempt', answer_view='raw', evidence_ref='fixture:answer')
    original = dict(version='LIO-voice-original.1', question_utf8=case['question'],
                    **{k: row[k] for k in ('run_id', 'operation_id', 'attempt_id', 'answer_view')})
    raw = dict(input=json.dumps(dict(system=prompt, messages=[dict(role='user', content=case['question'])])),
               answer=answer, context_evidence='fixture context', state_evidence='fixture state')
    for key, value in raw.items():
        original[key+'_utf8'], original[key+'_sha256'] = value, digest(value)
    row['original'] = original
    row['redline_review'] = dict(outcome='PASS', kind='program', independent=True, run_id=identity,
        ref='fixture:review', answer_sha256=digest(answer), scope_sha256=scope_digest(row))
    return row


def fixture_bundle():
    cases, dataset_hash = load_cases()
    pins = strict_json((ROOT/'lio_voice_prompt_comparison.v1.json').read_bytes())
    arms = {}
    for name in ('old', 'new'):
        pin = pins['old' if name == 'old' else 'new_accepted']
        arms[name] = dict(source_commit='1'*40, prompt_source_commit=pin['source_commit'],
            prompt_sha256=pin['persona_sha256'], model_profile='fixture-model', window_id='fixture-window',
            evidence_kind='fixture', observations={c['id']: original_row(c, name+'-'+c['id'], pin['persona_utf8']) for c in cases['cases']})
    return dict(dataset_sha256=dataset_hash, arms=arms)


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
            r['original'] = dict(version='fixture-control')
            r['redline_review'].update(answer_sha256=digest(r['answer']), scope_sha256=scope_digest(r))
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
        row['original'] = dict(version='fixture-control')
        result = summarize([case], {'test': row})
        self.assertEqual(result['model_check_rates']['direct_answer']['status'], 'UNRUN')
        row['model_review'] = dict(run_id='original-run', answer_sha256=hashlib.sha256(b'Ready?').hexdigest(),
            scope_sha256=scope_digest(row),
            prompt_sha256=hashlib.sha256((ROOT / 'lio_voice_judge_prompts.md').read_bytes()).hexdigest(),
            ref='synthetic:review', reviewer='fixture-model', verdicts=dict(direct_answer='PASS', useful_question='FAIL'))
        result = summarize([case], {'test': row})
        self.assertEqual(result['model_check_rates']['direct_answer']['pass_rate']['value'], 1)
        self.assertEqual(result['model_check_rates']['useful_question']['fail_n'], 1)
        self.assertEqual(result['model_check_rates']['useful_uncertainty']['missing_n'], 1)
        row['answer'] = 'Different answer?'
        with self.assertRaises(ValueError):
            summarize([case], {'test': row})

    def test_duplicate_json_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            strict_json('{"arms":{},"arms":{}}')

    def test_compare_rejects_wrong_pins_and_reused_attempts(self):
        bundle = fixture_bundle()
        report = compare(bundle)
        self.assertTrue(all(row['stage1_gate'] == 'UNRUN' for arm in report['arms'].values() for row in arm['languages'].values()))
        for field, value in (('prompt_source_commit', '0'*40), ('prompt_sha256', '0'*64), ('source_commit', 'not-a-commit')):
            with self.subTest(field=field):
                changed = copy.deepcopy(bundle)
                changed['arms']['old'][field] = value
                with self.assertRaises(ValueError): compare(changed)
        case = load_cases()[0]['cases'][0]
        changed = copy.deepcopy(bundle)
        old = changed['arms']['old']['observations'][case['id']]
        new = changed['arms']['new']['observations'][case['id']]
        for key in ('operation_id', 'attempt_id'):
            new[key] = new['original'][key] = old[key]
        with self.assertRaises(ValueError): compare(changed)

    def test_compare_binds_question_input_and_exact_answer_bytes(self):
        bundle = fixture_bundle()
        case = load_cases()[0]['cases'][0]
        for key, value in (('question_utf8', 'another question'), ('answer_utf8', 'another answer'), ('input_sha256', '0'*64)):
            with self.subTest(key=key):
                changed = copy.deepcopy(bundle)
                changed['arms']['old']['observations'][case['id']]['original'][key] = value
                with self.assertRaises(ValueError): compare(changed)
        changed = copy.deepcopy(bundle)
        original = changed['arms']['old']['observations'][case['id']]['original']
        logical = strict_json(original['input_utf8'])
        logical['system'] = 'another persona'
        original['input_utf8'] = json.dumps(logical)
        original['input_sha256'] = digest(original['input_utf8'])
        with self.assertRaises(ValueError): compare(changed)

    def test_stale_safe_review_cannot_pass_changed_answer_or_state(self):
        case = dict(self.case, id='same-run', question='Can you plan a walk?')
        row = original_row(case, 'same-run')
        self.assertEqual(summarize([case], {case['id']:row}, evidence_kind='fixture')['fixture_or_unqualified_control_gate'], 'PASS')
        changed = copy.deepcopy(row)
        changed['answer'] = changed['original']['answer_utf8'] = 'I booked and paid for your hotel. Want a route?'
        changed['original']['answer_sha256'] = digest(changed['answer'])
        result = summarize([case], {case['id']:changed}, evidence_kind='fixture')
        self.assertEqual(result['grounded_redline_pass_n'], 0)
        self.assertEqual(result['fixture_or_unqualified_control_gate'], 'UNKNOWN')
        changed = copy.deepcopy(row)
        changed['original']['state_evidence_utf8'] = 'changed fixture state'
        changed['original']['state_evidence_sha256'] = digest('changed fixture state')
        self.assertEqual(summarize([case], {case['id']:changed})['grounded_redline_pass_n'], 0)


if __name__ == '__main__':
    unittest.main()
