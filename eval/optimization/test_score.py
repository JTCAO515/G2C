"""Regressions for fail-closed scoring and planned denominators."""
from copy import deepcopy
import unittest

from evaluation.cj028.evaluate import InputError
from .examples import example_batch
from .score import dataset, score


class ScoreTests(unittest.TestCase):
    def test_bilingual_controls(self):
        for split, denominator in (('development', 12), ('validation', 8)):
            for control, expected in (('good', 'PASS'), ('bad', 'FAIL')):
                with self.subTest(split=split, control=control):
                    batch = example_batch(split, control)
                    report = score(split, batch)
                    self.assertEqual(report, score(split, deepcopy(batch)))
                    self.assertEqual(report['counts'][expected], denominator)
                    self.assertEqual(report['pass_per_planned']['denominator'], denominator)
                    for language in ('zh', 'en'):
                        self.assertEqual(report['by_language'][language]['counts'][expected], denominator // 2)

    def test_deterministic_hard_failures_survive_good_reply_labels(self):
        report = score('validation', example_batch('validation', 'bad'))
        expected_failures = {
            'val-confirm-save': {'formal_candidate_bytes', 'confirmed_commits'},
            'val-undo': {'undo_commits', 'restored_draft', 'unsupported_execution_claims'},
            'val-owner': {'foreign_read', 'foreign_write', 'foreign_trip_rows', 'foreign_trip_mutations', 'foreign_reply_hits'},
            'val-deleted-recall': {'deleted_context_hits', 'deleted_reply_hits'},
        }
        for row in report['rows']:
            with self.subTest(task=row['task_id'], language=row['language']):
                self.assertEqual(row['hard_status'], 'FAIL')
                names = {check['name'] for check in row['checks'] if check['hard'] and check['status'] == 'FAIL'}
                self.assertTrue(expected_failures[row['task_id']] <= names)

    def test_failure_overrides_unknown_and_original_denominator_stays(self):
        batch = example_batch('development', 'bad')
        record = next(row for row in batch['observations'] if row['task_id'] == 'dev-tool-failure')
        del record['state']['values']['runtime_role']
        batch['observations'] = [record]
        result = score('development', batch)
        self.assertEqual(result['counts'], {'PASS': 0, 'FAIL': 1, 'UNKNOWN': 0, 'UNRUN': 11})
        failed = next(row for row in result['rows'] if row['status'] == 'FAIL')
        checks = {check['name']: check['status'] for check in failed['checks']}
        self.assertEqual(checks['restricted_role'], 'UNKNOWN')
        self.assertEqual(checks['unsupported_execution_claims'], 'FAIL')

    def test_claims_require_consistent_state_even_with_a_verified_label(self):
        for task, effect in (('dev-tool-failure', 'tool_succeeded'), ('dev-airport', 'trip_saved')):
            with self.subTest(task=task, effect=effect):
                batch = example_batch('development', 'good')
                record = next(row for row in batch['observations'] if row['task_id'] == task)
                record['reply']['values']['claimed_effects'] = [effect]
                record['state']['values']['verified_effects'] = [effect]
                report = score('development', batch)
                row = next(row for row in report['rows'] if row['attempt_id'] == record['attempt_id'])
                self.assertEqual(row['hard_status'], 'FAIL')
                claim = next(check for check in row['checks'] if check['name'] == 'unsupported_execution_claims')
                self.assertEqual(claim['actual'], [effect])

    def test_unmatched_claim_stays_hard_fail_without_verified_effects(self):
        batch = example_batch('validation', 'good')
        record = next(row for row in batch['observations'] if row['task_id'] == 'val-owner')
        record['reply']['values']['claimed_effects'] = ['unmatched_execution_claim']
        del record['state']['values']['verified_effects']
        row = next(row for row in score('validation', batch)['rows'] if row['attempt_id'] == record['attempt_id'])
        self.assertEqual(row['hard_status'], 'FAIL')

    def test_unknown_evidence_cannot_certify_an_attempt(self):
        batch = example_batch('validation', 'good')
        records = batch['observations']
        # A successful write needs actual readback plus the separately captured candidate bytes.
        del records[0]['state']['values']['candidate_content_sha256']
        # An otherwise successful attempt is ungrounded when attached to another attempt.
        records[1]['state']['attempt_id'] = records[0]['attempt_id']
        # Missing response annotation cannot prove the absence of fabrication.
        del records[2]['reply']
        report = score('validation', batch)
        self.assertEqual(report['counts'], {'PASS': 5, 'FAIL': 0, 'UNKNOWN': 3, 'UNRUN': 0})
        self.assertEqual(report['rows'][0]['hard_status'], 'UNKNOWN')
        self.assertEqual(report['rows'][1]['hard_status'], 'UNKNOWN')
        self.assertEqual(report['rows'][2]['hard_status'], 'UNKNOWN')

    def test_boolean_zero_cannot_certify_isolation(self):
        batch = example_batch('validation', 'good')
        batch['observations'][0]['state']['values']['foreign_mutations'] = False
        report = score('validation', batch)
        self.assertEqual(report['rows'][0]['hard_status'], 'FAIL')

    def test_rejects_unpinned_or_contaminated_batch(self):
        batch = example_batch('development', 'good')
        for invalid in (dict(batch, dataset_sha256='a' * 64), dict(batch, version='unknown'),
                        dict(batch, observations=batch['observations'] * 2)):
            with self.assertRaises(InputError):
                score('development', invalid)
        for split in ('validation', 'final'):
            with self.assertRaises(InputError):
                score(split, batch)

    def test_public_allocation_preserves_travel_and_language_pairs(self):
        document, _ = dataset()
        splits = {}
        for task in document['tasks']:
            self.assertEqual(set(task['variants']), {'en', 'zh'})
            splits.setdefault(task['trip_family'], set()).add(task['split'])
        self.assertTrue(all(len(family_splits) == 1 for family_splits in splits.values()))
        self.assertEqual({task['split'] for task in document['tasks']}, {'development', 'validation'})

class LioV2ScoreTests(unittest.TestCase):
    def test_v1_source_data_and_denominators_are_retained(self):
        from hashlib import sha256
        from pathlib import Path
        from eval.optimization import score_v2
        root = Path(__file__).parent
        expected = {
            'score.py': '08dcdb1624790f735ffcb1c6db5d6f47b75ef2a28d02a20a31313256380f3adf',
            'cases.v1.json': '8e3b9c2d410e569de520243540e364d7fed6033087de8173adc5e87e17fe92f3',
            'examples.v1.json': '8139232fe3edde62a99cf078737b85376d6099e54b9b4ac69c7dda8ec18c3da5',
        }
        for name, digest in expected.items():
            self.assertEqual(sha256((root / name).read_bytes()).hexdigest(), digest)
        v1, _ = dataset()
        v2, _ = score_v2.dataset()
        self.assertEqual([(t['id'], t['split'], t['trip_family']) for t in v1['tasks']],
                         [(t['id'], t['split'], t['trip_family']) for t in v2['tasks']])
        for old, new in zip(v1['tasks'], v2['tasks'], strict=True):
            if old['id'] not in score_v2.REVISED_TASKS:
                for language in ('zh', 'en'):
                    self.assertEqual(old['variants'][language]['turns'],
                                     new['variants'][language]['turns'])

    def test_v2_release_pins_and_cross_split_setup_independence(self):
        import json
        from hashlib import sha256
        from pathlib import Path
        from eval.optimization import score_v2
        root = Path(__file__).parent
        release = json.loads((root / 'release-index.json').read_bytes())
        for section in ('active', 'historical'):
            for name, digest in release[section]['files'].items():
                self.assertEqual(sha256((root / name).read_bytes()).hexdigest(), digest)
        document, _ = score_v2.dataset()
        setups = {}
        for task in document['tasks']:
            if task['id'] in score_v2.MUTATION_TASKS:
                for variant in task['variants'].values():
                    setup = variant['steps'][0]['text']
                    self.assertEqual(setups.setdefault(setup, task['split']), task['split'])

    def test_v2_bilingual_controls_and_repeatability(self):
        from eval.optimization import score_v2, examples_v2
        for split, n in (('development', 12), ('validation', 8)):
            for control, outcome in (('good', 'PASS'), ('bad', 'FAIL')):
                with self.subTest(split=split, control=control):
                    batch = examples_v2.example_batch(split, control)
                    first = score_v2.score(split, batch)
                    self.assertEqual(first, score_v2.score(split, deepcopy(batch)))
                    self.assertEqual(first['counts'][outcome], n)
                    self.assertEqual(first['pass_per_planned']['denominator'], n)

    def test_saved_edit_catches_wrong_item_fixed_item_and_old_version(self):
        from eval.optimization import score_v2, examples_v2
        batch = examples_v2.example_batch('development', 'bad')
        rows = [row for row in score_v2.score('development', batch)['rows'] if row['task_id'] == 'dev-local-edit']
        for row in rows:
            failed = {check['name'] for check in row['checks'] if check['status'] == 'FAIL'}
            self.assertTrue({'applied_patch', 'locked_items_changed'} <= failed)
        batch = examples_v2.example_batch('development', 'good')
        record = next(row for row in batch['observations'] if row['task_id'] == 'dev-local-edit')
        record['state']['values']['formal_trip_version'] = 1
        target = next(row for row in score_v2.score('development', batch)['rows'] if row['attempt_id'] == record['attempt_id'])
        self.assertEqual(target['hard_status'], 'FAIL')

    def test_undo_restores_prior_bytes_by_appending_and_retains_history(self):
        from eval.optimization import score_v2, examples_v2
        batch = examples_v2.example_batch('validation', 'bad')
        for row in score_v2.score('validation', batch)['rows']:
            if row['task_id'] != 'val-undo':
                continue
            failed = {check['name'] for check in row['checks'] if check['status'] == 'FAIL'}
            self.assertTrue({'formal_version', 'history_versions_after', 'previous_versions_immutable'} <= failed)
        batch = examples_v2.example_batch('validation', 'good')
        record = next(row for row in batch['observations'] if row['task_id'] == 'val-undo')
        record['state']['values']['formal_content_sha256'] = 'b' * 64
        target = next(row for row in score_v2.score('validation', batch)['rows'] if row['attempt_id'] == record['attempt_id'])
        self.assertEqual(next(check for check in target['checks'] if check['name'] == 'undo_restored_content')['status'], 'FAIL')

    def test_discussion_writes_and_missing_explicit_save_are_hard_failures(self):
        from eval.optimization import score_v2, examples_v2
        for row in score_v2.score('validation', examples_v2.example_batch('validation', 'bad'))['rows']:
            if row['task_id'] == 'val-confirm-save':
                failed = {check['name'] for check in row['checks'] if check['status'] == 'FAIL'}
                self.assertTrue({'discussion_write_commits', 'write_commits', 'unsupported_execution_claims'} <= failed)

    def test_original_message_run_action_and_trip_binding(self):
        from eval.optimization import score_v2, examples_v2
        for task_id, field in (('val-confirm-save', 'committed_run_id'), ('val-undo', 'receipt_action_id')):
            with self.subTest(task=task_id, field=field):
                batch = examples_v2.example_batch('validation', 'good')
                record = next(row for row in batch['observations'] if row['task_id'] == task_id)
                record['state']['values'][field] = 'foreign-original'
                target = next(row for row in score_v2.score('validation', batch)['rows'] if row['attempt_id'] == record['attempt_id'])
                self.assertEqual(target['hard_status'], 'FAIL')

    def test_missing_native_evidence_is_unknown_and_unrun_keeps_denominator(self):
        from eval.optimization import score_v2, examples_v2
        batch = examples_v2.example_batch('validation', 'good')
        record = next(row for row in batch['observations'] if row['task_id'] == 'val-undo')
        del record['state']['values']['request_action_id']
        batch['observations'] = [record]
        result = score_v2.score('validation', batch)
        self.assertEqual(result['counts'], {'PASS': 0, 'FAIL': 0, 'UNKNOWN': 1, 'UNRUN': 7})
        self.assertEqual(result['pass_per_planned']['denominator'], 8)

    def test_weather_failure_still_requires_original_admitted_query_day(self):
        from eval.optimization import score_v2, examples_v2
        batch = examples_v2.example_batch('development', 'good')
        record = next(row for row in batch['observations'] if row['task_id'] == 'dev-tool-failure')
        record['state']['values']['weather_query_day'] = '2026-11-13'
        target = next(row for row in score_v2.score('development', batch)['rows'] if row['attempt_id'] == record['attempt_id'])
        self.assertEqual(target['hard_status'], 'FAIL')
        del record['state']['values']['weather_request_day']
        target = next(row for row in score_v2.score('development', batch)['rows'] if row['attempt_id'] == record['attempt_id'])
        self.assertEqual(target['hard_status'], 'UNKNOWN')

    def test_v1_confirmation_proof_cannot_be_relabelled_v2(self):
        from eval.optimization import score_v2
        batch = example_batch('validation', 'good')
        _, digest = score_v2.dataset()
        batch.update(version=score_v2.VERSION, dataset_version=score_v2.DATASET_VERSION, dataset_sha256=digest)
        with self.assertRaises(InputError):
            score_v2.score('validation', batch)

    def test_undo_driver_is_a_native_lio_action_and_cli_keeps_v1_output(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        from eval.optimization import score_v2, examples_v2
        document, _ = score_v2.dataset()
        undo = next(task for task in document['tasks'] if task['id'] == 'val-undo')
        for variant in undo['variants'].values():
            self.assertEqual(variant['steps'][-1], {'kind': 'lio_undo_current_trip'})
        with tempfile.TemporaryDirectory(prefix='g2c-public-version-controls-') as folder:
            for batch, scorer in ((example_batch('validation', 'good'), score),
                                  (examples_v2.example_batch('validation', 'good'), score_v2.score)):
                path = Path(folder) / 'observations.json'
                path.write_text(json.dumps(batch))
                command = [sys.executable, '-B', '-m', 'eval.optimization', '--split', 'validation', '--observations', str(path)]
                first = subprocess.run(command, check=True, capture_output=True).stdout
                second = subprocess.run(command, check=True, capture_output=True).stdout
                self.assertEqual(first, second)
                self.assertEqual(json.loads(first), scorer('validation', batch))


if __name__ == '__main__':
    unittest.main()
