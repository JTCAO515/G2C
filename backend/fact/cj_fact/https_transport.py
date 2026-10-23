"""One-shot pinned HTTPS primitive. Not registered with the production dispatcher.

No resolver, proxy, cookie jar, auth headers, redirect loop, retries or pool. The
public callable validates the existing policy/target; private _exchange is also
used directly by the task's loopback TLS fixture, without weakening that policy.
"""
import asyncio
import ipaddress
import math
import socket
import ssl
from urllib.parse import urlsplit

import h11

from .acquisition import InjectedResponse, PinnedTarget, _mime
from .policy import FactFailure, SourcePolicy, public_addresses


def _positive(value):
    return type(value) is int and value > 0


class PinnedHTTPSTransport:
    def __init__(self, policy: SourcePolicy, *, tls_context: ssl.SSLContext,
                 max_header_bytes: int, max_wire_bytes: int, max_reads: int):
        if not isinstance(policy, SourcePolicy) or not all(_positive(v) for v in
                (max_header_bytes, max_wire_bytes, max_reads)):
            raise FactFailure('invalid_https_configuration')
        self.policy = policy
        self.context = tls_context
        self.max_header_bytes = max_header_bytes
        self.max_wire_bytes = max_wire_bytes
        self.max_reads = max_reads
        self._check_tls()

    def _check_tls(self):
        if (not isinstance(self.context, ssl.SSLContext)
                or self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname
                or self.context.keylog_filename is not None):
            raise FactFailure('tls_verification_required')

    async def __call__(self, target: PinnedTarget) -> InjectedResponse:
        self._check_tls()
        if not isinstance(target, PinnedTarget):
            raise FactFailure('invalid_pinned_target')
        canonical = self.policy.target(target.url)
        if (canonical != target.url or urlsplit(canonical).hostname != target.hostname
                or not _positive(target.max_bytes) or target.max_bytes > self.policy.max_bytes
                or type(target.deadline) not in (int, float) or not math.isfinite(target.deadline)):
            raise FactFailure('invalid_pinned_target')
        addresses = public_addresses(target.addresses)  # every answer, not just selected IP
        # Exactly one address and one attempt. Never retry another IP on failure.
        return await self._exchange(target, addresses[0], 443)

    async def _exchange(self, target: PinnedTarget, address: str, port: int) -> InjectedResponse:
        """Private numeric-socket primitive; tests alone supply loopback/ephemeral port."""
        self._check_tls()
        loop = asyncio.get_running_loop()
        deadline = min(target.deadline, loop.time() + self.policy.timeout_seconds)
        if deadline <= loop.time():
            raise FactFailure('timeout')
        sock = None
        session = None
        writer = None
        handed_off = False
        try:
            async with asyncio.timeout_at(deadline):
                ip = ipaddress.ip_address(address)
                family = socket.AF_INET if ip.version == 4 else socket.AF_INET6
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.setblocking(False)
                endpoint = (str(ip), port) if ip.version == 4 else (str(ip), port, 0, 0)
                # Numeric inet_pton-compatible sockaddr: asyncio does not resolve host.
                await loop.sock_connect(sock, endpoint)
                if ipaddress.ip_address(sock.getpeername()[0]) != ip:
                    raise FactFailure('peer_not_pinned')
                self._check_tls()
                reader, writer = await asyncio.open_connection(
                    sock=sock, ssl=self.context, server_hostname=target.hostname,
                    ssl_handshake_timeout=max(deadline - loop.time(), 0.001),
                    ssl_shutdown_timeout=max(deadline - loop.time(), 0.001),
                    limit=min(self.max_header_bytes, 65536))
                # open_connection takes ownership; it receives no host/port to resolve.
                sock = None
                peer = writer.get_extra_info('peername')
                tls = writer.get_extra_info('ssl_object')
                if not peer or ipaddress.ip_address(peer[0]) != ip:
                    raise FactFailure('peer_not_pinned')
                if tls is None or tls.selected_alpn_protocol() not in (None, 'http/1.1'):
                    raise FactFailure('unsupported_tls_protocol')
                connection = h11.Connection(h11.CLIENT, max_incomplete_event_size=self.max_header_bytes)
                parsed = urlsplit(target.url)
                path = parsed.path or '/'
                if parsed.query:
                    path += '?' + parsed.query
                request = h11.Request(method=b'GET', target=path.encode('ascii'), headers=[
                    (b'Host', target.hostname.encode('ascii')),
                    (b'Accept', b'application/json, text/plain'),
                    (b'Accept-Encoding', b'identity'), (b'Connection', b'close')])
                writer.write(connection.send(request) + connection.send(h11.EndOfMessage()))
                await writer.drain()
                session = _Body(self, target, deadline, reader, writer, connection)
                response = await session.headers()
                # No implicit follow, including redirects. Caller owns response.close().
                result = InjectedResponse(target.url, str(ip), response.status_code,
                                        session.header(response, b'content-type', ''), session,
                                        session.header(response, b'content-encoding', 'identity'),
                                        session.header(response, b'content-length', None),
                                        session.header(response, b'location', None))
            handed_off = True
            return result
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise FactFailure('timeout') from None
        except ssl.SSLCertVerificationError:
            raise FactFailure('tls_certificate_invalid') from None
        except FactFailure:
            raise
        except (OSError, ssl.SSLError, h11.ProtocolError, ValueError):
            raise FactFailure('https_exchange_failed') from None
        finally:
            # Once a response is returned, _Body owns the socket and deadline timer.
            if not handed_off:
                if session is not None:
                    await session.aclose()
                elif writer is not None:
                    writer.transport.abort()
            if sock is not None:
                sock.close()


class _Body:
    def __init__(self, transport, target, deadline, reader, writer, connection):
        self.transport, self.target, self.deadline = transport, target, deadline
        self.reader, self.writer, self.connection = reader, writer, connection
        self.reads = self.wire_bytes = self.body_bytes = self.chunks = 0
        self.closed = False
        self.timer = asyncio.get_running_loop().call_at(deadline, self.abort)

    def abort(self):
        if not self.closed:
            self.closed = True
            self.timer.cancel()
            self.writer.transport.abort()  # no unbounded TLS shutdown wait

    async def aclose(self):
        self.abort()
        await asyncio.sleep(0)

    async def event(self):
        while True:
            if asyncio.get_running_loop().time() >= self.deadline:
                raise FactFailure('timeout')
            if self.closed:
                raise FactFailure('response_closed')
            event = self.connection.next_event()
            if event is not h11.NEED_DATA:
                return event
            if self.reads >= self.transport.max_reads:
                raise FactFailure('wire_read_limit')
            remaining = self.transport.max_wire_bytes - self.wire_bytes
            if remaining <= 0:
                raise FactFailure('wire_byte_limit')
            data = await self.reader.read(min(4096, remaining))
            self.reads += 1
            self.wire_bytes += len(data)
            self.connection.receive_data(data)

    @staticmethod
    def header(response, name, default):
        values = [value for key, value in response.headers if key == name]
        if len(values) > 1:
            raise FactFailure('duplicate_response_header')
        return values[0].decode('ascii') if values else default

    async def headers(self):
        event = await self.event()
        if not isinstance(event, h11.Response):
            raise FactFailure('unsupported_http_response')
        header_size = 20 + len(event.reason) + sum(len(k) + len(v) + 4 for k, v in event.headers)
        if header_size > self.transport.max_header_bytes:
            raise FactFailure('header_limit')
        # Examine framing before returning a response; no TE+CL ambiguity.
        length = self.header(event, b'content-length', None)
        transfer = self.header(event, b'transfer-encoding', None)
        if transfer is not None and length is not None:
            raise FactFailure('ambiguous_body_framing')
        if event.status_code == 200:
            _mime(self.header(event, b'content-type', ''))
            if self.header(event, b'content-encoding', 'identity').lower() != 'identity':
                raise FactFailure('encoded_body_rejected')
            if length is not None and (len(length) > 20 or not length.isascii()
                                       or not length.isdecimal() or int(length) > self.target.max_bytes):
                raise FactFailure('body_limit')
        # Validate even fields not used by this status (e.g. duplicate Location).
        for name in (b'content-type', b'content-encoding', b'location'):
            self.header(event, name, None)
        return event

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            async with asyncio.timeout_at(self.deadline):
                while True:
                    event = await self.event()
                    if isinstance(event, h11.Data):
                        self.chunks += 1
                        self.body_bytes += len(event.data)
                        if self.body_bytes > self.target.max_bytes:
                            raise FactFailure('body_limit')
                        if self.chunks > self.transport.policy.max_chunks:
                            raise FactFailure('chunk_limit')
                        return bytes(event.data)
                    if isinstance(event, h11.EndOfMessage):
                        if event.headers:
                            raise FactFailure('http_trailers_rejected')
                        await self.aclose()
                        raise StopAsyncIteration
                    raise FactFailure('malformed_http_body')
        except StopAsyncIteration:
            raise
        except asyncio.CancelledError:
            await self.aclose()
            raise
        except TimeoutError:
            await self.aclose()
            raise FactFailure('timeout') from None
        except FactFailure:
            await self.aclose()
            raise
        except (OSError, ssl.SSLError, h11.ProtocolError, ValueError):
            await self.aclose()
            raise FactFailure('https_body_failed') from None
