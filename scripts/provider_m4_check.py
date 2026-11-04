"""Offline regression for the bounded acceptance adapter; no real key/network."""
import asyncio
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

import httpx
import provider_m4 as subject


def sse():
    return ('data: '+json.dumps(dict(id='synthetic-id',object='chat.completion.chunk',created=1,model=subject.MODEL,
        choices=[dict(index=0,delta={'role':'assistant','content':'Synthetic answer'},finish_reason=None)]))+
        '\n\ndata: '+json.dumps(dict(id='synthetic-id',object='chat.completion.chunk',created=1,model=subject.MODEL,
        choices=[dict(index=0,delta={},finish_reason='stop')],usage=dict(prompt_tokens=3,completion_tokens=2,total_tokens=5)))+
        '\n\ndata: [DONE]\n\n').encode()


class Checks(unittest.TestCase):
    def test_secret_in_error_metadata_never_leaves_process(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=subject.Journal(Path(directory));key='synthetic-secret-key'
            payload=sse().replace(subject.MODEL.encode(),key.encode())
            async def run():
                with patch.object(subject.httpx,'AsyncHTTPTransport',lambda **kwargs:httpx.MockTransport(lambda request:httpx.Response(200,content=payload))):
                    return await subject.run(journal,'beijing','en-answer',key)
            result=asyncio.run(run())
            self.assertEqual(result['status'],'FAIL')
            self.assertNotIn(key,json.dumps(result))
            self.assertNotIn(key,json.dumps(journal.inspect()))

    def test_http_rejection_is_not_timeout_or_cancellation_success(self):
        for case in ('timeout','cancel'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory:
                async def run():
                    with patch.object(subject.httpx,'AsyncHTTPTransport',lambda **kwargs:httpx.MockTransport(lambda request:httpx.Response(401,json={'error':{'message':'synthetic rejection','type':'invalid_api_key'}}))):
                        return await subject.run(subject.Journal(Path(directory)),'beijing',case,'synthetic-only-key')
                self.assertEqual(asyncio.run(run())['status'],'FAIL')

    def test_completed_response_does_not_pass_timeout_case(self):
        with tempfile.TemporaryDirectory() as directory:
            async def run():
                with patch.object(subject.httpx,'AsyncHTTPTransport',lambda **kwargs:httpx.MockTransport(lambda request:httpx.Response(200,content=sse()))):
                    return await subject.run(subject.Journal(Path(directory)),'beijing','timeout','synthetic-only-key')
            self.assertEqual(asyncio.run(run())['status'],'FAIL')

    def test_real_cli_rejects_ledger_path_override_before_loading_key(self):
        import sys
        for directory in ('ledger-a','ledger-b'):
            with self.subTest(directory=directory),patch.object(sys,'argv',['provider_m4.py','--root',directory,'--region','beijing','--case','zh-answer']),patch.object(subject.subprocess,'run',side_effect=AssertionError('must not load credential')):
                with self.assertRaises(SystemExit) as error:subject.main()
                self.assertEqual(error.exception.code,2)

    def test_sdk_typed_chunk_stream_usage_and_original_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=subject.Journal(Path(directory));seen=[]
            def handler(request):
                seen.append(json.loads(request.content))
                return httpx.Response(200,content=sse())
            async def run():
                with patch.object(subject.httpx,'AsyncHTTPTransport',lambda **kwargs:httpx.MockTransport(handler)):
                    result=await subject.run(journal,'beijing','en-answer','synthetic-only-key')
                    self.assertEqual(result['status'],'PASS')
                    self.assertEqual(result['receipt']['usage'],dict(input_tokens=3,output_tokens=2))
                    self.assertEqual(result['receipt']['provider_reported_model_ids'],[subject.MODEL])
                    repeated=await subject.run(subject.Journal(Path(directory)),'beijing','en-answer','synthetic-only-key')
                    self.assertEqual(repeated['status'],'FAIL')
                    self.assertEqual(repeated['receipt']['outcome'],'NOT_SENT')
            asyncio.run(run())
            self.assertEqual(len(seen),1)
            self.assertEqual(seen[0]['max_tokens'],256)
            self.assertNotIn('max_completion_tokens',seen[0])
            self.assertEqual(journal.inspect()[0]['state'],'COMPLETE')

    def test_intent_after_process_restart_cannot_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);subject.Journal(root).reserve('beijing:unknown:0',b'original')
            with self.assertRaisesRegex(ValueError,'original_attempt_read_only'):
                subject.Journal(root).reserve('beijing:unknown:0',b'original')
            self.assertEqual(subject.Journal(root).inspect()[0]['state'],'INTENT')

    def test_unknown_outflow_never_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=subject.Journal(Path(directory));seen=[]
            def timeout(request):
                seen.append(1)
                raise httpx.ReadTimeout('synthetic')
            async def run():
                with patch.object(subject.httpx,'AsyncHTTPTransport',lambda **kwargs:httpx.MockTransport(timeout)):
                    return await subject.run(journal,'beijing','timeout','synthetic-only-key')
            result=asyncio.run(run())
            self.assertEqual(result['status'],'PASS');self.assertEqual(seen,[1])
            self.assertEqual(journal.inspect()[0]['state'],'UNKNOWN')

    def test_sdk_cancellation_closes_without_following_call(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=subject.Journal(Path(directory));seen=[]
            def handler(request):seen.append(1);return httpx.Response(200,content=sse())
            async def run():
                with patch.object(subject.httpx,'AsyncHTTPTransport',lambda **kwargs:httpx.MockTransport(handler)):
                    return await subject.run(journal,'beijing','cancel','synthetic-only-key')
            result=asyncio.run(run())
            self.assertEqual(result['status'],'PASS');self.assertEqual(seen,[1])
            self.assertEqual(result['receipt']['reason'],'CLIENT_CANCELLED')


if __name__=='__main__':
    unittest.main()
