"""All records in this suite are synthetic; no product acceptance evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cj028_evaluate', ROOT / 'evaluate.py')
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class SyntheticRecordsTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / 'fixtures/synthetic-plan.json').read_text())
        self.records = json.loads((ROOT / 'fixtures/synthetic-observations.json').read_text())

    def report(self):
        return evaluate.summarize(self.plan, self.records)

    def group(self, report, language='zh', candidate='synthetic-a', split='tuning'):
        return next(g for g in report['groups'] if g['language'] == language
                    and g['candidate_id'] == candidate and g['split'] == split)

    def test_independent_count_and_bilingual_missing_denominators(self):
        report = self.report()
        self.assertEqual(report['independent_product_scenario_n'], 3)
        self.assertEqual(report['holdout_product_scenario_n'], 1)
        self.assertEqual(self.group(report)['planned_attempt_n'], 2)
        self.assertEqual(self.group(report, 'en')['outcomes'], {'PASS': 0, 'FAIL': 0, 'UNKNOWN': 0, 'UNRUN': 2})
        self.assertIsNone(self.group(report, 'en')['pass_rate']['value'])

    def test_failure_timeout_unknown_missing_are_not_discarded(self):
        self.plan['attempts'] = [1, 2, 3, 4, 5]
        base = self.records[0]
        self.records = []
        for a, status in enumerate(('success', 'failure', 'timeout', 'unknown', 'missing'), 1):
            row = copy.deepcopy(base)
            row.update(attempt=a, status=status)
            self.records.append(row)
        group = self.group(self.report())
        self.assertEqual(group['outcomes'], {'PASS': 1, 'FAIL': 1, 'UNKNOWN': 2, 'UNRUN': 6})
        self.assertEqual(group['pass_rate']['denominator'], 4)
        self.assertEqual(len(group['attempts']), 10)
        self.assertEqual(len(self.report()['raw_observations']), 5)

    def test_no_success_certification_from_label_or_model_judge(self):
        self.records[0].pop('judgment')
        self.assertEqual(self.group(self.report())['outcomes']['UNKNOWN'], 1)
        self.records[0]['judgment'] = {'kind': 'model', 'independent': True, 'outcome': 'PASS', 'ref': 'synthetic:model'}
        self.assertEqual(self.group(self.report())['outcomes']['PASS'], 0)

    def test_pass_requires_independent_raw_evidence(self):
        self.records[0]['judgment']['independent'] = False
        self.assertEqual(self.group(self.report())['outcomes']['PASS'], 0)
        self.records[0]['judgment']['independent'] = True
        self.records[0].pop('raw_evidence_ref')
        self.assertEqual(self.group(self.report())['outcomes']['PASS'], 0)

    def test_duplicate_attempt_rejected(self):
        self.records.append(copy.deepcopy(self.records[0]))
        with self.assertRaisesRegex(evaluate.InputError, 'duplicate attempt'):
            self.report()

    def test_candidate_versions_not_pooled(self):
        candidate = copy.deepcopy(self.plan['candidates'][0])
        candidate.update(id='synthetic-b', commit='b' * 40, config_version='synthetic-config-b')
        self.plan['candidates'].append(candidate)
        row = copy.deepcopy(self.records[0])
        row.update(candidate_id='synthetic-b', status='failure')
        self.records.append(row)
        report = self.report()
        self.assertEqual(self.group(report)['outcomes']['PASS'], 1)
        self.assertEqual(self.group(report, candidate='synthetic-b')['outcomes']['FAIL'], 1)
        self.assertEqual(len(report['repeated_uses']), 1)

    def test_conflicting_candidate_fingerprint_rejected(self):
        for field in ('commit', 'config_version', 'model_version'):
            with self.subTest(field=field):
                rows = copy.deepcopy(self.records)
                rows[0][field] = 'conflicting-version'
                with self.assertRaisesRegex(evaluate.InputError, 'conflicts with candidate'):
                    evaluate.summarize(self.plan, rows)

    def test_unknown_ids_and_language_pairing_rejected(self):
        for field, value in [('scenario_id', 'absent'), ('language', 'fr'), ('candidate_id', 'absent'), ('network_id', 'absent'), ('attempt', 2)]:
            with self.subTest(field=field):
                rows = copy.deepcopy(self.records)
                rows[0][field] = value
                with self.assertRaises(evaluate.InputError):
                    evaluate.summarize(self.plan, rows)
        self.plan['scenarios'][0]['inputs'].pop('en')
        with self.assertRaisesRegex(evaluate.InputError, 'zh/en'):
            self.report()

    def test_one_third_hard_gate_uses_product_scenarios(self):
        extra = copy.deepcopy(self.plan['scenarios'][0])
        extra.update(id='synthetic-four')
        self.plan['scenarios'].append(extra)
        with self.assertRaisesRegex(evaluate.InputError, '1/3'):
            self.report()
        extra['product'] = False
        self.assertEqual(self.report()['holdout_fraction']['denominator'], 3)

    def test_holdout_tuning_history_and_observed_leakage_rejected(self):
        holdout = self.plan['scenarios'][2]
        holdout['used_for_tuning'] = True
        with self.assertRaisesRegex(evaluate.InputError, 'leakage'):
            self.report()
        holdout['used_for_tuning'] = False
        self.records[0].update(scenario_id=holdout['id'], purpose='tuning')
        with self.assertRaisesRegex(evaluate.InputError, 'leakage'):
            self.report()

    def test_repeated_holdout_visible_without_cherry_picking(self):
        self.plan['attempts'] = [1, 2]
        self.records[0].update(scenario_id='synthetic-three', purpose='holdout', status='failure')
        row = copy.deepcopy(self.records[0])
        row.update(attempt=2, status='success')
        self.records.append(row)
        report = self.report()
        self.assertEqual(report['repeated_uses'][0]['split'], 'holdout')
        self.assertEqual(self.group(report, split='holdout')['outcomes']['FAIL'], 1)
        self.assertEqual(self.group(report, split='holdout')['outcomes']['PASS'], 1)

    def test_unknown_cost_not_zero_and_currency_not_converted(self):
        self.records[0]['cost']['components'].append({'name': 'retry', 'amount': None, 'currency': 'USD', 'source': 'synthetic:unknown'})
        report = self.report()
        cost = self.group(report)['cost']
        self.assertEqual(cost['known_subtotals_by_currency'], {'USD': '0.03'})
        self.assertEqual(cost['unknown_or_missing_attempt_n'], 2)
        self.assertFalse(cost['total_cost_known'])
        self.assertEqual(self.group(report, 'en')['cost']['known_subtotals_by_currency'], {})

    def test_unconfirmed_thresholds_never_release(self):
        self.assertEqual(self.report()['release_decision'], 'UNKNOWN')
        self.assertIn('thresholds unconfirmed', self.report()['release_blockers'])
        self.assertEqual(evaluate.summarize(self.plan, [])['release_decision'], 'UNRUN')
        self.plan['approved_thresholds'] = {'claimed': 'synthetic:approval'}
        self.assertEqual(self.report()['release_decision'], 'UNKNOWN')

    def test_external_serious_errors_separate_by_language(self):
        self.records[0]['serious_errors'] = [{'kind': 'human', 'ref': 'synthetic:external-review',
                                            'description': 'synthetic constraint violation', 'resolved': False}]
        report = self.report()
        self.assertEqual(self.group(report)['outcomes']['FAIL'], 1)
        self.assertEqual(report['serious_errors'][0]['attempt_key'][2], 'zh')
        self.assertEqual(len(self.group(report)['serious_errors']), 1)
        self.assertEqual(self.group(report, 'en')['serious_errors'], [])
        self.assertIn('unresolved externally judged serious errors', report['release_blockers'])
        self.records[0]['serious_errors'][0]['kind'] = 'model'
        with self.assertRaises(evaluate.InputError):
            self.report()

    def test_latency_percentiles_keep_missing_and_timeout_context(self):
        self.plan['attempts'] = [1, 2]
        row = copy.deepcopy(self.records[0])
        row.update(attempt=2, status='timeout', first_body_seconds=None, draft_seconds=None)
        self.records.append(row)
        group = self.group(self.report())
        self.assertEqual(group['first_body_seconds']['known_n'], 1)
        self.assertEqual(group['first_body_seconds']['planned_n'], 4)
        self.assertEqual(group['first_body_seconds']['p95'], 2)
        self.assertEqual(group['statuses']['timeout'], 1)
        self.assertEqual(group['first_body_seconds']['threshold_decision'], 'UNKNOWN')

    def test_task_kinds_not_pooled_for_latency(self):
        self.plan['scenarios'][1]['task_kind'] = 'synthetic-planning'
        report = self.report()
        groups = [g for g in report['groups'] if g['language'] == 'zh' and g['split'] == 'tuning']
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(g['planned_attempt_n'] == 1 for g in groups))
        self.assertEqual(sorted(g['first_body_seconds']['known_n'] for g in groups), [0, 1])

    def test_network_and_language_measurements_not_pooled(self):
        self.plan['networks'].append({'id': 'synthetic-other-network', 'description': 'Not real.'})
        row = copy.deepcopy(self.records[0])
        row.update(language='en', network_id='synthetic-other-network', status='failure')
        self.records.append(row)
        report = self.report()
        self.assertEqual(sum(g['outcomes']['PASS'] for g in report['groups']), 1)
        self.assertEqual(sum(g['outcomes']['FAIL'] for g in report['groups']), 1)
        failed = next(g for g in report['groups'] if g['outcomes']['FAIL'])
        self.assertEqual((failed['language'], failed['network_id']), ('en', 'synthetic-other-network'))

    def test_duplicate_json_fields_and_nonfinite_numbers_rejected(self):
        for raw in (b'{"id": 1, "id": 2}', b'[NaN]', b'[Infinity]'):
            with self.subTest(raw=raw):
                with self.assertRaises(evaluate.InputError):
                    evaluate.read_json(raw)

    def test_bad_cost_latency_and_provenance_rejected(self):
        for field, value in [('first_body_seconds', -1), ('draft_seconds', True),
                             ('source_as_of', ''), ('attempt_source', ''), ('attempt', True)]:
            with self.subTest(field=field):
                rows = copy.deepcopy(self.records)
                rows[0][field] = value
                with self.assertRaises(evaluate.InputError):
                    evaluate.summarize(self.plan, rows)
        for value in ('NaN', 'Infinity', '-1', 0):
            with self.subTest(cost=value):
                rows = copy.deepcopy(self.records)
                rows[0]['cost']['components'][0]['amount'] = value
                with self.assertRaises(evaluate.InputError):
                    evaluate.summarize(self.plan, rows)

    def test_cli_explicit_files_and_invalid_records_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / 'plan.json'
            records = Path(directory) / 'observations.json'
            plan.write_text(json.dumps(self.plan))
            records.write_text(json.dumps(self.records * 2))
            run = subprocess.run([sys.executable, str(ROOT / 'evaluate.py'), '--scenarios', str(plan),
                                  '--observations', str(records)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            report = json.loads(run.stdout)
            self.assertEqual(report['validation'], 'FAIL')
            self.assertEqual(report['release_decision'], 'UNKNOWN')
            self.assertEqual(len(report['raw_observations']), 2)
            self.assertEqual(len(report['input_files']['scenarios']['sha256']), 64)


if __name__ == '__main__':
    unittest.main()
