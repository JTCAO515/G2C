"""Collector boundaries: safe replay and observed user-body timing."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('CJ_ENV', 'local')
import real
import real_budget
import real_phase
import smoke
from real_report import reconcile


class RealCollectorChecks(unittest.TestCase):
    def test_full_over_total_budget_stops_before_credentials_claim_or_exit(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(sys,'argv',['real.py','--output',str(Path(folder)/'new')]), \
                patch.dict(os.environ,{'CJ_M4_SYNTHETIC_ONLY':'1'}), \
                patch.object(real_phase,'claimed',return_value=False), \
                patch.object(real.subprocess,'check_output',return_value='candidate'), \
                patch.object(smoke,'require_full_ready'), \
                patch.object(real_budget,'verified_journal',return_value=[dict(kind='route')]*147), \
                patch.object(real,'create_real_services',side_effect=AssertionError('no service credentials or exit')) , \
                patch.object(real,'keychain',side_effect=AssertionError('no key read')), \
                patch.object(real_phase,'claim',side_effect=AssertionError('no phase claim')), \
                patch.object(real,'AuthorizationBudget',side_effect=AssertionError('no budget mutation')):
            with self.assertRaisesRegex(ValueError,'exceeds_authorization'):
                real.main()

    def test_existing_batch_never_reads_credentials_or_creates_authorization_intent(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(sys, 'argv', ['real.py', '--output', folder]), \
                    patch.object(real, 'keychain', side_effect=AssertionError('must not read keys')), \
                    patch.object(real, 'AuthorizationBudget', side_effect=AssertionError('must not open budget')):
                self.assertEqual(real.main(), 0)

    def test_source_link_is_not_the_first_answer_body(self):
        self.assertFalse(real.body_available('Source: https://example.com\n\n'))
        self.assertFalse(real.body_available('来源：https://example.com\n'))
        self.assertTrue(real.body_available('Source: https://example.com\nActual answer'))

    def test_substantive_citation_prefixed_paragraph_is_answer_body(self):
        for body in (
            '来源：国家移民管理局官方页面的实际摘录。日期适用性和旅客资格均为 UNKNOWN。',
            'Source: Official NIA excerpts. Date applicability and eligibility remain UNKNOWN.',
        ):
            with self.subTest(body=body):
                self.assertTrue(real.body_available('来源：https://en.nia.gov.cn/\n'+body))

    def test_standalone_source_links_with_padding_remain_metadata(self):
        self.assertFalse(real.body_available('  来源：https://en.nia.gov.cn/  \n\n Source: https://example.com/path '))
        self.assertFalse(real.body_available('来源：\n Source: \t https://example.com/path '))

    def test_citation_prefixed_body_keeps_the_original_submission_clock(self):
        body='来源：官方页面实际摘录。资格 UNKNOWN。'
        snapshots=[dict(text='来源：https://en.nia.gov.cn/\n',status='running'),
                   dict(text='来源：https://en.nia.gov.cn/\n'+body,status='running'),
                   dict(text='来源：https://en.nia.gov.cn/\n'+body,status='completed')]
        class Response:
            status_code=200
            def __init__(self,snapshot):self.snapshot=snapshot
            def json(self):return dict(snapshot=self.snapshot)
        class Client:
            def get(self,*args,**kwargs):return Response(snapshots.pop(0))
        class Future:
            def result(self,**kwargs):return ['original outcome']
        with patch.object(real.time,'monotonic',side_effect=[0,1,2,3,4,5,6]),patch.object(real.time,'sleep'):
            _,_,first,full,_=real.stream_run(Client(),{},'original',Future(),0,{})
        self.assertEqual((first,full),(4,6))

    def test_body_fix_does_not_unlock_an_original_failed_smoke_phase(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(real_phase,'PHASES',Path(folder)/'phases'):
            output=Path(folder)/'original'
            output.mkdir()
            for name,value in (('plan.json',{}),('observations.json',[]),('summary.json',{})):
                (output/name).write_text(json.dumps(value))
            self.assertTrue(real_phase.claim('smoke',output,'original-candidate'))
            real_phase.finish_smoke(output,'original-candidate','FAIL')
            claim=real_phase.path_for('smoke')
            result=claim.with_suffix('.result.json')
            original=(claim.read_bytes(),result.read_bytes())
            with patch.object(smoke,'summarize',side_effect=AssertionError('failed phase must remain sealed')):
                with self.assertRaisesRegex(ValueError,'original_canonical_smoke_PASS_required'):
                    smoke.require_full_ready(output,'original-candidate')
            self.assertEqual((claim.read_bytes(),result.read_bytes()),original)

    def test_first_body_and_complete_answer_use_the_actual_client_clock(self):
        snapshots = [dict(text='Source: https://example.com\n', status='running'),
                     dict(text='Source: https://example.com\nActual answer', status='running'),
                     dict(text='Source: https://example.com\nActual answer', status='completed')]
        class Response:
            status_code = 200
            def __init__(self, snapshot): self.snapshot = snapshot
            def json(self): return dict(snapshot=self.snapshot)
        class Client:
            def get(self, *args, **kwargs): return Response(snapshots.pop(0))
        class Future:
            def result(self, **kwargs): return ['original outcome']
        evidence = {}
        with patch.object(real.time, 'monotonic', side_effect=[0,1,2,3,4,5,6]), patch.object(real.time, 'sleep'):
            events, text, first, full, outcomes = real.stream_run(Client(), {}, 'original', Future(), 0, evidence)
        self.assertEqual((first, full, outcomes), (4, 6, ['original outcome']))
        self.assertEqual(evidence['events'], events)

    def test_failed_terminal_clock_never_counts_as_a_complete_answer(self):
        row = dict(scenario_id='original', language='zh', attempt=1, raw_evidence_ref='raw/original.json',
                   status='failure', first_body_seconds=None, full_answer_seconds=2.5,
                   judgment=dict(kind='program', outcome='FAIL'), serious_errors=['original error'],
                   cost=dict(complete=False), model_calls=1)
        original = json.dumps(row, sort_keys=True)
        corrected, changes = reconcile([row], {'raw/original.json': dict(observed=dict(run_status='unknown'))})
        self.assertEqual(json.dumps(row, sort_keys=True), original)
        self.assertIsNone(corrected[0]['full_answer_seconds'])
        self.assertEqual(corrected[0]['time_to_terminal_seconds'], 2.5)
        self.assertEqual(corrected[0]['serious_errors'], row['serious_errors'])
        self.assertEqual(corrected[0]['judgment'], row['judgment'])
        self.assertEqual(corrected[0]['cost'], row['cost'])
        self.assertEqual(changes[0]['original'], 2.5)

    def test_completed_run_with_missing_required_candidate_has_no_full_answer(self):
        row = dict(scenario_id='original', language='en', attempt=1, raw_evidence_ref='raw/original.json', full_answer_seconds=4)
        corrected, changes = reconcile([row], {'raw/original.json': dict(
            observed=dict(run_status='completed'), requested_candidate_missing=True)})
        self.assertIsNone(corrected[0]['full_answer_seconds'])
        corrected, changes = reconcile([row], {'raw/original.json': dict(
            observed=dict(run_status='completed'), requested_candidate_missing=False)})
        self.assertEqual(corrected[0]['full_answer_seconds'], 4)
        self.assertEqual(changes, [])


if __name__ == '__main__': unittest.main()
