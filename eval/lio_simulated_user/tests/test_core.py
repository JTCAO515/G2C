from copy import deepcopy
from contextlib import redirect_stdout
import io
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eval.lio_simulated_user.core import (FACTORS, TRACE_VERSION, InputError, assess,
    load_profiles, plan, render_choice, report, simulator_messages)
from eval.lio_simulated_user.runner import HostUnavailable, run_episode


DATA, DIGEST = load_profiles()


def profile_values(profile):
    # Checker positive control only, never a baseline/DUT response generator.
    return {k: dict(value=deepcopy(v['value']), state=v['state']) for k, v in profile['hidden_answers'].items()}


def assistant(profile, *, question=None, complete=True):
    text = question or 'A plan is ready.'
    return dict(speaker='assistant', text=text,
                questions=[] if question is None else [dict(factor='city', start=0, end=len(text))],
                questions_complete=True, question_evidence='fixture', profile=profile_values(profile),
                profile_complete=True, profile_evidence='fixture',
                memory_observation=dict(origin='fixture', complete=True, text='', facts=[], ref='fixture:empty-injection'),
                exploration_complete=complete, run_outcome='completed', observation_ref='fixture:checker-only')


def trace(profile, attempt=1):
    return dict(version=TRACE_VERSION, dataset_sha256=DIGEST, profile_id=profile['id'],
                attempt=attempt, candidate='checker-fixture-not-baseline', evidence_layer='L0',
                outcome='completed', turns=[dict(speaker='user', text=profile['opening'],
                disclosures=deepcopy(profile['initial_disclosures'])), assistant(profile)],
                memory_observation=dict(origin='fixture', complete=True, text='', facts=[], ref='fixture:empty-injection'),
                cost=dict(conservative_cny=None, token_estimate_cny=None, actual_paid_cny=None))


class Metrics(unittest.TestCase):
    def test_fixed_twenty_profiles_sixty_slots_and_fourteen_factors(self):
        self.assertEqual(len(DATA['profiles']), 20)
        self.assertEqual(len(plan(DATA, DIGEST)['slots']), 60)
        self.assertTrue(all(len(p['hidden_answers']) == 14 for p in DATA['profiles']))
        self.assertEqual({p['locale'] for p in DATA['profiles']}, {'zh', 'en'})

    def test_missing_observations_are_unrun_not_zero_error_pass(self):
        value = report(DATA, DIGEST, [])
        self.assertEqual(value['overall']['outcomes'], {'UNRUN': 60})
        self.assertEqual(value['overall']['G2']['status'], 'UNRUN')
        self.assertEqual(value['overall']['G3']['denominator'], 840)
        self.assertEqual(value['by_language']['zh']['planned'], 30)
        self.assertIsNone(value['overall']['costs']['actual_paid_cny']['total'])

    def test_full_checker_positive_control_is_not_a_release(self):
        value = report(DATA, DIGEST, [trace(p, a) for p in DATA['profiles'] for a in (1, 2, 3)])
        self.assertEqual(value['overall']['G2']['status'], 'PASS')
        self.assertEqual(value['overall']['G3']['matched'], 840)
        self.assertEqual(value['overall']['G3']['status'], 'PASS')
        self.assertEqual(value['evidence_layer'], 'L0')
        self.assertEqual(value['product_release'], 'UNRUN')

    def test_known_refused_and_inferred_questions_each_fail_g2(self):
        for index, factor in ((0, 'city'), (4, 'dietary'), (2, 'party_type'), (6, 'mobility')):
            p = DATA['profiles'][index]
            t = trace(p)
            t['turns'][-1]['questions'] = [dict(factor=factor, start=0, end=4)]
            result = assess(p, t)
            self.assertEqual(result['G2']['status'], 'FAIL', (index, factor))
            self.assertEqual(result['G2']['forbidden_question_count'], 1)
            self.assertEqual(sum(result['G2']['category_counts'].values()), 1)

    def test_hidden_but_undisclosed_factor_is_not_known(self):
        p = DATA['profiles'][0];t = trace(p)
        t['turns'][-1]['questions'] = [dict(factor='lodging_tier', start=0, end=4)]
        self.assertEqual(assess(p, t)['G2']['status'], 'PASS')

    def test_actual_injected_memory_counts_known_but_unread_memory_cannot_pass(self):
        p = DATA['profiles'][0];t = trace(p);answer = p['hidden_answers']['pace']
        t['memory_observation'] = dict(origin='fixture', complete=True, text=answer['text'],
            facts=[dict(factor='pace', value=answer['value'], state='from_memory', quote=answer['text'])], ref='fixture:memory')
        t['turns'][-1]['questions'] = [dict(factor='pace', start=0, end=4)]
        self.assertEqual(assess(p, t)['G2']['violations'][0]['reason'], 'from_memory')
        t = trace(p);t['memory_observation'] = None
        self.assertEqual(assess(p, t)['G2']['status'], 'UNKNOWN')

    def test_incomplete_question_census_does_not_certify_zero(self):
        p = DATA['profiles'][0];t = trace(p)
        t['turns'][-1]['questions_complete'] = False
        self.assertEqual(assess(p, t)['G2']['status'], 'UNKNOWN')

    def test_advisory_or_missing_profile_is_not_ground_truth(self):
        p = DATA['profiles'][0]
        for profile in (None, profile_values(p)):
            t = trace(p);t['turns'][-1].update(profile=profile, profile_complete=False)
            result = assess(p, t)['G3']
            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertEqual(result['matched'], 0)
            self.assertEqual(len(result['unavailable_factors']), 14)

    def test_model_metadata_cannot_claim_accepted_or_complete_observation(self):
        p = DATA['profiles'][0]
        for key in ('question_evidence', 'profile_evidence'):
            t = trace(p);t['turns'][-1][key] = 'advisory'
            with self.assertRaises(InputError):assess(p, t)
        t = trace(p);t['evidence_layer'] = 'L2'
        with self.assertRaises(InputError):assess(p, t)

    def test_missing_accepted_profile_factors_remain_in_denominator(self):
        p = DATA['profiles'][0];t = trace(p)
        for key in FACTORS[:3]:del t['turns'][-1]['profile'][key]
        result = assess(p, t)['G3']
        self.assertEqual((result['matched'], result['denominator'], result['status']), (11, 14, 'FAIL'))

    def test_eighty_percent_boundary_is_not_rounded_up(self):
        p = DATA['profiles'][0];t = trace(p)
        for key in FACTORS[:2]:del t['turns'][-1]['profile'][key]
        self.assertEqual(assess(p, t)['G3']['status'], 'PASS')
        del t['turns'][-1]['profile'][FACTORS[2]]
        self.assertEqual(assess(p, t)['G3']['status'], 'FAIL')

    def test_boolean_cannot_match_integer_and_interests_ignore_order(self):
        p = DATA['profiles'][0];t = trace(p)
        t['turns'][-1]['profile']['duration_days']['value'] = True
        t['turns'][-1]['profile']['interests']['value'].reverse()
        result = assess(p, t)['G3']
        self.assertIn('duration_days', result['incorrect_factors'])
        self.assertIn('interests', result['matched_factors'])

    def test_partial_attempts_stay_sixty_and_cannot_be_best_of_three(self):
        p = DATA['profiles'][0];bad = trace(p, 1)
        bad['turns'][-1]['questions'] = [dict(factor='city', start=0, end=4)]
        value = report(DATA, DIGEST, [bad, trace(p, 2), trace(p, 3)])
        self.assertEqual(value['overall']['planned'], 60)
        self.assertEqual(value['overall']['G2']['status'], 'FAIL')
        self.assertEqual(value['overall']['outcomes']['UNRUN'], 57)
        with self.assertRaises(InputError):report(DATA, DIGEST, [bad, trace(p, 1)])

    def test_later_adjustment_cannot_replace_the_exploration_end_profile(self):
        p = DATA['profiles'][0];t = trace(p)
        t['turns'] += [dict(speaker='user', text='直接出方案。', disclosures=[]), assistant(p)]
        with self.assertRaises(InputError):assess(p, t)

    def test_duplicate_question_annotation_does_not_double_count_one_question(self):
        p = DATA['profiles'][0];t = trace(p)
        question = dict(factor='city', start=0, end=4)
        t['turns'][-1]['questions'] = [question, dict(question)]
        with self.assertRaises(InputError):assess(p, t)

    def test_candidate_layer_and_dataset_cannot_be_pooled(self):
        p = DATA['profiles'][0]
        for change in ({'candidate':'other'}, {'evidence_layer':'L2'}, {'dataset_sha256':'x'}):
            with self.assertRaises(InputError):report(DATA, DIGEST, [trace(p), trace(p, 2) | change])

    def test_source_annotation_cannot_omit_known_opening_or_invent_fact(self):
        p = DATA['profiles'][0]
        for change in ('omit', 'invent'):
            t = trace(p)
            if change == 'omit':t['turns'][0]['disclosures'] = []
            else:t['turns'][0]['disclosures'][0]['value'] = 'other-city'
            with self.assertRaises(InputError):assess(p, t)

    def test_failed_host_with_perfect_advisory_values_is_not_profile_pass(self):
        p = DATA['profiles'][0];t = trace(p);t['outcome'] = 'unknown'
        value = report(DATA, DIGEST, [t])
        self.assertEqual(value['results'][0]['G3']['status'], 'UNKNOWN')
        self.assertEqual(value['overall']['G3']['status'], 'UNKNOWN')

    def test_decimal_costs_missing_paid_and_failed_costs_are_retained(self):
        p = DATA['profiles'][0];t = trace(p);t['outcome'] = 'failed'
        t['cost'].update(conservative_cny='1.0000001', token_estimate_cny='0.0000001')
        value = report(DATA, DIGEST, [t])
        costs = value['overall']['costs']
        self.assertEqual(costs['conservative_cny']['known_subtotal'], '1.0000001')
        self.assertEqual(costs['actual_paid_cny']['unknown_or_unrun'], 60)
        self.assertIsNone(costs['conservative_cny']['total'])
        for amount in ('NaN', '-1', True, 0.5):
            bad = trace(p);bad['cost']['actual_paid_cny'] = amount
            with self.assertRaises(InputError):report(DATA, DIGEST, [bad])


class Simulator(unittest.TestCase):
    def test_default_entry_runs_suite_and_propagates_real_child_failure(self):
        from scripts import test as entry
        actual_run = subprocess.run
        selected = []

        def process(argv, **kwargs):
            if 'eval/lio_simulated_user/tests' in argv:
                selected.append(argv)
                return actual_run([sys.executable, '-B', '-c', 'raise SystemExit(17)'], **kwargs)
            return subprocess.CompletedProcess(argv, 0)

        with patch.object(entry.subprocess, 'run', side_effect=process), redirect_stdout(io.StringIO()):
            self.assertEqual(entry.main(), 1)
        self.assertEqual(len(selected), 1)

    def test_hidden_answers_only_enter_actor_and_dut_receives_text(self):
        profile = deepcopy(DATA['profiles'][0]);profile['behavior']['direct_after'] = 1
        profile['hidden_answers']['must_see']['value'] = ['PRIVATE-HIDDEN-MARKER']
        seen = [];actor_inputs = []
        class Dut:
            def reply(self, text, locale, *, first):
                seen.append((text, locale, first))
                return assistant(profile, complete=not first)
        class Actor:
            def choose(self, messages):
                actor_inputs.append(messages)
                return dict(answers=[], action='direct')
        result = run_episode(profile, 1, DIGEST, 'test', 'L0', Dut(), Actor(),
                             lambda: dict(conservative_cny=None, token_estimate_cny=None, actual_paid_cny=None))
        self.assertEqual(result['outcome'], 'completed')
        self.assertNotIn('PRIVATE-HIDDEN-MARKER', json.dumps(seen))
        self.assertIn('PRIVATE-HIDDEN-MARKER', json.dumps(actor_inputs))

    def test_simulator_rules_cannot_be_overridden_by_arbitrary_selection(self):
        p = DATA['profiles'][2]  # brief
        for choice in (dict(answers=['city','pace'], action='continue'),
                       dict(answers=['pace'], action='continue'),
                       dict(answers=['city','city'], action='continue')):
            with self.assertRaises(InputError):render_choice(p, choice, [dict(factor='city')], 1)
        with self.assertRaises(InputError):render_choice(p, dict(answers=[], action='continue'), [], 2)
        full = DATA['profiles'][0]
        with self.assertRaises(InputError):
            render_choice(full, dict(answers=[], action='continue'), [dict(factor='pace')], 1)

    def test_native_unknown_stops_without_a_second_submit(self):
        p = DATA['profiles'][0];calls = []
        class Dut:
            def reply(self, *args, **kwargs):calls.append(1);raise HostUnavailable()
        class Actor:
            def choose(self, messages):raise AssertionError('must not invoke actor after unknown')
        value = run_episode(p, 1, DIGEST, 'test', 'L0', Dut(), Actor(),
                            lambda: dict(conservative_cny=None, token_estimate_cny=None, actual_paid_cny=None))
        self.assertEqual(calls, [1]);self.assertEqual(value['outcome'], 'unknown')

    def test_run_bound_does_not_turn_unfinished_exploration_into_success(self):
        p = deepcopy(DATA['profiles'][0]);p['behavior']['direct_after'] = 1
        class Dut:
            def reply(self, *args, **kwargs):return assistant(p, complete=False)
        class Actor:
            def choose(self, messages):return dict(answers=[], action='direct')
        value = run_episode(p, 1, DIGEST, 'test', 'L0', Dut(), Actor(),
                            lambda: dict(conservative_cny=None, token_estimate_cny=None, actual_paid_cny=None))
        self.assertEqual(value['outcome'], 'unknown')
        self.assertEqual(assess(p, value)['G3']['status'], 'UNKNOWN')

    def test_cli_produces_all_unrun_and_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            out = str(Path(directory) / 'plan')
            args = [sys.executable, '-B', '-m', 'eval.lio_simulated_user', 'plan', '--output', out]
            first = subprocess.run(args, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            result = json.loads((Path(out) / 'report.json').read_text())
            self.assertEqual(len(result['results']), 60)
            self.assertIn('UNKNOWN', (Path(out) / 'report.md').read_text())
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)

    def test_report_retains_original_trace_byte_hash_and_observer_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'original.json'
            raw = json.dumps(trace(DATA['profiles'][0]), ensure_ascii=False, indent=2).encode()
            original.write_bytes(raw)
            out = Path(directory) / 'report'
            args = [sys.executable, '-B', '-m', 'eval.lio_simulated_user', 'report',
                    '--traces', str(original), '--output', str(out)]
            result = subprocess.run(args, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report_value = json.loads((out / 'report.json').read_bytes())
            self.assertEqual(report_value['source_traces'], [dict(ref=str(original), sha256=sha256(raw).hexdigest())])
            self.assertEqual(report_value['results'][0]['evidence_refs'], ['fixture:checker-only'])


if __name__ == '__main__':
    unittest.main()
