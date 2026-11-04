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
        for scenario in self.plan['scenarios']:scenario['recipe']='answer'
        self.plan['networks'][0].update(kind='target_network',endpoint='https://api-beta.go2china.space',
            client_environment='Controlled unit fixture; no network execution',
            measurement=dict(kind='program',independent=True,outcome='PASS',ref='synthetic:network-measurement'))
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
                        hard_outcome='PASS',checks=[dict(name=name,status='PASS',actual=value,expected=value)
                            for name,value in (('restricted_role','cj_m1_runtime'),('foreign_read',0),('foreign_write',0),
                                               ('unconfirmed_memory_write_count',0),('formal_write_count',0))]),
                    serious_error_review=dict(kind='program',independent=True,outcome='PASS',ref='synthetic:review')))

    def profile(self,result,language='zh',network=None):
        return next(p for p in result['quality_acceptance']['profiles']
                    if p['language']==language and (network is None or p['network_id']==network))

    def direct(self,counts,rows):
        return profile_gate(counts=counts,rows=rows,first_body=latency(rows,'first_body_seconds'),
            full_answer=latency(rows,'full_answer_seconds'),serious_errors=[],real=True,
            scenarios={s['id']:s for s in self.plan['scenarios']},network=self.plan['networks'][0])

    def test_exact_approved_limits_pass(self):
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual({c['status'] for c in p['criteria'].values()},{'PASS'})
        self.assertEqual(p['evaluation_release_decision'],'PASS')

    def test_exact_ninety_percent_completion_passes(self):
        rows=[deepcopy(self.rows[0]) for _ in range(10)]
        for passed,failed,status in ((9,1,'PASS'),(8,2,'FAIL')):
            p=self.direct(dict(PASS=passed,FAIL=failed,UNKNOWN=0,UNRUN=0),rows)
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
        result=report(self.plan,self.rows)
        self.assertEqual(self.profile(result)['outcomes']['UNKNOWN'],1)
        self.assertEqual(self.profile(result)['evaluation_release_decision'],'FAIL')

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
        rows=[deepcopy(self.rows[0])|dict(first_body_seconds=6)]+[None]*19
        p=self.direct(dict(PASS=1,FAIL=0,UNKNOWN=0,UNRUN=19),rows)
        self.assertEqual(p['criteria']['first_body_p95']['status'],'UNKNOWN')
        rows[1]=deepcopy(self.rows[0])|dict(first_body_seconds=6)
        p=self.direct(dict(PASS=2,FAIL=0,UNKNOWN=0,UNRUN=18),rows)
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

    def test_one_successful_check_cannot_certify_all_required_hard_items(self):
        original=deepcopy(self.rows)
        for row in self.rows:
            row['independent_judgment']['checks']=row['independent_judgment']['checks'][:1]
        result=report(self.plan,self.rows);p=self.profile(result)
        self.assertEqual(p['outcomes']['PASS'],0)
        self.assertEqual(p['outcomes']['UNKNOWN'],3)
        self.assertEqual(p['criteria']['serious_errors']['status'],'UNKNOWN')
        self.assertNotEqual(p['evaluation_release_decision'],'PASS')
        self.assertEqual(result['raw_observations'],self.rows)
        self.assertEqual(len(original[0]['independent_judgment']['checks']),5)

    def test_program_nested_serious_error_is_not_lost_when_resolved(self):
        error=dict(kind='program',ref='eval/judge.py:foreign_write',description='Synthetic nested owner violation',resolved=True)
        self.rows[0]['independent_judgment']['serious_errors']=[error]
        result=report(self.plan,self.rows);p=self.profile(result)
        self.assertEqual(p['criteria']['serious_errors']['status'],'FAIL')
        self.assertEqual(p['outcomes']['FAIL'],1)
        self.assertEqual(p['criteria']['completion_rate']['numerator'],2)
        self.assertEqual(len(result['serious_errors']),1)
        self.assertNotIn('serious_errors',result['raw_observations'][0])

    def test_hard_fail_overrides_task_pass_in_every_numerator(self):
        self.rows[0]['independent_judgment']['checks'][2]['status']='FAIL'
        result=report(self.plan,self.rows);p=self.profile(result)
        self.assertEqual(p['criteria']['completion_rate']['numerator'],2)
        self.assertEqual(p['outcomes']['FAIL'],1)
        self.assertEqual(sum(g['outcomes']['FAIL'] for g in result['groups']),1)
        self.assertEqual(result['raw_observations'][0]['judgment']['outcome'],'PASS')

    def test_resolved_top_level_error_still_counts_as_failed_task(self):
        self.rows[0]['serious_errors']=[dict(kind='human',ref='synthetic:review',description='Synthetic severe error',resolved=True)]
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['outcomes']['FAIL'],1)
        self.assertEqual(p['criteria']['completion_rate']['numerator'],2)

    def test_estimate_plus_reservation_is_not_known_money_in_old_cost_field(self):
        for row in self.rows:
            row['cost']=dict(complete=True,components=[
                dict(name='model estimate',amount='3',currency='CNY',source='synthetic:price',basis='estimated'),
                dict(name='same task reservation',amount='10',currency='CNY',source='synthetic:reservation',basis='reserved')])
        result=report(self.plan,self.rows)
        for group in result['groups']:
            if not any(a['observation'] for a in group['attempts']):continue
            self.assertEqual(group['cost']['known_subtotals_by_currency'],{})
            self.assertFalse(group['cost']['total_cost_known'])
            self.assertEqual(group['cost']['complete_attempt_n'],0)
        self.assertEqual(self.profile(result)['real_fees']['subtotals_by_basis']['estimated'],{'CNY':'9'})
        self.assertEqual(self.profile(result)['real_fees']['subtotals_by_basis']['reserved'],{'CNY':'30'})

    def test_unknown_network_cannot_become_real_scope_pass(self):
        network=self.plan['networks'][0]
        self.plan['networks']=[dict(id=network['id'],description='UNKNOWN: collector did not measure network')]
        result=report(self.plan,self.rows);p=self.profile(result)
        self.assertEqual({c['status'] for c in p['criteria'].values()},{'PASS'})
        self.assertEqual(p['network_evidence_status'],'UNKNOWN')
        self.assertEqual(result['quality_acceptance']['evaluation_release_decision'],'UNKNOWN')

    def test_local_real_metrics_do_not_omit_required_target_network(self):
        self.plan['networks'][0].update(kind='local_real_services',endpoint='local-signed-api')
        result=report(self.plan,self.rows)
        self.assertEqual(self.profile(result)['evaluation_release_decision'],'PASS')
        self.assertEqual(result['quality_acceptance']['evaluation_release_decision'],'UNKNOWN')
        self.assertFalse(result['quality_acceptance']['candidates'][0]['target_network_planned'])

    def test_nullable_proof_and_task_judgment_are_unknown_without_crash(self):
        self.rows[0].update(independent_judgment=None,judgment=None)
        result=report(self.plan,self.rows)
        self.assertEqual(self.profile(result)['outcomes']['UNKNOWN'],1)
        self.assertIsNone(result['raw_observations'][0]['independent_judgment'])

    def test_program_pass_label_cannot_redefine_foreign_write_expected_value(self):
        check=self.rows[0]['independent_judgment']['checks'][2]
        check.update(actual=1,expected=1)
        self.assertEqual(self.profile(report(self.plan,self.rows))['outcomes']['FAIL'],1)

    def test_model_network_review_does_not_certify_measurement(self):
        self.plan['networks'][0]['measurement']['kind']='model'
        self.assertEqual(self.profile(report(self.plan,self.rows))['network_evidence_status'],'UNKNOWN')

    def test_unknown_reference_markers_cannot_certify_bills_or_reviews(self):
        for row in self.rows:
            row['cost']=dict(complete=True,components=[dict(name='model',amount='3',currency='CNY',source='synthetic:bill',basis='billed',receipt_ref='UNKNOWN')])
            row['serious_error_review']['ref']='UNKNOWN: no review'
        p=self.profile(report(self.plan,self.rows))
        self.assertEqual(p['real_fees']['status'],'UNKNOWN')
        self.assertEqual(p['criteria']['serious_errors']['status'],'UNKNOWN')


if __name__=='__main__':unittest.main()
