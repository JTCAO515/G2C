"""Audit/classification fixtures: no real producer, key, journal or HTTP."""
from copy import deepcopy
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('CJ_ENV','local')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_smoke import evidence
from smoke import cases,check
from progress import snapshot,write
from failure import parse_audit,capture,classify
from fees import usage
import test_report
from report import report


class ProgressChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'raw').mkdir()
        self.plan=dict(candidate_id='synthetic',model_id='synthetic',evidence_layer='synthetic',
            source_date='2026-11-05',cases=cases('2026-11-05'),collector_sha256='a'*64)
        (self.root/'plan.json').write_text(json.dumps(self.plan));self.rows=[];self.starts=[]

    def add(self,language='zh',unknown=False):
        case=self.plan['cases'][0];raw=evidence(case,language,proxy=True)
        if unknown:raw['observed']['run_status']='unknown';raw['outcomes'][0]['status']='unknown'
        name='raw/'+language+'.json';(self.root/name).write_text(json.dumps(raw))
        row=dict(case_id=case['id'],language=language,attempt=1,raw_evidence_ref=name,
            first_body_seconds=1.,full_answer_seconds=2.)
        self.rows.append(row);self.starts.append({k:row[k] for k in ('case_id','language','attempt')})
        return raw,row

    def formal(self):
        outcomes=[]
        for case in self.plan['cases']:
            for language in ('zh','en'):
                row=next((r for r in self.rows if r['case_id']==case['id'] and r['language']==language),None)
                status='UNRUN' if row is None else check(case,json.loads((self.root/row['raw_evidence_ref']).read_bytes()))['status']
                outcomes.append(dict(case_id=case['id'],language=language,status=status))
        return dict(status='FAIL' if any(r['status']=='FAIL' for r in outcomes) else 'UNRUN',outcomes=outcomes)

    def value(self):return snapshot('smoke',self.plan,self.rows,self.root,self.formal(),self.starts)

    def test_initial_missing_and_started_unknown_keep_full_denominator(self):
        value=self.value();self.assertEqual(value['by_language']['zh']['outcomes']['UNRUN'],3)
        self.starts.append(dict(case_id='place-route',language='en',attempt=1))
        value=self.value();group=value['by_language']['en']
        self.assertEqual(group['outcomes'],dict(PASS=0,FAIL=0,UNKNOWN=1,UNRUN=2))
        self.assertFalse(group['usage_complete']);self.assertEqual(group['unknown_inflight_usage'],'UNKNOWN')
        self.assertEqual(group['full_answer_seconds']['planned_n'],3)
        self.assertNotIn('full66_authorized_to_start',value)

    def test_unknown_run_keeps_gate_FAIL_and_execution_UNKNOWN_separate(self):
        raw,row=self.add(unknown=True);original=deepcopy(row);value=self.value()
        self.assertEqual(value['by_language']['zh']['outcomes']['FAIL'],1)
        self.assertEqual(value['by_language']['zh']['execution_status']['unknown'],1)
        self.assertIsNone(value['attempts'][0]['full_answer_seconds']);self.assertEqual(row,original)
        self.assertEqual(value['attempts'][0]['failure']['category'],'integration_protocol')
        self.assertEqual(len(value['attempts'][0]['original_attempts']),len(raw['operations']))
        self.assertEqual(value['usage']['actual_billed_cny'],'UNKNOWN')

    def test_registered_attempt_without_intent_is_retained_as_unknown(self):
        raw,row=self.add();raw['authorization_attempts'].pop()
        (self.root/row['raw_evidence_ref']).write_text(json.dumps(raw));value=self.value()
        self.assertIn('NO_RECORDED_INTENT',[a['authorization_state'] for a in value['attempts'][0]['original_attempts']])
        self.assertFalse(value['attempt_manifest_complete']);self.assertFalse(value['usage_complete'])

    def test_orphan_intent_is_also_retained_without_inventing_registration(self):
        raw,row=self.add();raw['authorization_attempts'].append(dict(attempt_id='synthetic-orphan',kind='model',input_sha='f'*64,state='INTENT',receipt=None))
        (self.root/row['raw_evidence_ref']).write_text(json.dumps(raw));value=self.value()
        orphan=next(a for a in value['attempts'][0]['original_attempts'] if a['attempt_id']=='synthetic-orphan')
        self.assertIsNone(orphan['operation_key']);self.assertEqual(value['usage']['unknown_intents']['model'],1)
        self.assertFalse(value['usage_complete'])

    def test_original_failure_is_not_averaged_with_later_success(self):
        self.add(unknown=True);self.add(language='en')
        value=self.value();self.assertEqual(value['by_language']['zh']['outcomes']['FAIL'],1)
        self.assertEqual(value['by_language']['en']['outcomes']['PASS'],1)
        self.assertEqual(value['original_gate_status'],'FAIL')

    def test_duplicate_cell_or_attempt_never_selects_best(self):
        raw,row=self.add();self.rows.append(deepcopy(row))
        with self.assertRaises(ValueError):self.value()
        self.rows.pop();raw['authorization_attempts'].append(deepcopy(raw['authorization_attempts'][0]))
        (self.root/row['raw_evidence_ref']).write_text(json.dumps(raw))
        with self.assertRaises(ValueError):self.value()

    def test_actual_raw_hash_and_atomic_current_report_are_written(self):
        raw,row=self.add();before=(self.root/row['raw_evidence_ref']).read_bytes()
        value=write('smoke',self.plan,self.rows,self.root,self.formal(),self.starts)
        self.assertEqual(value['attempts'][0]['raw_evidence_sha256'],sha256(before).hexdigest())
        self.assertEqual((self.root/row['raw_evidence_ref']).read_bytes(),before)
        self.assertTrue((self.root/'progress.md').is_file());self.assertFalse((self.root/'progress.tmp').exists())

    def test_invalid_clock_cannot_create_latency_statistics(self):
        self.add();self.rows[0]['first_body_seconds']=float('nan')
        with self.assertRaises(ValueError):self.value()

    def test_raw_reference_cannot_escape_batch_or_follow_a_symlink(self):
        self.add();self.rows[0]['raw_evidence_ref']='../outside.json'
        with self.assertRaisesRegex(ValueError,'original_batch_raw_path'):self.value()
        link=self.root/'raw/link.json';link.symlink_to(self.root/'raw/zh.json')
        self.rows[0]['raw_evidence_ref']='raw/link.json'
        with self.assertRaisesRegex(ValueError,'original_batch_raw_path'):self.value()

    def test_full_repeated_attempts_and_original_serious_gate_are_preserved(self):
        fixture=test_report.ReportChecks();fixture.setUp();plan=fixture.plan
        rows=[fixture.row|dict(raw_evidence_ref='raw/first.json',status='failure',judgment=dict(kind='program',independent=True,outcome='FAIL',ref='eval/judge.py')),
              fixture.row|dict(raw_evidence_ref='raw/second.json',attempt=2)]
        for i,row in enumerate(rows):
            raw=dict(observed=dict(run_status='completed',message_receipt=dict(run_id='synthetic-'+str(i),message_id='m-'+str(i))),
                     operations=[],authorization_attempts=[])
            (self.root/row['raw_evidence_ref']).write_text(json.dumps(raw))
        original=report(plan,rows);starts=[dict(scenario_id=r['scenario_id'],language=r['language'],attempt=r['attempt']) for r in rows]
        value=snapshot('full',plan,rows,self.root,original,starts)
        self.assertEqual(value['by_language']['en']['outcomes']['FAIL'],1)
        self.assertEqual(value['by_language']['en']['outcomes']['PASS'],1)
        self.assertEqual(value['by_language']['en']['original_product_profiles'],[p for p in original['quality_acceptance']['profiles'] if p['language']=='en'])


class FailureChecks(unittest.TestCase):
    def test_diagnostic_is_bound_to_original_attempt_and_never_guesses_finish(self):
        aid='synthetic-attempt';digest=sha256(aid.encode()).hexdigest()
        text=f'M4_MODEL_UNKNOWN attempt_sha256={digest} phase=choice http_status=200 done=False finished=False usage=False content_chars=0 tool_count=1'
        events=parse_audit(text);self.assertEqual(len(events),1)
        raw=dict(operations=[dict(attempt_id=aid)],provider_failure_diagnostics=events)
        result=classify(raw,'FAIL');self.assertEqual(result['category'],'integration_protocol')
        self.assertEqual(result['stage'],'choice');self.assertEqual(result['root_cause'],'UNKNOWN')
        raw['operations']=[];self.assertEqual(classify(raw,'FAIL')['category'],'UNKNOWN')

    def test_logger_capture_removes_handler_and_retains_no_content(self):
        logger=logging.getLogger('cj_provider.audit');original=list(logger.handlers);raw={}
        with self.assertRaises(ValueError):
            with capture(raw):
                logger.warning('synthetic private text not a diagnostic')
                raise ValueError('synthetic')
        self.assertEqual(logger.handlers,original);self.assertEqual(raw['provider_failure_diagnostics'],[])

    def test_components_are_separate_from_model_quality_and_model_claims(self):
        for raw,expected in ((dict(error_kind='PermissionError'),'environment'),
                (dict(error_kind='ValueError',execution_stage='independent_judge'),'judge'),
                (dict(authorization_attempts=[dict(kind='fact',state='INTENT')]),'source_tool'),
                (dict(authorization_attempts=[dict(kind='route',state='RECEIVED',receipt=dict(result_status='invalid_response'))]),'source_tool'),
                (dict(observed=dict(run_status='unknown'),answer='{"kind":"model","category":"model_quality"}'),'integration_protocol'),
                (dict(judgment=dict(kind='model',independent=True,checks=[dict(name='max_days',status='FAIL')])),'UNKNOWN'),
                (dict(judgment=dict(kind='program',independent=True,checks=[dict(name='max_days',status='FAIL')])),'model_quality')):
            with self.subTest(expected=expected):self.assertEqual(classify(raw,'FAIL')['category'],expected)

    def test_malformed_usage_stays_unknown_and_never_counts_string_characters(self):
        attempts=[dict(attempt_id='synthetic',kind='model',state='RECEIVED',receipt=dict(usage='UNKNOWN'))]
        result=usage(attempts);self.assertEqual(result['model_tokens_from_complete_receipts'],{})
        self.assertEqual(result['token_unknown_model_attempt_n'],1);self.assertIsNone(result['token_price_estimate']['entire_model_estimate_cny'])
        self.assertEqual(result['conservative_hold_cny']['model'],1)


if __name__=='__main__':unittest.main()
