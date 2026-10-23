"""Real private loopback TLS; all provider data/credentials are SYNTHETIC.

No real Gaode DNS/request. Production private dial is patched at the socket seam;
public endpoint policy and actual TLS hostname verification remain in force.
"""
import asyncio
from contextlib import redirect_stderr, redirect_stdout, suppress
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from cj_place import Config, Detail, Departure, Endpoint, Coordinate, ORIGIN, Outcome, RouteQuery, Search
from cj_place import execute, parse_response, prepare
from cj_place.https_transport import ProviderCredentials, fetch_candidate
from cj_place import https_transport as ht

SENTINEL = "synthetic_ONLY_012_KEY_7cb68e41"
CONFIG = Config(ORIGIN, 4096, 4096, 2, 60)
SEARCH = Search("合成地点", "合成城市", 1, 20)


class LoopbackTLSTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        local = Path(__file__).resolve().parents[1] / ".local"
        local.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="transport-tls-", dir=local)
        cls.root = Path(cls.temp.name)
        cls.cert = cls.root / "fixture-cert.pem"
        cls.key = cls.root / "fixture-key.pem"
        subprocess.run(["/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "1", "-subj", "/CN=restapi.amap.com",
                        "-addext", "subjectAltName=DNS:restapi.amap.com",
                        "-keyout", str(cls.key), "-out", str(cls.cert)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.key.chmod(0o600)
        cls.server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.server_context.load_cert_chain(cls.cert, cls.key)
        cls.client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cls.client_context.load_verify_locations(cafile=str(cls.cert))
        cls.client_context.minimum_version = ssl.TLSVersion.TLSv1_2

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()  # only this run's disposable synthetic TLS material

    async def asyncSetUp(self):
        self.mode = "normal"
        self.calls = []
        self.dials = 0
        self.handlers = set()
        self.expected_handshake_failures = False
        self.handshake_diagnostics = []
        loop = asyncio.get_running_loop()
        self.old_exception_handler = loop.get_exception_handler()
        def record_expected_handshake(context_loop, context):
            if (self.expected_handshake_failures and
                context.get("message") == "Error on transport creation for incoming connection" and
                isinstance(context.get("exception"), (ConnectionResetError, ssl.SSLError))):
                self.handshake_diagnostics.append(type(context["exception"]).__name__)
            else:
                context_loop.default_exception_handler(context)
        loop.set_exception_handler(record_expected_handshake)
        self.seen = asyncio.Event()
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0, ssl=self.server_context)
        self.port = self.server.sockets[0].getsockname()[1]
        self.dial_patch = patch.object(ht, "_connect", self.dial)
        self.dial_patch.start()

    async def asyncTearDown(self):
        self.dial_patch.stop()
        self.server.close()
        await self.server.wait_closed()
        tasks = list(self.handlers)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        asyncio.get_running_loop().set_exception_handler(self.old_exception_handler)

    async def dial(self):
        self.dials += 1
        return await asyncio.open_connection("127.0.0.1", self.port, ssl=self.client_context,
                                             server_hostname="restapi.amap.com", limit=16384)

    def request(self, query=SEARCH, config=CONFIG, at=None):
        return prepare(config, query, "synthetic-tls-request", at or datetime.now(timezone.utc))

    def credentials(self):
        return ProviderCredentials(SENTINEL, datetime.now(timezone.utc) + timedelta(seconds=60))

    async def call(self, query=SEARCH, config=CONFIG):
        request = self.request(query, config)
        receipt = await fetch_candidate(config, request, self.credentials())
        return request, receipt

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            self.calls.append(head)
            self.seen.set()
            target = head.split(b" ", 2)[1].decode("ascii")
            query = parse_qs(urlsplit(target).query)
            if target.startswith("/v3/direction/"):
                body = json.dumps({"status":"1", "info":"OK", "infocode":"10000", "count":"1",
                                   "route":{"origin":query["origin"][0], "destination":query["destination"][0],
                                            "paths":[{"distance":"123", "duration":"60"}]}}).encode()
            else:
                body = json.dumps({"status":"1", "info":"OK", "infocode":"10000", "count":"1",
                                   "pois":[{"id":query.get("id", ["SYNTH_A"])[0], "name":"合成地点",
                                            "address":"合成地址", "location":"116.1,39.1"}]}, ensure_ascii=False).encode()
            if self.mode == "wait":
                await asyncio.sleep(5)
            elif self.mode == "drip":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n")
                for _ in range(10):
                    writer.write(b"x")
                    await writer.drain()
                    await asyncio.sleep(0.06)
                return
            elif self.mode == "redirect":
                writer.write(("HTTP/1.1 302 Found\r\nLocation: https://evil.invalid/?key=" + SENTINEL +
                              "\r\nSet-Cookie: synthetic=private\r\nContent-Length: 0\r\n\r\n").encode())
                await writer.drain()
                return
            elif self.mode == "http429":
                writer.write(b"HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            elif self.mode in ("echo", "escaped_echo"):
                secret = SENTINEL if self.mode == "echo" else "".join("\\u%04x" % ord(c) for c in SENTINEL)
                body = ('{"echo":"' + secret + '"}').encode()
            elif self.mode == "malformed":
                body = b'{"status":"1","status":"0"}'
            elif self.mode == "huge_length":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 999999999\r\n\r\n")
                await writer.drain()
                return
            elif self.mode == "oversize_eof":
                writer.write(b"HTTP/1.1 200 OK\r\n\r\n" + b"x" * 4097)
                await writer.drain()
                return
            elif self.mode == "oversize_chunk":
                writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1001\r\n")
                await writer.drain()
                return
            elif self.mode == "ambiguous":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n")
                await writer.drain()
                return
            elif self.mode == "duplicate_length":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            elif self.mode == "gzip":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            elif self.mode == "huge_header":
                writer.write(b"HTTP/1.1 200 OK\r\nX-Large: " + b"x" * 17000 + b"\r\n\r\n")
                await writer.drain()
                return
            elif self.mode == "truncated":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nshort")
                await writer.drain()
                return
            if self.mode == "chunked":
                writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
                for part in (body[:7], body[7:21], body[21:]):
                    writer.write(("%x\r\n" % len(part)).encode() + part + b"\r\n")
                writer.write(b"0\r\n\r\n")
            elif self.mode == "eof":
                writer.write(b"HTTP/1.1 200 OK\r\n\r\n" + body)
            else:
                writer.write(("HTTP/1.1 200 OK\r\nContent-Length: %d\r\nSet-Cookie: private=ignored\r\n\r\n" % len(body)).encode() + body)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        finally:
            writer.close()
            with suppress(Exception, asyncio.CancelledError):
                await writer.wait_closed()
            self.handlers.discard(task)

    async def test_actual_tls_bytes_parse_for_all_four_fixed_endpoints(self):
        origin = Endpoint("SYNTH_A", Coordinate("116.1,39.1"), "entrance")
        dest = Endpoint("SYNTH_B", Coordinate("116.2,39.2"), "poi_center")
        queries = (SEARCH, Detail("SYNTH_A"),
                   RouteQuery(origin, dest, "walking", Departure("at_query_time", None)),
                   RouteQuery(origin, dest, "driving", Departure("at_query_time", None)))
        for query in queries:
            with self.subTest(kind=type(query).__name__):
                request, receipt = await self.call(query)
                self.assertEqual(receipt.state, "received")
                target = urlsplit(self.calls[-1].split(b" ", 2)[1].decode("ascii"))
                self.assertEqual(target.path, request.path)
                expected_query = {k: [v] for k, v in request.params}
                expected_query["key"] = [SENTINEL]
                self.assertTrue(parse_qs(target.query) == expected_query, "exact outbound query mismatch")
                result = parse_response(CONFIG, request, receipt.response, now=datetime.now(timezone.utc), evidence="synthetic")
                self.assertEqual(result.outcome, Outcome.OK)
                self.assertEqual(result.source.binding_digest, request.binding_digest)
                self.assertIs(result.source.query_started_at, request.started_at)
                self.assertEqual(result.source.evidence, "synthetic")
                self.assertNotIn(SENTINEL, repr(result))
        self.assertEqual(self.dials, 4)
        self.assertEqual(len(self.calls), 4)
        for raw in self.calls:
            self.assertTrue(b"Host: restapi.amap.com\r\n" in raw)
            self.assertFalse(b"Cookie:" in raw)
            self.assertTrue(b"Accept-Encoding: identity\r\n" in raw)
            self.assertEqual(parse_qs(urlsplit(raw.split(b" ", 2)[1].decode()).query)["key"], [SENTINEL])

    async def test_chunked_and_eof_body_framing(self):
        for mode in ("chunked", "eof"):
            self.mode = mode
            request, receipt = await self.call()
            self.assertEqual(receipt.state, "received")
            self.assertEqual(parse_response(CONFIG, request, receipt.response, now=datetime.now(timezone.utc)).outcome, Outcome.OK)

    async def test_tampering_key_in_descriptor_and_request_size_reject_before_dial(self):
        request = self.request()
        for altered in (replace(request, origin=ORIGIN + ".invalid"),
                        replace(request, path="/v3/other"),
                        replace(request, params=(*request.params, ("key", SENTINEL))),
                        replace(request, params=tuple((k, "changed" if k == "city" else v) for k,v in request.params))):
            result = await fetch_candidate(CONFIG, altered, self.credentials())
            self.assertEqual(result.state, "rejected")
        config = replace(CONFIG, max_request_bytes=len((ORIGIN + request.path + "?" + ht.urlencode(request.params)).encode()) + 1)
        prepared = self.request(config=config)
        result = await fetch_candidate(config, prepared, self.credentials())
        self.assertEqual(result.reason, "credentialed_request_bytes_limit")
        self.assertEqual(self.dials, 0)

    async def test_expired_missing_credentials_and_stale_future_time_do_not_dial(self):
        expired = ProviderCredentials(SENTINEL, datetime.now(timezone.utc) - timedelta(seconds=1))
        self.assertEqual((await fetch_candidate(CONFIG, self.request(), expired)).state, "rejected")
        self.assertEqual((await fetch_candidate(CONFIG, self.request(), None)).state, "rejected")
        for delta in (-61, 10):
            request = self.request(at=datetime.now(timezone.utc) + timedelta(seconds=delta))
            self.assertEqual((await fetch_candidate(CONFIG, request, self.credentials())).state, "rejected")
        self.assertEqual(self.dials, 0)

    async def test_redirect_and_http_failure_are_received_without_follow_or_secret(self):
        for mode, outcome in (("redirect", Outcome.PROVIDER_ERROR), ("http429", Outcome.RATE_LIMITED)):
            self.mode = mode
            request, receipt = await self.call()
            self.assertEqual(receipt.state, "received")
            self.assertEqual(receipt.response.body, b"")
            result = parse_response(CONFIG, request, receipt.response, now=datetime.now(timezone.utc))
            self.assertEqual(result.outcome, outcome)
            self.assertNotIn(SENTINEL, repr(receipt))
            self.assertNotIn(SENTINEL, repr(result))
        self.assertEqual(self.dials, 2)
        self.assertEqual(len(self.calls), 2)

    async def test_literal_and_json_escaped_secret_echo_are_not_returned_or_logged(self):
        for mode in ("echo", "escaped_echo"):
            self.mode = mode
            log = io.StringIO()
            with redirect_stdout(log), redirect_stderr(log):
                request, receipt = await self.call()
            self.assertEqual(receipt.reason, "credential_echo_rejected")
            self.assertIsNone(receipt.response)
            self.assertEqual(log.getvalue(), "")
            self.assertNotIn(SENTINEL, repr(request))
            self.assertNotIn(SENTINEL, repr(self.credentials()))

    async def test_response_caps_framing_and_encoding_fail_unknown(self):
        for mode in ("huge_length", "oversize_eof", "oversize_chunk", "huge_header", "ambiguous", "duplicate_length", "gzip", "truncated"):
            self.mode = mode
            _, receipt = await self.call()
            self.assertEqual(receipt.state, "unknown", mode)
            self.assertIsNone(receipt.response)
        self.assertEqual(self.dials, 8)

    async def test_malformed_actual_body_fails_closed_before_response_boundary(self):
        self.mode = "malformed"
        _, receipt = await self.call()
        self.assertEqual(receipt.state, "unknown")
        self.assertEqual(receipt.reason, "response_secret_check_unavailable")
        self.assertIsNone(receipt.response)

    async def test_total_deadline_stops_slow_drip_and_no_retry(self):
        self.mode = "drip"
        config = replace(CONFIG, timeout_seconds=0.15)
        before = asyncio.get_running_loop().time()
        _, receipt = await self.call(config=config)
        self.assertEqual(receipt.state, "unknown")
        self.assertIsNone(receipt.response)
        self.assertLess(asyncio.get_running_loop().time() - before, 0.5)
        self.assertEqual(self.dials, 1)
        self.assertEqual(len(self.calls), 1)

    async def test_cancellation_after_send_closes_and_propagates_no_retry(self):
        self.mode = "wait"
        request = self.request()
        task = asyncio.create_task(fetch_candidate(CONFIG, request, self.credentials()))
        await asyncio.wait_for(self.seen.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.dials, 1)
        self.assertEqual(len(self.calls), 1)

    async def test_tls_hostname_and_untrusted_cert_fail_without_http_request(self):
        self.expected_handshake_failures = True
        async def wrong_host():
            self.dials += 1
            return await asyncio.open_connection("127.0.0.1", self.port, ssl=self.client_context,
                                                 server_hostname="wrong.invalid")
        untrusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        async def no_trust():
            self.dials += 1
            return await asyncio.open_connection("127.0.0.1", self.port, ssl=untrusted,
                                                 server_hostname="restapi.amap.com")
        for connector in (wrong_host, no_trust):
            with patch.object(ht, "_connect", connector):
                _, receipt = await self.call()
            self.assertEqual(receipt.state, "unknown")
            self.assertIsNone(receipt.response)
        self.assertEqual(len(self.calls), 0)

    async def test_transport_exception_and_close_error_never_expose_prose(self):
        async def raises():
            raise OSError("synthetic-secret-exception:" + SENTINEL)
        with patch.object(ht, "_connect", raises):
            _, receipt = await self.call()
        self.assertEqual(receipt.reason, "transport_unknown")
        self.assertNotIn(SENTINEL, repr(receipt))
        async def bad_close():
            reader, writer = await self.dial()
            async def fail():
                raise OSError("synthetic-close-secret:" + SENTINEL)
            writer.wait_closed = fail
            return reader, writer
        with patch.object(ht, "_connect", bad_close):
            _, receipt = await self.call()
        self.assertEqual(receipt.reason, "close_unknown")
        self.assertIsNone(receipt.response)
        self.assertNotIn(SENTINEL, repr(receipt))

    async def test_expiry_during_call_drops_late_response(self):
        self.mode = "drip"
        request = self.request()
        credentials = ProviderCredentials(SENTINEL, datetime.now(timezone.utc) + timedelta(seconds=0.1))
        before = asyncio.get_running_loop().time()
        receipt = await fetch_candidate(CONFIG, request, credentials)
        self.assertEqual(receipt.state, "unknown")
        self.assertIsNone(receipt.response)
        self.assertEqual(self.dials, 1)
        self.assertLess(asyncio.get_running_loop().time() - before, 0.4)

    async def test_synchronous_close_failure_is_sanitized_and_aborted(self):
        writers = []
        async def bad_close():
            reader, writer = await self.dial()
            writers.append(writer)
            def fail():
                raise OSError("synthetic-close-secret:" + SENTINEL)
            writer.close = fail
            return reader, writer
        with patch.object(ht, "_connect", bad_close):
            _, receipt = await self.call()
        self.assertEqual(receipt.state, "unknown")
        self.assertEqual(receipt.reason, "close_unknown")
        self.assertIsNone(receipt.response)
        self.assertTrue(writers[0].transport.is_closing())
        self.assertNotIn(SENTINEL, repr(receipt))

    async def test_delayed_close_that_swallows_timeout_cannot_return_success(self):
        config = replace(CONFIG, timeout_seconds=0.08)
        async def late_close():
            reader, writer = await self.dial()
            async def slow():
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    await asyncio.sleep(0.01)
            writer.wait_closed = slow
            return reader, writer
        with patch.object(ht, "_connect", late_close):
            _, receipt = await self.call(config=config)
        self.assertEqual(receipt.state, "unknown")
        self.assertIsNone(receipt.response)
        self.assertEqual(self.dials, 1)

    async def test_cancel_during_close_propagates_after_abort(self):
        closing = asyncio.Event()
        writers = []
        async def blocked_close():
            reader, writer = await self.dial()
            writers.append(writer)
            async def slow():
                closing.set()
                await asyncio.sleep(5)
            writer.wait_closed = slow
            return reader, writer
        with patch.object(ht, "_connect", blocked_close):
            task = asyncio.create_task(fetch_candidate(CONFIG, self.request(), self.credentials()))
            await asyncio.wait_for(closing.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(writers[0].transport.is_closing())
        self.assertEqual(self.dials, 1)

    async def test_late_connect_return_after_timeout_cannot_send_request(self):
        config = replace(CONFIG, timeout_seconds=0.08)
        async def late_connect():
            reader, writer = await self.dial()
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                await asyncio.sleep(0.01)
            return reader, writer
        with patch.object(ht, "_connect", late_connect):
            _, receipt = await self.call(config=config)
        self.assertEqual(receipt.state, "unknown")
        self.assertIsNone(receipt.response)
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(self.dials, 1)

    async def test_proxy_cookie_and_keylog_environment_not_used(self):
        keylog = self.root / "must-not-exist-keylog"
        with patch.dict(os.environ, {"HTTPS_PROXY":"http://127.0.0.1:9", "https_proxy":"http://127.0.0.1:9",
                                     "SSLKEYLOGFILE":str(keylog), "CJ_GAODE_API_KEY":"not-the-injected-key"}):
            request, receipt = await self.call()
            self.assertEqual(receipt.state, "received")
            self.assertIsNone(ht._tls_context().keylog_filename)
        self.assertFalse(keylog.exists())
        self.assertEqual(self.dials, 1)
        self.assertFalse(b"Cookie:" in self.calls[0])
        self.assertNotIn(SENTINEL, repr(execute(SEARCH, config=CONFIG)))
        self.assertEqual(execute(SEARCH, config=CONFIG).outcome, Outcome.UNAVAILABLE)


class ProductionDialPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_host_port_tls_verification_no_public_override(self):
        dial = AsyncMock(return_value=("synthetic-reader", "synthetic-writer"))
        with patch.object(asyncio, "open_connection", dial):
            await ht._connect()
        args, kwargs = dial.call_args
        self.assertEqual(args, ("restapi.amap.com", 443))
        self.assertEqual(kwargs["server_hostname"], "restapi.amap.com")
        self.assertTrue(kwargs["ssl"].check_hostname)
        self.assertEqual(kwargs["ssl"].verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(kwargs["ssl"].minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertIsNone(kwargs["ssl"].keylog_filename)


if __name__ == "__main__":
    unittest.main(verbosity=2)
