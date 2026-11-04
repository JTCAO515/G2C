"""Controlled metric fixtures: no network, provider or monetary execution."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from report import report
from gates import profile_gate
from evaluate import InputError, latency


class GateChecks(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]
        self.plan=json.loads((root/'evaluation/cj028/fixtures/synthetic-plan.json').read_text())
        # 'real' here exercises the calculator branch in a controlled unit fixture.
        # It is never emitted as a real evaluation report.
        self.plan['evidence_layer']='real'
        self.rows=[]
        for language in ('zh','en'):
            for scenario in self.plan['scenarios']:
                self.rows.append(dict(candidate_id=self.plan['candidates'][0]['id'],scenario_id=scenario['id'],
                    language=language,network_id=self.plan['networks'][0]['id'],attempt=1,
                    purpose='holdout' if scenario['split']=='holdout' else 'evaluation',status='success',
                    attempt_source='synthetic metric fixture, no execution',observed_at='synthetic',source_as_of='synthetic',
                    raw_evidence_ref='synthetic:metric-record',first_body_seconds=5,full_answer_seconds=90,
                    model_calls=1,tool_calls=2,memory_calls=0,
                    judgment=dict(kind='program',independent=True,outcome='PASS',ref='eval/judge.py'),
                    independent_judgment=dict(kind='program',independent=True,ref='eval/judge.py',
                        hard_outcome='PASS',checks=[dict(name='synthetic state',status='PASS')]),
                    serious_error_review=dict(kind='program',independent=True,outcome='PASS',ref='synthetic:review')))

    def profile(self,result,language='zh',network=None):
        return next(p for p in result['quality_acceptance']['profiles']
                    if p['language']==language and (network is None or p['network_id']==network))

    def test_exact_approved_limits_pass(self):
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual({c['status'] for c in p['criteria'].values()},{'PASS'})
        self.assertEqual(p['evaluation_release_decision'],'PASS')

    def test_exact_ninety_percent_completion_passes(self):
        rows=[deepcopy(self.rows[0]) for _ in range(10)]
        for passed,failed,status in ((9,1,'PASS'),(8,2,'FAIL')):
            p=profile_gate(counts=dict(PASS=passed,FAIL=failed,UNKNOWN=0,UNRUN=0),rows=rows,
                first_body=latency(rows,'first_body_seconds'),full_answer=latency(rows,'full_answer_seconds'),
                serious_errors=[],real=True)
            self.assertEqual(p['criteria']['completion_rate']['status'],status)

    def test_plan_cannot_weaken_jt_thresholds(self):
        self.plan['approved_thresholds']=dict(completion_rate_minimum=.1,first_body_p95_maximum_seconds=999)
        self.rows[0]['first_body_seconds']=6
        self.rows[0]['judgment']['outcome']='FAIL'
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['criteria']['completion_rate']['status'],'FAIL')
        self.assertEqual(p['criteria']['first_body_p95']['status'],'FAIL')

    def test_human_task_review_still_requires_program_hard_evidence(self):
        self.rows[0]['judgment']=dict(kind='human',independent=True,outcome='PASS',ref='synthetic:human-task-review')
        self.assertEqual(self.profile(report(self.plan,self.rows))['evaluation_release_decision'],'PASS')
        self.rows[0]['independent_judgment']['kind']='model'
        self.assertEqual(self.profile(report(self.plan,self.rows))['evaluation_release_decision'],'UNKNOWN')

    def test_candidate_versions_are_never_selected_by_best_score(self):
        other=deepcopy(self.plan['candidates'][0]);other['id']='synthetic-other'
        self.plan['candidates'].append(other)
        more=[deepcopy(r)|dict(candidate_id=other['id']) for r in self.rows]
        self.rows[0]['serious_errors']=[dict(kind='program',ref='synthetic:old-failure',description='Synthetic old candidate error',resolved=False)]
        r=report(self.plan,self.rows+more)['quality_acceptance']
        self.assertEqual([c['evaluation_release_decision'] for c in r['candidates']],['FAIL','PASS'])
        self.assertEqual(r['evaluation_release_decision'],'UNKNOWN')

    def test_language_failure_cannot_be_averaged_with_other_language(self):
        self.rows[0]['judgment']['outcome']='FAIL'
        result=report(self.plan,self.rows)
        self.assertEqual(self.profile(result)['criteria']['completion_rate']['status'],'FAIL')
        self.assertEqual(self.profile(result,'en')['evaluation_release_decision'],'PASS')
        self.assertEqual(result['quality_acceptance']['evaluation_release_decision'],'FAIL')

    def test_any_serious_error_survives_resolved_flag(self):
        self.rows[0]['serious_errors']=[dict(kind='program',ref='synthetic:original-error',description='Synthetic severe violation',resolved=True)]
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['criteria']['serious_errors']['status'],'FAIL')
        self.assertEqual(p['criteria']['serious_errors']['observed_n'],1)

    def test_repeated_success_does_not_erase_original_serious_error(self):
        self.plan['attempts']=[1,2]
        repeated=[deepcopy(r)|dict(attempt=2) for r in self.rows]
        self.rows[0]['serious_errors']=[dict(kind='program',ref='synthetic:first-error',description='Synthetic first-attempt error',resolved=False)]
        p=self.profile(report(self.plan,self.rows+repeated))
        self.assertEqual(p['planned_attempt_n'],6)
        self.assertEqual(p['criteria']['serious_errors']['status'],'FAIL')

    def test_model_review_cannot_certify_zero_serious_errors(self):
        self.rows[0]['serious_error_review']['kind']='model'
        self.assertEqual(self.profile(report(self.plan,self.rows))['criteria']['serious_errors']['status'],'UNKNOWN')

    def test_model_hard_pass_cannot_certify_independent_state(self):
        self.rows[0]['independent_judgment']['kind']='model'
        self.assertEqual(self.profile(report(self.plan,self.rows))['criteria']['serious_errors']['status'],'UNKNOWN')

    def test_program_check_failure_cannot_be_overridden_by_pass_label(self):
        self.rows[0]['independent_judgment']['checks'][0]['status']='FAIL'
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['criteria']['serious_errors']['status'],'FAIL')

    def test_missing_planned_tasks_prevent_perfect_subset_release(self):
        p=self.profile(report(self.plan,self.rows[1:]))
        self.assertEqual(p['criteria']['completion_rate']['value'],1)
        self.assertEqual(p['criteria']['completion_rate']['status'],'UNKNOWN')
        self.assertEqual(p['criteria']['full_answer_p95']['status'],'UNKNOWN')

    def test_api_total_is_not_first_body_or_full_answer(self):
        for row in self.rows:
            row.pop('first_body_seconds');row.pop('full_answer_seconds');row['api_task_seconds']=.1
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['criteria']['first_body_p95']['status'],'UNKNOWN')
        self.assertEqual(p['criteria']['full_answer_p95']['status'],'UNKNOWN')

    def test_latency_limit_failure(self):
        self.rows[0]['first_body_seconds']=5.01
        self.rows[0]['full_answer_seconds']=90.01
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['criteria']['first_body_p95']['status'],'FAIL')
        self.assertEqual(p['criteria']['full_answer_p95']['status'],'FAIL')

    def test_known_slow_subset_does_not_overstate_full_p95(self):
        rows=[dict(first_body_seconds=6)]+[None]*19
        p=profile_gate(counts=dict(PASS=1,FAIL=0,UNKNOWN=0,UNRUN=19),rows=rows,
                       first_body=latency(rows,'first_body_seconds'),full_answer=latency(rows,'full_answer_seconds'),
                       serious_errors=[],real=True)
        self.assertEqual(p['criteria']['first_body_p95']['status'],'UNKNOWN')
        rows[1]=dict(first_body_seconds=6)
        p=profile_gate(counts=dict(PASS=2,FAIL=0,UNKNOWN=0,UNRUN=18),rows=rows,
                       first_body=latency(rows,'first_body_seconds'),full_answer=latency(rows,'full_answer_seconds'),
                       serious_errors=[],real=True)
        self.assertEqual(p['criteria']['first_body_p95']['status'],'FAIL')

    def test_fake_format_never_becomes_real_quality_pass(self):
        self.plan['evidence_layer']='local'
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['diagnostic_status'],'PASS')
        self.assertEqual(p['evaluation_release_decision'],'UNRUN')

    def test_networks_are_separate_and_unrun_grid_is_retained(self):
        self.plan['networks'].append(dict(id='synthetic-target',description='synthetic missing target grid'))
        result=report(self.plan,self.rows)
        self.assertEqual(self.profile(result,network='synthetic-target')['evaluation_release_decision'],'UNRUN')
        self.assertEqual(result['quality_acceptance']['evaluation_release_decision'],'UNRUN')

    def test_estimate_is_not_real_billed_fee(self):
        for row in self.rows:
            row['cost']=dict(complete=True,components=[dict(name='model',amount='0.03',currency='CNY',source='synthetic:price',basis='estimated')])
        fees=self.profile(report(self.plan,self.rows))['real_fees']
        self.assertEqual(fees['subtotals_by_basis']['estimated'],{'CNY':'0.09'})
        self.assertEqual(fees['subtotals_by_basis']['billed'],{})
        self.assertEqual(fees['status'],'UNKNOWN')

    def test_explicit_zero_bill_requires_receipt_and_complete_coverage(self):
        for row in self.rows:
            row['cost']=dict(complete=True,components=[dict(name='model',amount='0',currency='CNY',source='synthetic:bill',basis='billed',receipt_ref='synthetic:zero-receipt')])
        fees=self.profile(report(self.plan,self.rows))['real_fees']
        self.assertEqual(fees['status'],'PASS')
        self.assertEqual(fees['subtotals_by_basis']['billed'],{'CNY':'0'})
        self.rows[0]['cost']['components'][0].pop('receipt_ref')
        self.assertEqual(self.profile(report(self.plan,self.rows))['real_fees']['status'],'UNKNOWN')

    def test_unprovided_tool_volume_is_unknown_not_zero_total(self):
        for row in self.rows:row.pop('tool_calls')
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['call_volume']['tool_calls']['unknown_or_missing_attempt_n'],3)

    def test_invalid_full_answer_timing_and_call_counts_fail_boundary(self):
        for field,value in (('full_answer_seconds',float('nan')),('tool_calls',True),('memory_calls',-1)):
            row=deepcopy(self.rows[0]);row[field]=value
            with self.subTest(field=field),self.assertRaises(InputError):report(self.plan,[row])

    def test_empty_plan_observations_are_unrun(self):
        p=self.profile(report(self.plan,[]))
        self.assertEqual(p['evaluation_release_decision'],'UNRUN')


if __name__=='__main__':unittest.main()
