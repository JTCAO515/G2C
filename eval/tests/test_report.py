import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from report import report
from evaluate import InputError


class ReportChecks(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]
        self.plan=json.loads((root/'evaluation/cj028/fixtures/synthetic-plan.json').read_text())
        self.plan['attempts']=[1,2]
        self.row=dict(candidate_id=self.plan['candidates'][0]['id'],scenario_id=self.plan['scenarios'][0]['id'],
            language='en',network_id=self.plan['networks'][0]['id'],attempt=1,purpose='evaluation',status='success',
            attempt_source='synthetic test',observed_at='synthetic',source_as_of='synthetic',raw_evidence_ref='synthetic:raw',
            model_calls=2,api_task_seconds=1.5,judgment=dict(kind='program',independent=True,outcome='PASS',ref='eval/judge.py'),
            independent_judgment=dict(hard_outcome='PASS'))

    def group(self,result):
        return next(g for g in result['groups'] if any(a['observation'] for a in g['attempts']))

    def test_repeated_failure_is_not_averaged_away_and_calls_unknown_not_zero(self):
        rows=[self.row|dict(status='failure',judgment=dict(kind='program',independent=True,outcome='FAIL',ref='eval/judge.py')),
              self.row|dict(attempt=2,model_calls=None)]
        result=report(self.plan,rows);group=self.group(result)
        self.assertEqual(group['outcomes']['FAIL'],1)
        self.assertEqual(group['outcomes']['PASS'],1)
        self.assertEqual(group['model_calls']['known_total'],2)
        self.assertGreaterEqual(group['model_calls']['unknown_or_unrun_attempt_n'],1)
        self.assertTrue(result['repeated_uses'])
        self.assertEqual(result['release_decision'],'UNKNOWN')

    def test_model_hard_pass_is_not_program_evidence(self):
        result=report(self.plan,[self.row|dict(judgment=dict(kind='model',independent=True,outcome='PASS',ref='self'))])
        group=self.group(result)
        self.assertEqual(group['outcomes']['PASS'],0)
        self.assertEqual(group['hard_outcomes']['PASS'],0)
        self.assertEqual(sum(group['hard_outcomes'].values()),group['planned_attempt_n'])

    def test_invalid_call_counts_are_rejected(self):
        for calls in (-1,True,1.5,'2'):
            with self.subTest(calls=calls),self.assertRaises(InputError):report(self.plan,[self.row|dict(model_calls=calls)])

    def test_nonfinite_api_latency_is_rejected(self):
        for elapsed in (-1,float('nan'),float('inf'),True):
            with self.subTest(elapsed=elapsed),self.assertRaises(InputError):report(self.plan,[self.row|dict(api_task_seconds=elapsed)])


if __name__=='__main__':unittest.main()
