"""Fixed pure-GET diagnostic; synthetic HTTP responses never count as network proof."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import os

import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('CJ_ENV','local')
import network_read as probe
from failure import parse_audit
from cj_api.run_display_projection import encode_response


def snapshot():
    return dict(conversation_id=probe.MESSAGE,generation=probe.GENERATION,message_id=probe.MESSAGE,
        run_id=probe.RUN,message_sequence=1,status='completed',event_highwater=2,
        text='synthetic source; not a quality assessment',text_state='complete')


class NetworkReadChecks(unittest.TestCase):
    def test_exact_existing_v1_envelope_six_GETs_and_never_quality_PASS(self):
        calls=[]
        def handle(request):
            calls.append(request)
            self.assertEqual((request.method,request.url.host,request.url.path),('GET','api-beta.go2china.space','/v1/run-display'))
            self.assertEqual(request.url.params['message_id'],probe.MESSAGE)
            body=encode_response(json.dumps(snapshot()).encode(),'r')
            return httpx.Response(200,headers={'X-Request-ID':'r','Cache-Control':'no-store'},content=body)
        with tempfile.TemporaryDirectory() as folder,httpx.Client(transport=httpx.MockTransport(handle)) as client:
            result=probe.collect(client,Path(folder)/'out',dict(kind='synthetic_unit'))
            self.assertEqual(len(calls),6);self.assertEqual(result['outcomes'],dict(PASS=6,FAIL=0,UNKNOWN=0))
            self.assertEqual(result['quality_release_decision'],'UNRUN')
            self.assertEqual(result['submitted_messages'],0);self.assertEqual(result['model_or_tool_dispatches'],0)
            self.assertEqual(len(list((Path(folder)/'out/raw').glob('*.json'))),6)

    def test_bad_header_identity_shape_and_timeout_stop_without_retry(self):
        for kind in ('v6_on_v1','trace','foreign','cached','http503','timeout'):
            calls=[]
            def handle(request):
                calls.append(request)
                if kind=='timeout':raise httpx.ReadTimeout('private-exception-sentinel',request=request)
                if kind=='http503':return httpx.Response(503,json={})
                data=dict(request_id='r',snapshot=snapshot())
                if kind=='v6_on_v1':data['version']='RUN-display.6'
                if kind=='foreign':data['snapshot']['run_id']='foreign'
                return httpx.Response(200,headers={'X-Request-ID':'other' if kind=='trace' else 'r',
                    'Cache-Control':'public' if kind=='cached' else 'no-store'},json=data)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as folder,httpx.Client(transport=httpx.MockTransport(handle)) as client:
                result=probe.collect(client,Path(folder)/'out',dict(kind='synthetic_unit'))
                self.assertEqual(len(calls),1);self.assertEqual(result['unrun_n'],5)
                self.assertEqual(result['availability'],'UNKNOWN' if kind=='timeout' else 'FAIL')
                self.assertNotIn('private-exception-sentinel',json.dumps(result))
                self.assertEqual(result['quality_release_decision'],'UNRUN')

    def test_bearer_ownership_mode_symlink_and_audience_preflight(self):
        def token(audience):
            def part(value):return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
            return part(dict(alg='RS256'))+'.'+part(dict(iss='https://local.g2c.invalid',aud=audience,
                sub='m4-synthetic-beta-a',exp=int(time.time())+600))+'.synthetic_signature'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bearer';path.write_text(token('g2c-local'));path.chmod(0o644)
            with self.assertRaises(ValueError):probe.bearer(path)
            path.chmod(0o600);self.assertEqual(probe.bearer(path),path.read_text())
            link=Path(folder)/'link';link.symlink_to(path)
            with self.assertRaises(OSError):probe.bearer(link)
            path.write_text(token('another-service'))
            with self.assertRaises(ValueError):probe.bearer(path)

    def test_final_B_reason_allowlist_preserves_old_and_masks_unknown(self):
        reasons=('native_json_invalid','native_json_duplicate','native_envelope_type','native_envelope_fields',
            'native_version_literal','native_answer_fields','native_answer_calls','native_answer_text',
            'native_kind_literal','native_tool_answer','native_calls_type','native_calls_bound','native_call_fields',
            'native_call_name','native_call_arguments','native_contract_bound','native_contract_invalid','parse_error')
        template='M4_MODEL_UNKNOWN attempt_sha256='+'a'*64+' phase=native_function_turn http_status=200 done=True finished=True usage=True content_chars=0 tool_count=1 reason={} choice_rejection=none finish_reason=stop argument_chars_before_rejection=246'
        for reason in reasons:
            self.assertEqual(parse_audit(template.format(reason))[0]['reason_code'],reason)
        self.assertEqual(parse_audit(template.format('native_unapproved_code'))[0]['reason_code'],'UNKNOWN')


if __name__=='__main__':unittest.main()
