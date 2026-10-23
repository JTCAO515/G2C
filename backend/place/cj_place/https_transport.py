"""Fixed Gaode v3 HTTPS candidate. NOT a canonical authorized dispatch entry.

No registration, environment/proxy/cookie lookup, redirects, retry or usage
settlement. Tests replace only the private dial function with local TLS.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import ssl
from typing import Literal
from urllib.parse import urlencode

from .gaode import Config, PreparedRequest, Response, _decode, prepare
from .models import ORIGIN, aware

_HOST = "restapi.amap.com"
_HEADER_LIMIT = 16384  # fixed narrow HTTP profile, not a user/provider quota
_PATHS = frozenset(("/v3/place/text", "/v3/place/detail",
                    "/v3/direction/walking", "/v3/direction/driving"))


@dataclass(frozen=True, repr=False)
class ProviderCredentials:
    """Trusted host's per-call secret; never included in a prepared binding."""
    api_key: str = field(repr=False)
    expires_at: datetime

    def __post_init__(self):
        if type(self.api_key) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", self.api_key):
            raise ValueError("provider_credentials_invalid")
        aware(self.expires_at)

    def __repr__(self):
        return "ProviderCredentials(<redacted>)"


@dataclass(frozen=True)
class TransportResult:
    # received means complete bounded HTTP receipt, NOT successful provider data.
    state: Literal["received", "rejected", "unknown"]
    reason: str
    response: Response | None = field(default=None, repr=False)


class _WireFailure(Exception):
    pass


def _tls_context():
    # Construct directly: create_default_context can enable SSLKEYLOGFILE from env.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["http/1.1"])
    return context


async def _connect():
    return await asyncio.open_connection(_HOST, 443, ssl=_tls_context(),
                                         server_hostname=_HOST, limit=_HEADER_LIMIT)


def _secret_in(body, secret):
    if secret.encode("ascii") in body:
        return True
    # Also reject JSON-escaped echoes without changing the returned original bytes.
    try:
        decoded = _decode(body)
    except Exception:
        # An uninspectable body is not proof that a recoverable secret is absent.
        # Refuse it before constructing any Response; retain valid bytes as-is.
        raise _WireFailure("response_secret_check_unavailable") from None

    def contains(value):
        if isinstance(value, str):
            return secret in value
        if isinstance(value, dict):
            return any(contains(k) or contains(v) for k, v in value.items())
        if isinstance(value, list):
            return any(contains(v) for v in value)
        return False
    return contains(decoded)


async def _read_response(reader, body_limit):
    """Bound header/framing bytes as well as body; no decompression/cookie state."""
    wire_left = body_limit + _HEADER_LIMIT

    async def take_until(separator):
        nonlocal wire_left
        data = await reader.readuntil(separator)
        wire_left -= len(data)
        if wire_left < 0:
            raise _WireFailure("response_wire_limit")
        return data

    header = await take_until(b"\r\n\r\n")
    if len(header) > _HEADER_LIMIT:
        raise _WireFailure("response_headers_limit")
    lines = header[:-4].split(b"\r\n")
    if not re.fullmatch(rb"HTTP/1\.[01] [1-5][0-9]{2} [^\r\n]*", lines[0]):
        raise _WireFailure("response_status_invalid")
    status = int(lines[0].split(b" ", 2)[1])
    if status < 200:
        raise _WireFailure("interim_response_unsupported")
    headers = {}
    if len(lines) > 101:
        raise _WireFailure("response_headers_limit")
    for line in lines[1:]:
        if len(line) > 4096 or b":" not in line:
            raise _WireFailure("response_headers_invalid")
        name, value = line.split(b":", 1)
        if not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
            raise _WireFailure("response_headers_invalid")
        name = name.lower()
        if name in (b"content-length", b"transfer-encoding", b"content-encoding") and name in headers:
            raise _WireFailure("response_framing_ambiguous")
        headers[name] = value.strip()
    length = headers.get(b"content-length")
    transfer = headers.get(b"transfer-encoding")
    if length is not None and transfer is not None:
        raise _WireFailure("response_framing_ambiguous")
    if transfer is not None and transfer.lower() != b"chunked":
        raise _WireFailure("response_transfer_unsupported")
    if headers.get(b"content-encoding", b"identity").lower() != b"identity":
        raise _WireFailure("response_encoding_unsupported")
    # Non-200 data is unnecessary for parse_response and may echo a secret URL.
    # Discard all of it and close; never follow Location or retain Set-Cookie.
    if status != 200:
        return status, b""
    chunks = []
    size = 0

    async def take_body(count):
        nonlocal size, wire_left
        if count > body_limit - size or count > wire_left:
            raise _WireFailure("response_bytes_limit")
        while count:
            part = await reader.readexactly(min(count, 8192))
            count -= len(part)
            size += len(part)
            wire_left -= len(part)
            chunks.append(part)

    if length is not None:
        if not re.fullmatch(rb"[0-9]{1,20}", length):
            raise _WireFailure("response_length_invalid")
        await take_body(int(length))
    elif transfer is not None:
        while True:
            line = await take_until(b"\r\n")
            if len(line) > 128 or not re.fullmatch(rb"[0-9a-fA-F]{1,16}\r\n", line):
                raise _WireFailure("response_chunk_invalid")
            count = int(line[:-2], 16)
            if count == 0:
                # Narrow provider profile: no chunk extensions or trailers.
                if await take_until(b"\r\n") != b"\r\n":
                    raise _WireFailure("response_trailers_unsupported")
                break
            await take_body(count)
            if await take_until(b"\r\n") != b"\r\n":
                raise _WireFailure("response_chunk_invalid")
    else:
        while True:
            part = await reader.read(min(8192, body_limit - size + 1, wire_left + 1))
            if not part:
                break
            size += len(part)
            wire_left -= len(part)
            if size > body_limit or wire_left < 0:
                raise _WireFailure("response_bytes_limit")
            chunks.append(part)
    return status, b"".join(chunks)


async def fetch_candidate(config: Config, request: PreparedRequest,
                          credentials: ProviderCredentials) -> TransportResult:
    """Low-level one-shot candidate, never authorization or a retry/recovery API.

    Credentials must come from trusted host configuration. This function performs
    no AUTH/USAGE/RUN operation. Production execute remains unconditionally closed.
    Every result after possible I/O failure is unknown; caller must preserve the
    original attempt. Caller cancellation propagates after close/abort, never as
    proof of non-dispatch. No raw exception, secret URL or body is logged.
    """
    writer = None
    cancelled = False
    outcome = TransportResult("unknown", "transport_unknown")
    try:
        if type(config) is not Config or type(request) is not PreparedRequest or type(credentials) is not ProviderCredentials:
            return TransportResult("rejected", "transport_configuration_invalid")
        if prepare(config, request.query, request.request_ref, request.started_at) != request or request.origin != ORIGIN or request.path not in _PATHS:
            return TransportResult("rejected", "request_binding_invalid")
        credentials.__post_init__()
        expires = credentials.expires_at.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if now >= expires:
            return TransportResult("rejected", "credentials_expired")
        age = (now - request.started_at.astimezone(timezone.utc)).total_seconds()
        if age < 0:
            return TransportResult("rejected", "request_time_invalid")
        remaining = min(config.timeout_seconds, config.max_age_seconds) - age
        if remaining <= 0:
            return TransportResult("rejected", "request_deadline_expired")
        remaining = min(remaining, (expires - now).total_seconds())
        target = request.path + "?" + urlencode((*request.params, ("key", credentials.api_key)))
        if len((ORIGIN + target).encode("ascii")) > config.max_request_bytes:
            return TransportResult("rejected", "credentialed_request_bytes_limit")
    except Exception:
        return TransportResult("rejected", "transport_configuration_invalid")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + remaining
    try:
        async with asyncio.timeout_at(deadline):
            reader, writer = await _connect()
            if loop.time() >= deadline:
                raise _WireFailure("connect_deadline_exceeded")
            if datetime.now(timezone.utc) >= expires:
                raise _WireFailure("credentials_expired_unknown")
            payload = ("GET " + target + " HTTP/1.1\r\nHost: " + _HOST +
                       "\r\nAccept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n").encode("ascii")
            writer.write(payload)
            await writer.drain()
            status, body = await _read_response(reader, config.max_response_bytes)
            if status == 200 and _secret_in(body, credentials.api_key):
                raise _WireFailure("credential_echo_rejected")
            receipt = Response(request.binding_digest, request.origin, request.path, status, body,
                               datetime.now(timezone.utc))
            outcome = TransportResult("received", "http_received", receipt)
    except asyncio.CancelledError:
        cancelled = True
    except _WireFailure as error:
        outcome = TransportResult("unknown", error.args[0])
    except Exception:
        outcome = TransportResult("unknown", "transport_unknown")
    finally:
        if writer is not None:
            try:
                writer.close()
                async with asyncio.timeout_at(deadline):
                    await writer.wait_closed()
            except asyncio.CancelledError:
                cancelled = True
                with suppress(Exception):
                    writer.transport.abort()
            except Exception:
                with suppress(Exception):
                    writer.transport.abort()
                outcome = TransportResult("unknown", "close_unknown")
    if cancelled:
        raise asyncio.CancelledError() from None
    if loop.time() > deadline or datetime.now(timezone.utc) >= expires:
        return TransportResult("unknown", "deadline_or_credentials_expired")
    return outcome
