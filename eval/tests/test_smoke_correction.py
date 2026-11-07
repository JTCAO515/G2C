import json
import os
from contextlib import ExitStack, nullcontext
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_smoke import evidence
import hk
import real_phase
import smoke
import smoke_correction as correction


def write(path, value):
    path.write_text(json.dumps(value))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class CorrectionChecks(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.root = root
        self.original = root / 'original'
        self.original.mkdir()
        (self.original / 'raw').mkdir()
        self.output = root / 'corrected'
        self.ledger = []
        self.cases = smoke.cases('2026-11-07')
        self.original_source = dict(runner_commit='original-eval', backend_commit='approved-B', manifest_sha256='original-manifest')
        self.current_source = dict(self.original_source, runner_commit='corrected-eval', manifest_sha256='corrected-manifest')
        plan = dict(cases=self.cases, source_date='2026-11-07', planned_n=6, candidate_id='original-eval',
                    execution_source=self.original_source, batch_id='round2-smoke', model_id=smoke.M4_MODEL)
        rows = []
        for case, language in [(c, l) for c in self.cases for l in ('zh', 'en')][:-1]:
            raw = evidence(case, language, proxy=True, profile=smoke.M4_NATIVE_TURN_PROFILE_V2)
            ref = 'raw/' + case['id'] + '-' + language + '.json'
            write(self.original / ref, raw)
            self.ledger.extend(raw['authorization_attempts'])
            rows.append(dict(case_id=case['id'], language=language, raw_evidence_ref=ref,
                             first_body_seconds=1.0, full_answer_seconds=2.0))
        write(self.original / 'plan.json', plan)
        write(self.original / 'observations.json', rows)
        write(self.original / 'case-starts.json', [dict(case_id=r['case_id'], language=r['language'], attempt=1) for r in rows])
        write(self.original / 'summary.json', dict(status='FAIL'))
        write(self.original / 'budget-after.json', self.ledger)
        write(self.original / 'runtime-config.json', dict(current=dict(meter=dict(budget=100))))
        self.stack.enter_context(patch.object(real_phase, 'PHASES', root / 'phases'))
        self.assertTrue(real_phase.claim('smoke', self.original, 'original-eval'))
        real_phase.finish_smoke(self.original, 'original-eval', 'FAIL')
        self.old_claim = real_phase.path_for('smoke')
        self.old_result = self.old_claim.with_suffix('.result.json')
        self.old_bytes = self.old_claim.read_bytes(), self.old_result.read_bytes()
        self.policy_file = root / 'policy.json'
        self.policy = dict(version='C-SMOKE-CORRECTION.1', approval_ref='specific JT approval',
            original_output=str(self.original), original_candidate='original-eval', backend_commit='approved-B',
            original_manifest_sha256='original-manifest', adapter_identity=real_phase.adapter_identity(),
            claim_sha256=digest(self.old_claim), result_sha256=digest(self.old_result),
            original_file_sha256={p.relative_to(self.original).as_posix(): digest(p)
                                  for p in self.original.rglob('*') if p.is_file()},
            unchanged_eval_sha256={'eval/scenarios.json': digest(correction.ROOT / 'eval/scenarios.json')},
            approved_body_file_sha256=digest(correction.ROOT / 'eval/real.py'),
            missing_cell=dict(case_id='fact', language='en'), max_new_cases=1)
        write(self.policy_file, self.policy)
        for obj, name, value in ((correction, 'POLICY', self.policy_file), (hk, 'active', lambda: True),
                (hk, 'require_output', lambda p: None), (hk, 'source_info', lambda: self.current_source),
                (hk, 'source_candidate', lambda: 'corrected-eval'),
                (correction, 'verified_journal', lambda: self.ledger), (smoke, 'verified_journal', lambda: self.ledger)):
            self.stack.enter_context(patch.object(obj, name, value))
        self.stack.enter_context(patch.dict(os.environ, {'CJ_M4_SYNTHETIC_ONLY': '1'}))

    def run_command(self, output=None):
        with patch.object(sys, 'argv', ['smoke_correction.py', '--output', str(output or self.output)]):
            return correction.main()

    def mock_only_case(self):
        raw = evidence(self.cases[-1], 'en', proxy=True, profile=smoke.M4_NATIVE_TURN_PROFILE_V2)

        def invoke(client, database, conninfo, auth, context, services, scenario, language, subject,
                   target, *, allowed_native):
            self.assertEqual((scenario['id'], language, subject, allowed_native),
                             ('smoke-fact', 'en', 'm4-synthetic-r2-smoke-fact-en', frozenset({'fact'})))
            target.update({k: v for k, v in raw.items() if k not in ('observed', 'operations', 'authorization_attempts')})
            self.ledger.extend(raw['authorization_attempts'])
            return raw['observed'], {}, 1.0, 2.0

        def init_auth(path, subjects):
            self.assertEqual(subjects, ['m4-synthetic-r2-smoke-fact-en'])
            path.mkdir()
            (path / 'trip-confirmation.key').write_bytes(b'fixture-only')

        budget = SimpleNamespace(check_date=lambda: None, inspect=lambda: self.ledger)
        runtime = SimpleNamespace(model=SimpleNamespace(authorization=budget))
        self.stack.enter_context(patch.object(smoke, 'create_real_services', return_value=runtime))
        self.stack.enter_context(patch.object(smoke, 'private_database', return_value=nullcontext(self.root / 'conninfo')))
        self.stack.enter_context(patch.object(smoke, 'dev_auth', SimpleNamespace(init=init_auth, activate_travel=lambda *a: None)))
        self.stack.enter_context(patch.object(smoke.local_run_context, 'provision_budget'))
        for name in ('load_run_context', 'LocalDatabase', 'create_local_app', 'ConfirmationSigner'):
            self.stack.enter_context(patch.object(smoke, name))
        self.stack.enter_context(patch.object(smoke, 'tcp_app', return_value=nullcontext(object())))
        self.stack.enter_context(patch.object(smoke, 'original_operations', return_value=raw['operations']))
        return self.stack.enter_context(patch.object(smoke, 'run_case', side_effect=invoke))

    def test_only_unrun_fact_starts_once_and_same_candidate_six_can_gate_full(self):
        invoke = self.mock_only_case()
        self.assertEqual(self.run_command(), 0)
        self.assertEqual(invoke.call_count, 1)
        smoke.require_full_ready(self.output, 'corrected-eval')
        with self.assertRaisesRegex(ValueError, 'same_candidate_approved_correction_PASS_required'):
            smoke.require_full_ready(self.output, 'changed-eval')
        another = self.root / 'other-output'
        self.assertEqual(self.run_command(another), 0)
        self.assertFalse(another.exists())
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual((self.old_claim.read_bytes(), self.old_result.read_bytes()), self.old_bytes)

        # A rewritten reused row cannot be legalized by updating the new seal.
        path = self.output / 'raw/fact-zh.json'
        path.write_bytes(path.read_bytes() + b' ')
        result_path = correction.correction_path(self.policy).with_suffix('.result.json')
        result = correction.read(result_path)
        result['hashes']['raw/fact-zh.json'] = digest(path)
        write(result_path, result)
        with self.assertRaisesRegex(ValueError, 'reused_raw_bytes_changed'):
            smoke.require_full_ready(self.output, 'corrected-eval')

    def test_over_budget_stops_before_claim_or_credentials(self):
        self.ledger.extend(dict(attempt_id='old-extra-' + str(i), kind='place') for i in range(147))
        with patch.object(smoke, 'create_real_services', side_effect=AssertionError('credentials forbidden')):
            with self.assertRaisesRegex(ValueError, 'remaining_FACT_plus_full_exceeds_authorization'):
                self.run_command()
        self.assertFalse(correction.correction_path(self.policy).exists())

    def test_already_started_missing_cell_is_denied_even_when_its_file_hash_matches(self):
        path = self.original / 'case-starts.json'
        starts = correction.read(path)
        starts.append(dict(case_id='fact', language='en', attempt=1))
        write(path, starts)
        self.policy['original_file_sha256']['case-starts.json'] = digest(path)
        write(self.policy_file, self.policy)
        with self.assertRaisesRegex(ValueError, 'only_never_started_English_FACT_may_complete'):
            self.run_command()

    def test_live_receipt_change_and_dependency_change_fail_closed(self):
        self.ledger[0] = dict(self.ledger[0], state='INTENT', receipt=None)
        with self.assertRaisesRegex(ValueError, 'original_authorization_snapshot_changed'):
            self.run_command()
        self.policy['unchanged_eval_sha256']['eval/scenarios.json'] = '0' * 64
        write(self.policy_file, self.policy)
        with self.assertRaisesRegex(ValueError, 'approved_checker_and_unchanged_evaluation_dependencies_required'):
            self.run_command()

    def test_incomplete_once_only_claim_cannot_be_restarted(self):
        real_phase.exclusive(correction.correction_path(self.policy), {})
        with patch.object(smoke, 'create_real_services', side_effect=AssertionError('credentials forbidden')):
            self.assertEqual(self.run_command(), 0)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
