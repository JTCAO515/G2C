"""Real task-private loopback TLS only. No provider, public DNS, system trust edit."""
import asyncio
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from cj_fact import FactFailure, PinnedTarget, RestrictedAcquisition
from cj_fact.https_transport import PinnedHTTPSTransport
from test_fact import POLICY, URL


class HTTPSLoopbackTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        local = Path(__file__).resolve().parents[1] / '.local'
        local.mkdir(exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(prefix='https-', dir=local)
        root = Path(cls.directory.name)
        cls.certificate, key = root / 'certificate.pem', root / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cls.certificate), '-days', '1',
                        '-subj', '/CN=weather.example.test',
                        '-addext', 'subjectAltName=DNS:weather.example.test'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.server_context.load_cert_chain(cls.certificate, key)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()  # only the fixture-created certificate/key/tempdir

    async def asyncSetUp(self):
        self.requests, self.sni, self.peers, self.errors = [], [], [], []
        self.allow_tls_rejection = False
        self.loop = asyncio.get_running_loop()
        self.previous_exception_handler = self.loop.get_exception_handler()
        self.loop.set_exception_handler(lambda _, context: self.errors.append(context))
        self.server_context.set_servername_callback(lambda _, name, __: self.sni.append(name))
        self.response_bytes = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 9\r\n\r\nSYNTHETIC'
        self.handler = None
        self.accepted = asyncio.Event()
        self.disconnected = asyncio.Event()
        self.tasks, self.writers = set(), set()
        self.server = await asyncio.start_server(self.serve, '127.0.0.1', 0, ssl=self.server_context)
        self.port = self.server.sockets[0].getsockname()[1]
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=self.certificate)
        self.transport = PinnedHTTPSTransport(POLICY, tls_context=context,
                                            max_header_bytes=1024, max_wire_bytes=8192, max_reads=32)

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        for writer in tuple(self.writers):
            writer.transport.abort()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        self.server_context.set_servername_callback(None)
        self.loop.set_exception_handler(self.previous_exception_handler)
        unexpected = [context for context in self.errors if not (
            self.allow_tls_rejection and isinstance(context.get('exception'), (ConnectionResetError, ssl.SSLError))
            and context.get('message') == 'Error on transport creation for incoming connection')]
        self.assertEqual(unexpected, [], 'unexpected asyncio fixture errors')

    async def serve(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.writers.add(writer)
        try:
            self.peers.append(writer.get_extra_info('peername')[0])
            self.accepted.set()
            request = await reader.readuntil(b'\r\n\r\n')
            self.requests.append(request)
            if self.handler is not None:
                await self.handler(reader, writer)
            else:
                writer.write(self.response_bytes)
                await writer.drain()
            await reader.read()
            self.disconnected.set()
        except (OSError, asyncio.IncompleteReadError):
            self.disconnected.set()
        finally:
            writer.transport.abort()
            self.writers.discard(writer)
            self.tasks.discard(task)

    def target(self, seconds=1.0, **changes):
        target = PinnedTarget(URL, 'weather.example.test', ('127.0.0.1',),
                              POLICY.max_bytes, asyncio.get_running_loop().time() + seconds)
        return replace(target, **changes)

    async def exchange(self, **changes):
        return await self.transport._exchange(self.target(**changes), '127.0.0.1', self.port)

    async def consume(self, response):
        try:
            return b''.join([chunk async for chunk in response.body])
        finally:
            await response.close()

    async def test_actual_tls_sni_peer_host_and_no_dns_or_ambient_credentials(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, 'getaddrinfo', side_effect=AssertionError('no DNS allowed')), \
                patch.dict('os.environ', {'HTTPS_PROXY': 'http://127.0.0.1:1',
                                         'ALL_PROXY': 'http://127.0.0.1:1',
                                         'HTTP_PROXY': 'http://127.0.0.1:1'}):
            response = await self.exchange()
            self.assertEqual(await self.consume(response), b'SYNTHETIC')
        self.assertEqual(response.url, URL)
        self.assertEqual(response.peer_ip, '127.0.0.1')
        self.assertEqual(self.sni, ['weather.example.test'])
        self.assertEqual(self.peers, ['127.0.0.1'])
        self.assertEqual(self.requests, [b'GET /forecast HTTP/1.1\r\nHost: weather.example.test\r\n'
                                      b'Accept: application/json, text/plain\r\nAccept-Encoding: identity\r\n'
                                      b'Connection: close\r\n\r\n'])
        await asyncio.wait_for(self.disconnected.wait(), 1)

    async def test_public_policy_rejects_fixture_private_address_before_socket(self):
        with patch.object(self.transport, '_exchange', side_effect=AssertionError('no socket')):
            with self.assertRaisesRegex(FactFailure, 'non_public_dns_answer'):
                await self.transport(self.target())
        self.assertEqual(self.requests, [])

    async def test_public_target_policy_and_configuration_guards(self):
        for changes in (dict(hostname='rules.example.test'), dict(max_bytes=True),
                        dict(url='https://unlisted.test/'), dict(deadline=float('nan')),
                        dict(addresses=('8.8.8.8', '127.0.0.1'))):
            with self.subTest(changes=changes), \
                    patch.object(self.transport, '_exchange', side_effect=AssertionError('no socket')):
                with self.assertRaises(FactFailure):
                    await self.transport(self.target(**changes))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        with self.assertRaisesRegex(FactFailure, 'tls_verification_required'):
            PinnedHTTPSTransport(POLICY, tls_context=context, max_header_bytes=1024,
                                max_wire_bytes=8192, max_reads=32)
        with self.assertRaisesRegex(FactFailure, 'production_integration_unavailable'):
            await RestrictedAcquisition(POLICY).fetch(URL)

    async def test_untrusted_certificate_rejected_before_http(self):
        self.allow_tls_rejection = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # no fixture CA trust
        self.transport.context = context
        with self.assertRaisesRegex(FactFailure, 'tls_certificate_invalid'):
            await self.exchange()
        self.assertEqual(self.requests, [])

    async def test_wrong_hostname_certificate_rejected_before_http(self):
        self.allow_tls_rejection = True
        with self.assertRaisesRegex(FactFailure, 'tls_certificate_invalid'):
            await self.exchange(hostname='rules.example.test', url='https://rules.example.test/page')
        self.assertEqual(self.sni, ['rules.example.test'])
        self.assertEqual(self.requests, [])

    async def test_redirect_returns_without_second_request_and_closes_unstarted_body(self):
        self.response_bytes = b'HTTP/1.1 302 Found\r\nLocation: https://127.0.0.1/secret\r\nContent-Length: 1000\r\n\r\n'
        response = await self.exchange()
        self.assertEqual(response.status, 302)
        self.assertEqual(response.location, 'https://127.0.0.1/secret')
        await response.close()  # no body iteration at all
        await asyncio.wait_for(self.disconnected.wait(), 1)
        self.assertEqual(len(self.requests), 1)

    async def test_chunked_and_close_delimited_frames(self):
        self.response_bytes = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\n\r\n3\r\none\r\n3\r\ntwo\r\n0\r\n\r\n'
        self.assertEqual(await self.consume(await self.exchange()), b'onetwo')
        async def close_body(_, writer):
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nraw')
            await writer.drain()
            writer.close()
        self.handler = close_body
        self.assertEqual(await self.consume(await self.exchange()), b'raw')

    async def test_compressed_oversize_ambiguous_and_malformed_headers(self):
        records = [
            b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Encoding: gzip\r\nContent-Length: 1\r\n\r\nx',
            b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 4097\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nLocation: /a\r\nLocation: /b\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nX-Huge: ' + b'x' * 2048 + b'\r\n\r\n',
            b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n',
            b'not HTTP\r\n\r\n',
        ]
        for raw in records:
            with self.subTest(index=records.index(raw)), self.assertRaises(FactFailure):
                self.response_bytes = raw
                await self.exchange()

    async def test_streaming_body_limit_and_chunk_limit_close(self):
        self.response_bytes = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\n\r\n1001\r\n' + b'x' * 4097 + b'\r\n0\r\n\r\n'
        with self.assertRaisesRegex(FactFailure, 'body_limit'):
            await self.consume(await self.exchange())
        self.transport.policy = replace(POLICY, max_chunks=1)
        self.response_bytes = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\n\r\n1\r\na\r\n1\r\nb\r\n0\r\n\r\n'
        with self.assertRaisesRegex(FactFailure, 'chunk_limit'):
            await self.consume(await self.exchange())

    async def test_truncated_body_and_trailers_are_rejected(self):
        for raw in (b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 10\r\n\r\nx',
                    b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx\r\n0\r\nX-Trailer: nope\r\n\r\n'):
            async def respond(_, writer):
                writer.write(raw)
                await writer.drain()
                writer.close()
            self.handler = respond
            with self.subTest(raw=raw[:20]), self.assertRaises(FactFailure):
                await self.consume(await self.exchange())

    async def test_header_timeout_and_no_retry(self):
        eof = asyncio.Event()
        async def stall(reader, _):
            await reader.read()
            eof.set()
        self.handler = stall
        with self.assertRaisesRegex(FactFailure, 'timeout'):
            await self.exchange(seconds=0.05)
        await asyncio.wait_for(eof.wait(), 1)
        self.assertEqual(len(self.requests), 1)

    async def test_body_timeout_cancel_and_abandoned_response_close(self):
        eof = asyncio.Event()
        async def header_only(reader, writer):
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 10\r\n\r\n')
            await writer.drain()
            await reader.read()
            eof.set()
        self.handler = header_only
        with self.assertRaisesRegex(FactFailure, 'timeout'):
            await self.consume(await self.exchange(seconds=0.05))
        await asyncio.wait_for(eof.wait(), 1)
        eof.clear()
        response = await self.exchange()
        task = asyncio.create_task(anext(response.body))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(eof.wait(), 1)
        eof.clear()
        response = await self.exchange(seconds=0.05)
        await asyncio.wait_for(eof.wait(), 1)  # deadline timer closes an unread response
        with self.assertRaisesRegex(FactFailure, 'timeout'):
            await anext(response.body)

    async def test_wire_limits_and_read_limit(self):
        self.transport.max_wire_bytes = 20
        with self.assertRaisesRegex(FactFailure, 'wire_byte_limit'):
            await self.exchange()
        self.transport.max_wire_bytes = 8192
        self.transport.max_reads = 1
        async def split(reader, writer):
            writer.write(b'HTTP/1.1 200 OK\r\n')
            await writer.drain()
            await reader.read()
        self.handler = split
        with self.assertRaisesRegex(FactFailure, 'wire_read_limit'):
            await self.exchange()

    async def test_checked_peer_mismatch_blocks_http(self):
        real_open = asyncio.open_connection
        class WrongPeerWriter:
            def __init__(self, writer):
                self.writer = writer
            def get_extra_info(self, name):
                return ('1.1.1.1', 443) if name == 'peername' else self.writer.get_extra_info(name)
            @property
            def transport(self):
                return self.writer.transport
        async def wrong_peer(**kwargs):
            reader, writer = await real_open(**kwargs)
            return reader, WrongPeerWriter(writer)
        with patch('cj_fact.https_transport.asyncio.open_connection', side_effect=wrong_peer):
            with self.assertRaisesRegex(FactFailure, 'peer_not_pinned'):
                await self.exchange()
        await asyncio.wait_for(self.disconnected.wait(), 1)
        self.assertEqual(self.requests, [])

    async def test_public_callable_uses_first_validated_address_once(self):
        from unittest.mock import AsyncMock
        target = self.target(addresses=('8.8.8.8', '1.1.1.1'))
        failing = AsyncMock(side_effect=FactFailure('https_exchange_failed'))
        with patch.object(self.transport, '_exchange', failing):
            with self.assertRaisesRegex(FactFailure, 'https_exchange_failed'):
                await self.transport(target)
        failing.assert_awaited_once_with(target, '8.8.8.8', 443)
        self.assertEqual(self.requests, [])

    async def test_handshake_timeout_and_native_cancel_close_numeric_socket(self):
        accepted = asyncio.Event()
        eof = asyncio.Event()
        raw_tasks = set()
        async def no_tls(reader, writer):
            task = asyncio.current_task()
            raw_tasks.add(task)
            try:
                await reader.read(1)  # observe a real TLS ClientHello
                accepted.set()
                await reader.read()
                eof.set()
            finally:
                writer.transport.abort()
                raw_tasks.discard(task)
        server = await asyncio.start_server(no_tls, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with self.assertRaisesRegex(FactFailure, 'timeout'):
                await self.transport._exchange(self.target(seconds=0.05), '127.0.0.1', port)
            await asyncio.wait_for(eof.wait(), 1)
            eof.clear()
            accepted.clear()
            task = asyncio.create_task(self.transport._exchange(self.target(), '127.0.0.1', port))
            await asyncio.wait_for(accepted.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(eof.wait(), 1)
        finally:
            server.close()
            await server.wait_closed()
            for task in tuple(raw_tasks):
                task.cancel()
            await asyncio.gather(*tuple(raw_tasks), return_exceptions=True)

    async def test_acquisition_event_cancellation_closes_actual_fixture_socket(self):
        from test_fact import NOW
        started, eof, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def stall(reader, _):
            started.set()
            await reader.read()
            eof.set()
        self.handler = stall
        async def resolve(_):
            return ('8.8.8.8',)  # synthetic DNS metadata; never contacted
        async def fixture_transport(target):
            return await self.transport._exchange(target, '127.0.0.1', self.port)
        task = asyncio.create_task(RestrictedAcquisition(POLICY).fetch_synthetic(
            URL, resolve=resolve, transport=fixture_transport, retrieved_at=NOW, cancelled=cancelled))
        await asyncio.wait_for(started.wait(), 1)
        cancelled.set()
        with self.assertRaisesRegex(FactFailure, '^cancelled$'):
            await task
        await asyncio.wait_for(eof.wait(), 1)
        self.assertEqual(len(self.requests), 1)

    async def test_actual_connect_failure_is_safe_and_attempted_once(self):
        guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        guard.bind(('127.0.0.1', 0))  # bound but not listening: no unrelated service race
        port = guard.getsockname()[1]
        loop = asyncio.get_running_loop()
        real_connect = loop.sock_connect
        try:
            with patch.object(loop, 'sock_connect', wraps=real_connect) as connect:
                with self.assertRaises(FactFailure) as failure:
                    await self.transport._exchange(self.target(seconds=0.05), '127.0.0.1', port)
                # macOS may drop rather than refuse a bound, non-listening port.
                self.assertIn(str(failure.exception), ('https_exchange_failed', 'timeout'))
                connect.assert_awaited_once()
        finally:
            guard.close()
        self.assertEqual(self.requests, [])

    async def test_expired_deadline_does_not_open_socket(self):
        with patch('cj_fact.https_transport.socket.socket', side_effect=AssertionError('no socket')):
            with self.assertRaisesRegex(FactFailure, 'timeout'):
                await self.exchange(seconds=-1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
