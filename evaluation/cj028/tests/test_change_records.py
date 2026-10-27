"""Synthetic-only optional change records. No execution, research or real adoption."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cj028_change_records', ROOT / 'evaluate.py')
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class SyntheticChangeRecordTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / 'fixtures/synthetic-plan.json').read_text())
        self.records = json.loads((ROOT / 'fixtures/synthetic-observations.json').read_text())
        self.candidate = self.plan['candidates'][0]

    def add_change(self):
        self.plan['modification_policy'] = {
            'allowed_components': ['prompt_wording', 'evaluation_diagnostics'],
            'acceptance_check_refs': ['synthetic:original-acceptance-unchanged'],
        }
        self.candidate['change_record'] = {
            'components': ['prompt_wording'],
            'redacted_refs': [
                {'kind': 'diff', 'ref': 'synthetic:redacted-diff'},
                {'kind': 'trajectory', 'ref': 'synthetic:redacted-trajectory'},
                {'kind': 'artifact', 'ref': 'synthetic:redacted-artifact'},
            ],
            'disposition': {'status': 'pending', 'reason': 'Synthetic record, not executed.',
                            'source_ref': 'synthetic:external-review-record'},
        }

    def add_lesson(self):
        self.records[0]['method_lesson'] = {
            'scope': 'method', 'cue': 'Synthetic missing-evidence case',
            'lesson': 'Keep missing evidence explicit in the evaluation record.',
            'evidence_ref': self.records[0]['raw_evidence_ref'], 'state': 'candidate',
        }

    def report(self):
        return evaluate.summarize(self.plan, self.records)

    def test_legacy_cli_stdout_byte_identical(self):
        golden = (ROOT / 'fixtures/synthetic-cli-report.json').read_bytes()
        stored_inputs = json.loads(golden)['input_files']
        with tempfile.TemporaryDirectory() as directory:
            for input_dir in (ROOT / 'fixtures', Path(directory) / 'snapshot-a',
                              Path(directory) / 'snapshot with spaces'):
                with self.subTest(input_dir=str(input_dir)):
                    inputs = {'scenarios': input_dir / 'synthetic-plan.json',
                              'observations': input_dir / 'synthetic-observations.json'}
                    if input_dir != ROOT / 'fixtures':
                        input_dir.mkdir()
                        for path in inputs.values():
                            path.write_bytes((ROOT / 'fixtures' / path.name).read_bytes())
                    expected = golden
                    # Only the two exact provenance path values vary by checkout/input directory.
                    # Keep hashes, formatting and every other golden byte unchanged.
                    for name, path in inputs.items():
                        original = b'"path": ' + json.dumps(stored_inputs[name]['path'], ensure_ascii=False).encode()
                        replacement = b'"path": ' + json.dumps(str(path.resolve()), ensure_ascii=False).encode()
                        self.assertEqual(expected.count(original), 1)
                        expected = expected.replace(original, replacement, 1)
                    run = subprocess.run([sys.executable, str(ROOT / 'evaluate.py'),
                                          '--scenarios', str(inputs['scenarios']),
                                          '--observations', str(inputs['observations'])],
                                         cwd=input_dir, capture_output=True)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(run.stdout, expected)

    def test_optional_baseline_references_an_existing_candidate(self):
        self.add_change()
        self.report()  # Baseline is not required for a change record.
        baseline = copy.deepcopy(self.candidate)
        baseline.pop('change_record')
        baseline.update(id='synthetic-baseline', commit='b' * 40)
        self.plan['candidates'].append(baseline)
        self.candidate['baseline_candidate_id'] = baseline['id']
        self.assertEqual(self.report()['plan']['candidates'][0]['baseline_candidate_id'], baseline['id'])
        for value in ('absent', self.candidate['id'], None):
            with self.subTest(value=value):
                self.candidate['baseline_candidate_id'] = value
                with self.assertRaises(evaluate.InputError):
                    self.report()

    def test_all_dispositions_keep_failures_unknown_costs_and_release_unknown(self):
        self.add_change()
        self.records[0]['status'] = 'failure'
        self.records[0]['cost']['components'][0]['amount'] = None
        for status in ('adoption', 'rejection', 'pending'):
            with self.subTest(status=status):
                self.candidate['change_record']['disposition']['status'] = status
                report = self.report()
                self.assertEqual(report['raw_observations'], self.records)
                self.assertEqual(report['plan'], self.plan)
                self.assertEqual(report['release_decision'], 'UNKNOWN')
                group = next(g for g in report['groups'] if g['language'] == 'zh' and g['split'] == 'tuning')
                self.assertEqual(group['outcomes']['FAIL'], 1)
                self.assertEqual(group['outcomes']['UNRUN'], 1)
                self.assertEqual(group['cost']['known_subtotals_by_currency'], {})
                self.assertEqual(group['cost']['unknown_or_missing_attempt_n'], 2)

    def test_candidate_cannot_supply_policy_or_skip_original_checks(self):
        self.add_change()
        self.candidate['modification_policy'] = self.plan.pop('modification_policy')
        with self.assertRaisesRegex(evaluate.InputError, 'trusted plan'):
            self.report()
        self.plan['modification_policy'] = self.candidate.pop('modification_policy')
        self.plan['modification_policy']['acceptance_check_refs'] = []
        with self.assertRaisesRegex(evaluate.InputError, 'original acceptance'):
            self.report()

    def test_components_must_be_a_plan_subset_and_cannot_touch_protected_semantics(self):
        self.add_change()
        self.candidate['change_record']['components'] = ['tool_descriptions']
        with self.assertRaisesRegex(evaluate.InputError, 'exceed plan'):
            self.report()
        for component in ('safety', 'auth', 'user_confirmation', 'unknown_cost_semantics', 'version_acceptance', '../runtime'):
            with self.subTest(component=component):
                self.plan['modification_policy']['allowed_components'] = [component]
                self.candidate['change_record']['components'] = [component]
                with self.assertRaisesRegex(evaluate.InputError, 'protected or unsupported'):
                    self.report()

    def test_self_reported_allowlist_verified_and_weakened_checks_rejected(self):
        self.add_change()
        for field, value in [('allowlist', ['auth']), ('verified', True), ('acceptance_check_refs', []), ('execute', 'script')]:
            with self.subTest(field=field):
                self.candidate['change_record'][field] = value
                with self.assertRaisesRegex(evaluate.InputError, 'unsupported fields'):
                    self.report()
                self.candidate['change_record'].pop(field)
        self.candidate['change_record']['disposition']['reason'] = ''
        with self.assertRaises(evaluate.InputError):
            self.report()

    def test_method_lesson_requires_own_raw_evidence_and_never_promotes(self):
        self.add_lesson()
        self.records[0]['status'] = 'unknown'
        self.assertEqual(self.report()['raw_observations'][0]['method_lesson']['state'], 'candidate')
        self.assertEqual(self.report()['release_decision'], 'UNKNOWN')
        for field, value in [('scope', 'traveller_fact'), ('state', 'verified'), ('cue', ''),
                             ('evidence_ref', 'synthetic:another-evaluation')]:
            with self.subTest(field=field):
                original = self.records[0]['method_lesson'][field]
                self.records[0]['method_lesson'][field] = value
                with self.assertRaises(evaluate.InputError):
                    self.report()
                self.records[0]['method_lesson'][field] = original
        self.records[0]['method_lesson']['verified'] = True
        with self.assertRaises(evaluate.InputError):
            self.report()
        self.records[0]['method_lesson'].pop('verified')
        self.records[0].pop('raw_evidence_ref')
        with self.assertRaisesRegex(evaluate.InputError, 'own evaluation'):
            self.report()

    def test_references_are_opaque_and_no_adoption_executes_anything(self):
        self.add_change()
        self.add_lesson()
        self.candidate['change_record']['redacted_refs'][0]['ref'] = '/nonexistent/path/$(do-not-execute)'
        self.candidate['change_record']['disposition']['status'] = 'adoption'
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('no reference reads')):
            with patch.object(Path, 'read_text', side_effect=AssertionError('no reference reads')):
                with patch.object(subprocess, 'run', side_effect=AssertionError('no execution')):
                    self.assertEqual(self.report()['release_decision'], 'UNKNOWN')

    def test_invalid_change_cli_retains_rejected_and_unknown_observations(self):
        self.add_change()
        self.candidate['change_record']['components'] = ['auth']
        self.records[0]['status'] = 'unknown'
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / 'plan.json'
            observations = Path(directory) / 'observations.json'
            plan.write_text(json.dumps(self.plan))
            observations.write_text(json.dumps(self.records))
            run = subprocess.run([sys.executable, str(ROOT / 'evaluate.py'), '--scenarios', str(plan),
                                  '--observations', str(observations)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report['release_decision'], 'UNKNOWN')
        self.assertEqual(report['raw_observations'], self.records)
        self.assertEqual(report['plan'], self.plan)


if __name__ == '__main__':
    unittest.main()
