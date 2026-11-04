"""Acceptance cannot pass with model-only, unknown or empty product evidence."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from real_services_acceptance import verification_passed,M4_BASE,M4_MODEL


def proof():
    cases={};attempts=[]
    for name,registration,endpoint,status in (
        ('place-zh','tool.place','https://restapi.amap.com/v3/place/text','ok'),
        ('weather-en','tool.weather','https://restapi.amap.com/v3/weather/weatherInfo','observed')):
        run='run-'+name;mid='message-'+name;operations=[]
        for key,kind,receipt in (
            ('model.tool_turn.0','model.tool_turn',dict(model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',usage={'total_tokens':10})),
            ('tool.0.0',registration,dict(endpoint=endpoint,result_status=status)),
            ('model.tool_turn.1','model.tool_turn',dict(model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',usage={'total_tokens':10}))):
            attempt=name+'-'+key
            operations.append(dict(run_id=run,operation_key=key,registration_id=kind,attempt_id=attempt))
            attempts.append(dict(attempt_id=attempt,state='RECEIVED',receipt=receipt))
        cases[name]=dict(state='completed',run_id=run,message_id=mid,operations=operations,
            display=dict(run_id=run,message_id=mid,status='completed',text_state='complete',answer_chars=30,text_sha256='a'*64))
    return dict(state='COMPLETE',cases=cases),attempts


class Verification(unittest.TestCase):
    def test_matching_tool_followup_receipts_and_product_body_required(self):
        batch,attempts=proof();self.assertTrue(verification_passed(batch,attempts))
        for mutate in (
            lambda b,a:b.update(state='UNKNOWN_INTERRUPTED'),
            lambda b,a:b['cases']['place-zh'].update(operations=b['cases']['place-zh']['operations'][:1]),
            lambda b,a:b['cases']['place-zh']['display'].update(answer_chars=0),
            lambda b,a:b['cases']['weather-en']['display'].update(run_id='different-original'),
            lambda b,a:a[2].update(state='INTENT'),
            lambda b,a:a[1]['receipt'].update(result_status='rate_limited'),
            lambda b,a:b['cases']['weather-en']['operations'][1].update(registration_id='tool.fact'),
            lambda b,a:b['cases']['place-zh'].update(operations=b['cases']['place-zh']['operations'][:2]),
        ):
            b,a=copy.deepcopy((batch,attempts));mutate(b,a)
            self.assertFalse(verification_passed(b,a))


if __name__=='__main__':unittest.main()
