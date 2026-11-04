from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fees import token_estimate


def received(i,o):
    return dict(kind='model',state='RECEIVED',receipt=dict(model_id='qwen3.8-flash',region='cn-beijing',
        usage=dict(prompt_tokens=i,completion_tokens=o,total_tokens=i+o)))


class FeesChecks(unittest.TestCase):
    def test_known_receipts_match_prior_public_price_estimate_exactly(self):
        r=token_estimate([received(1294,129)])
        self.assertEqual(r['known_receipt_subtotal_cny'],'0.0013835')
        self.assertEqual(r['actual_billed_cny'],'UNKNOWN')

    def test_unknown_window_does_not_become_zero_total_or_release_hold(self):
        r=token_estimate([received(1294,129),dict(kind='model',state='INTENT',receipt=None)])
        self.assertIsNone(r['entire_model_estimate_cny'])
        self.assertEqual(r['unknown_model_attempts'],1)
        self.assertEqual(r['known_receipt_subtotal_cny'],'0.0013835')

    def test_no_known_usage_does_not_estimate_an_entire_zero_bill(self):
        r=token_estimate([dict(kind='model',state='INTENT',receipt=None),dict(kind='route',state='RECEIVED',receipt={})])
        self.assertIsNone(r['entire_model_estimate_cny'])
        self.assertEqual(r['tool_monetary_cost'],'UNKNOWN')

    def test_unreconciled_token_usage_is_unknown(self):
        row=received(100,10);row['receipt']['usage']['total_tokens']=99
        self.assertEqual(token_estimate([row])['unknown_model_attempts'],1)


if __name__=='__main__':unittest.main()
