import asyncio
from contextlib import suppress
import unittest
from https_transport_checks import LoopbackTLSTests, SENTINEL

class SecretEchoChecks(LoopbackTLSTests):
    async def handle(self, reader, writer):
        task=asyncio.current_task(); self.handlers.add(task)
        try:
            head=await reader.readuntil(b'\r\n\r\n'); self.calls.append(head); self.seen.set()
            body=self.payload
            writer.write(('HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n'%len(body)).encode()+body)
            await writer.drain()
        except (ConnectionError,asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with suppress(Exception,asyncio.CancelledError):await writer.wait_closed()
            self.handlers.discard(task)

    async def test_duplicate_key_escaped_credential_must_not_enter_response(self):
        escaped=''.join('\\u%04x'%ord(c) for c in SENTINEL)
        self.payload=('{"duplicate":1,"duplicate":2,"echo":"'+escaped+'"}').encode()
        _,result=await self.call()
        self.assertEqual(self.dials,1)
        self.assertIsNone(result.response,'recoverable credential echo must not escape in Response.body')

    async def test_truncated_json_escaped_credential_must_not_enter_response(self):
        escaped=''.join('\\u%04x'%ord(c) for c in SENTINEL)
        self.payload=('{"echo":"'+escaped+'"').encode()
        _,result=await self.call()
        self.assertEqual(self.dials,1)
        self.assertIsNone(result.response,'recoverable credential echo must not escape in malformed Response.body')

if __name__=='__main__':
    suite=unittest.TestSuite(SecretEchoChecks(name) for name in (
      'test_duplicate_key_escaped_credential_must_not_enter_response',
      'test_truncated_json_escaped_credential_must_not_enter_response'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
