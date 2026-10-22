import asyncio
import ssl
import threading
import unittest
from dataclasses import replace
import httpx
from cj_auth.https_jwks_transport import HTTPSConfiguration, HTTPSJWKSTransport, HTTPTransportFailure
from cj_auth.jwks_provider import JWKSRequest


class Stream(httpx.AsyncByteStream):
    def __init__(self,chunks,stall=False): self.parts,self.stall,self.closed=chunks,stall,False
    async def __aiter__(self):
        for part in self.parts: yield part
        if self.stall: await asyncio.sleep(10)
    async def aclose(self): self.closed=True


class HTTPSTests(unittest.TestCase):
    def setUp(self):
        self.url='https://keys.synthetic.invalid/jwks'
        self.config=HTTPSConfiguration(self.url,.2,.2,.2,.2,.01,128,4)
    def request(self,timeout=1): return JWKSRequest(self.url,timeout,128,threading.Event())
    def adapter(self,handler):
        return HTTPSJWKSTransport(self.config,http_transport_factory=lambda:httpx.MockTransport(handler))

    def test_default_disabled_and_target_mismatch_never_call_transport(self):
        with self.assertRaisesRegex(HTTPTransportFailure,'disabled'): HTTPSJWKSTransport().fetch(self.request())
        calls=[]; adapter=self.adapter(lambda r:calls.append(r))
        with self.assertRaisesRegex(HTTPTransportFailure,'target_mismatch'):
            adapter.fetch(JWKSRequest('https://other.invalid',1,128,threading.Event()))
        request=self.request(); request.cancelled.set()
        with self.assertRaisesRegex(HTTPTransportFailure,'cancelled'): adapter.fetch(request)
        self.assertEqual(calls,[])

    def test_request_has_no_secret_headers_and_timeouts_are_httpx_options(self):
        stream=Stream([b'{"keys":[]}']); seen=[]
        def handle(r): seen.append(r); return httpx.Response(200,headers={'content-type':'application/json'},stream=stream)
        response=self.adapter(handle).fetch(self.request())
        self.assertEqual(b''.join(response.chunks),b'{"keys":[]}')
        self.assertTrue(stream.closed)
        self.assertEqual(seen[0].method,'GET')
        self.assertNotIn('authorization',seen[0].headers); self.assertNotIn('cookie',seen[0].headers)
        self.assertEqual(seen[0].headers['accept-encoding'],'identity')
        self.assertEqual(seen[0].extensions['timeout'],{'connect':.2,'read':.2,'write':.2,'pool':.2})
        response.close(); self.assertTrue(response.closed); self.assertEqual(response.chunks,())

    def test_redirects_never_follow_even_to_same_origin(self):
        for status in (301,302,303,307,308):
            calls=[]; stream=Stream([b'not read'])
            def handle(r): calls.append(r); return httpx.Response(status,headers={'location':self.url+'/other'},stream=stream)
            response=self.adapter(handle).fetch(self.request())
            self.assertEqual(response.status,status); self.assertEqual(len(calls),1); self.assertEqual(response.chunks,())
            self.assertTrue(stream.closed)

    def test_limits_encoding_and_close_on_failure(self):
        for parts,encoding in (([b'x'*129],None),([b'x']*5,None),([b'compressed'],'gzip')):
            stream=Stream(parts)
            headers={} if encoding is None else {'content-encoding':encoding}
            adapter=self.adapter(lambda r:httpx.Response(200,headers=headers,stream=stream))
            with self.assertRaises(HTTPTransportFailure): adapter.fetch(self.request())
            self.assertTrue(stream.closed)

    def test_total_timeout_is_inside_adapter_and_closes_stream(self):
        stream=Stream([b'{'],stall=True)
        adapter=self.adapter(lambda r:httpx.Response(200,stream=stream))
        with self.assertRaisesRegex(HTTPTransportFailure,'total_timeout'): adapter.fetch(self.request(.05))
        self.assertTrue(stream.closed)

    def test_cancel_inflight_closes_response(self):
        request=self.request(); stream=Stream([b'{'],stall=True)
        adapter=self.adapter(lambda r:httpx.Response(200,stream=stream))
        timer=threading.Timer(.05,request.cancelled.set); timer.start()
        try:
            with self.assertRaisesRegex(HTTPTransportFailure,'cancelled'): adapter.fetch(request)
        finally: timer.cancel(); timer.join()
        self.assertTrue(stream.closed)

    def test_configuration_and_tls_cannot_disable_verification(self):
        with self.assertRaises(ValueError): replace(self.config,url='http://keys.invalid')
        with self.assertRaises(ValueError): replace(self.config,url='https://keys.synthetic.invalid/a/../jwks')
        with self.assertRaises(ValueError): replace(self.config,read_timeout_seconds=None)
        unsafe=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); unsafe.check_hostname=False; unsafe.verify_mode=ssl.CERT_NONE
        with self.assertRaises(ValueError): HTTPSJWKSTransport(self.config,tls_context=unsafe)

    def test_sync_entry_rejects_running_event_loop_without_io(self):
        calls=[]; adapter=self.adapter(lambda r:calls.append(r))
        async def run():
            with self.assertRaisesRegex(HTTPTransportFailure,'sync_entry_requires_worker'): adapter.fetch(self.request())
        asyncio.run(run()); self.assertEqual(calls,[])


if __name__=='__main__': unittest.main()
