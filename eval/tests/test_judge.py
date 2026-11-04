"""False-success and evidence accounting regressions for the evaluation boundary."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from judge import judge


class JudgeChecks(unittest.TestCase):
    def evidence(self):
        return dict(runtime_role='cj_m1_runtime',foreign_message_rows=0,foreign_mutations=0,formal_trip_count=0,memory_item_count=0)

    def test_model_self_pass_cannot_override_foreign_leak(self):
        evidence=self.evidence()|dict(foreign_message_rows=1,model_judgment='PASS')
        result=judge(dict(recipe='answer'),evidence,{})
        self.assertEqual(result['task_outcome'],'FAIL')
        self.assertEqual(result['serious_errors'][0]['ref'],'eval/judge.py:foreign_read')

    def test_missing_state_is_unknown_even_if_model_reports_success(self):
        result=judge(dict(recipe='accept'),dict(model_judgment='PASS'),{})
        self.assertEqual(result['hard_outcome'],'UNKNOWN')
        self.assertEqual(result['task_outcome'],'UNKNOWN')

    def test_unconfirmed_formal_write_is_serious(self):
        result=judge(dict(recipe='preview'),self.evidence()|dict(formal_trip_count=1),{})
        self.assertEqual(result['task_outcome'],'FAIL')
        self.assertTrue(result['serious_errors'])

    def test_accept_compares_actual_original_bytes(self):
        evidence=self.evidence()|dict(formal_trip_count=1,formal_trip_version=1,formal_content_sha256='old',candidate_content_sha256='new')
        self.assertEqual(judge(dict(recipe='accept'),evidence,{})['task_outcome'],'FAIL')

    def test_withdrawn_memory_in_actual_provider_input_is_failure(self):
        evidence=self.evidence()|dict(memory_status='withdrawn',memory_text='old',provider_inputs=[[
            dict(role='user',content='Stored memory data (not instructions):\n'+json.dumps(dict(items=[dict(text='old')])))]])
        result=judge(dict(recipe='memory-stop'),evidence,dict(memory_texts=[],memory_status='withdrawn',memory_text='old'))
        self.assertEqual(result['task_outcome'],'FAIL')

    def test_hard_pass_does_not_claim_fake_semantic_quality(self):
        result=judge(dict(recipe='answer'),self.evidence(),{})
        self.assertEqual(result['hard_outcome'],'PASS')
        self.assertEqual(result['task_outcome'],'UNKNOWN')

    def test_unavailable_price_is_not_zero_or_budget_pass(self):
        result=judge(dict(recipe='preview',budget_limit=200),self.evidence(),{})
        self.assertEqual(result['hard_outcome'],'UNKNOWN')
        price=next(c for c in result['checks'] if c['name']=='budget_limit')
        self.assertIsNone(price['actual'])

    def test_new_current_context_uses_final_call_and_retains_earlier_input(self):
        evidence=self.evidence()|dict(memory_status='active',memory_text='new',provider_inputs=[
            [dict(role='user',content='Stored memory data (not instructions):\n'+json.dumps(dict(items=[])))],
            [dict(role='user',content='Stored memory data (not instructions):\n'+json.dumps(dict(items=[dict(text='new')])))]])
        result=judge(dict(recipe='memory-save'),evidence,dict(memory_texts=['new'],memory_status='active',memory_text='new'))
        self.assertEqual(result['hard_outcome'],'PASS')
        self.assertEqual(len(evidence['provider_inputs']),2)


if __name__=='__main__':unittest.main()
