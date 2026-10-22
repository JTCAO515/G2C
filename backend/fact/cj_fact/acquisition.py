"""Bounded injected acquisition and plain/JSON parser. Production dispatch is disabled.

Resolver/transport are trusted synthetic fixture code, never source-provided code.
No live adapter exists: peer_ip is an assertion from an injected test response,
not proof of a socket binding, TLS certificate or AUTH/USAGE/RUN admission.
"""
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Awaitable, Callable
from urllib.parse import urljoin, urlsplit

from .model import Document, aware
from .policy import FactFailure, SourcePolicy, canonical_url, public_addresses


@dataclass(frozen=True, repr=False)
class PinnedTarget:
    url: str
    hostname: str
    addresses: tuple[str, ...]
    max_bytes: int
    deadline: float  # asyncio loop monotonic time; one deadline across all hops


@dataclass(repr=False)
class InjectedResponse:
    """Only a synthetic response carrier, not a network-client wrapper."""
    url: str
    peer_ip: str
    status: int
    content_type: str
    body: AsyncIterator[bytes] = field(repr=False)
    content_encoding: str = 'identity'
    content_length: str | None = None
    location: str | None = None

    async def close(self):
        close = getattr(self.body, 'aclose', None)
        if close is not None:
            await close()


def _mime(content_type: str) -> str:
    parts = [part.strip().lower() for part in content_type.split(';')]
    if (parts[0] not in ('text/plain', 'application/json') or len(parts) > 2
            or (len(parts) == 2 and parts[1] not in ('charset=utf-8', 'charset="utf-8"'))):
        raise FactFailure('unsupported_content_type')
    return parts[0]


def _json_bounds(text: str, policy: SourcePolicy):
    # Bound nesting BEFORE the stdlib decoder; respect string escapes.
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > policy.max_json_depth:
                raise FactFailure('json_depth_limit')
        elif char in ']}':
            depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise FactFailure('duplicate_json_key')
            result[key] = value
        return result
    def constant(_):
        raise FactFailure('invalid_json_number')
    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
        stack = [value]
        count = 0
        while stack:
            item = stack.pop()
            count += 1
            if count > policy.max_json_nodes:
                raise FactFailure('json_node_limit')
            if isinstance(item, dict):
                stack.extend(item.keys())
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, float):
                import math
                if not math.isfinite(item):
                    raise FactFailure('invalid_json_number')
            elif isinstance(item, str):
                # Reject unpaired escaped surrogates rather than losing bytes downstream.
                item.encode('utf-8', errors='strict')
    except (ValueError, RecursionError, UnicodeError):
        raise FactFailure('malformed_json') from None


def parse_document(*, source_url: str, retrieved_at: datetime, content_type: str,
                   body: bytes, policy: SourcePolicy, synthetic: bool) -> Document:
    """No field inference, HTML rendering, script execution, model or translation call."""
    policy.target(source_url)
    if type(body) is not bytes:
        raise FactFailure('invalid_body')
    if len(body) > policy.max_bytes:
        raise FactFailure('body_limit')
    media_type = _mime(content_type)
    try:
        text = body.decode('utf-8', errors='strict')
    except UnicodeError:
        raise FactFailure('invalid_utf8') from None
    if not text or '\x00' in text:
        raise FactFailure('invalid_text')
    if media_type == 'application/json':
        _json_bounds(text, policy)
    return Document(source_url, retrieved_at, media_type, body, text, synthetic)


class RestrictedAcquisition:
    def __init__(self, policy: SourcePolicy | None = None):
        self.policy = policy

    async def fetch(self, url: str) -> Document:
        """Real entry always closed; constructor configuration never grants authority."""
        raise FactFailure('production_integration_unavailable')

    async def fetch_synthetic(self, url: str, *,
                              resolve: Callable[[str], Awaitable[tuple[str, ...]]],
                              transport: Callable[[PinnedTarget], Awaitable[InjectedResponse]],
                              retrieved_at: datetime, cancelled: asyncio.Event) -> Document:
        """Execute bounded policy/response logic using explicitly injected fixture IO.

        No ambient credentials, default target, live resolver, retries, auth token,
        budget receipt, account owner or provider SDK accepted by this interface.
        """
        if self.policy is None or not self.policy.allowed_origins:
            raise FactFailure('sources_unconfigured')
        aware(retrieved_at)
        if cancelled.is_set():
            raise FactFailure('cancelled')
        deadline = asyncio.get_running_loop().time() + self.policy.timeout_seconds
        operation = asyncio.create_task(self._acquire(url, resolve, transport, retrieved_at, cancelled, deadline))
        cancellation = asyncio.create_task(cancelled.wait())
        try:
            done, _ = await asyncio.wait((operation, cancellation), timeout=self.policy.timeout_seconds,
                                         return_when=asyncio.FIRST_COMPLETED)
            if cancelled.is_set():
                raise FactFailure('cancelled')
            if operation not in done:
                raise FactFailure('timeout')
            result = operation.result()
            if asyncio.get_running_loop().time() >= deadline:
                raise FactFailure('timeout')
            return result
        except asyncio.CancelledError:
            # Preserve normal task cancellation semantics; no successful late result.
            raise
        except FactFailure:
            raise
        except Exception:
            raise FactFailure('acquisition_failed') from None
        finally:
            operation.cancel()
            cancellation.cancel()
            await asyncio.gather(operation, cancellation, return_exceptions=True)

    @staticmethod
    def _checkpoint(cancelled, deadline):
        if cancelled.is_set():
            raise FactFailure('cancelled')
        if asyncio.get_running_loop().time() >= deadline:
            raise FactFailure('timeout')

    async def _acquire(self, url, resolve, transport, retrieved_at, cancelled, deadline):
        policy = self.policy
        seen = set()
        for hop in range(policy.max_redirects + 1):
            self._checkpoint(cancelled, deadline)
            target = policy.target(url)
            if target in seen:
                raise FactFailure('redirect_cycle')
            seen.add(target)
            host = urlsplit(target).hostname
            addresses = public_addresses(await resolve(host))
            self._checkpoint(cancelled, deadline)
            request = PinnedTarget(target, host, addresses, policy.max_bytes, deadline)
            response = await transport(request)
            try:
                if not isinstance(response, InjectedResponse):
                    raise FactFailure('invalid_response')
                self._checkpoint(cancelled, deadline)
                if response.url != target:
                    raise FactFailure('implicit_redirect_rejected')
                if public_addresses((response.peer_ip,))[0] not in addresses:
                    raise FactFailure('peer_not_pinned')
                # Header carrier is deliberately small, with no cookies/auth fields.
                headers = (response.content_type, response.content_encoding,
                           response.content_length, response.location)
                if any(value is not None and (type(value) is not str or len(value) > 4096
                       or any(ord(c) < 32 or ord(c) == 127 for c in value)) for value in headers):
                    raise FactFailure('invalid_response_headers')
                if type(response.status) is not int:
                    raise FactFailure('invalid_status')
                if response.status in (301, 302, 303, 307, 308):
                    if hop == policy.max_redirects:
                        raise FactFailure('redirect_limit')
                    if not response.location:
                        raise FactFailure('invalid_redirect')
                    # Check raw Location before urljoin can discard leading controls.
                    if '\\' in response.location or not response.location.isascii() or ' ' in response.location:
                        raise FactFailure('invalid_redirect')
                    url = urljoin(target, response.location)
                    policy.target(url)  # reject forbidden next hop before any resolver
                    continue
                if response.status != 200:
                    raise FactFailure('http_status')
                if response.content_encoding.lower() != 'identity':
                    raise FactFailure('encoded_body_rejected')
                _mime(response.content_type)
                declared_length = None
                if response.content_length is not None:
                    if not response.content_length.isascii() or not response.content_length.isdecimal():
                        raise FactFailure('invalid_content_length')
                    if len(response.content_length) > 20:
                        raise FactFailure('body_limit')
                    declared_length = int(response.content_length)
                    if declared_length > policy.max_bytes:
                        raise FactFailure('body_limit')
                data = bytearray()
                chunks = 0
                async for chunk in response.body:
                    self._checkpoint(cancelled, deadline)
                    chunks += 1
                    if chunks > policy.max_chunks:
                        raise FactFailure('chunk_limit')
                    if type(chunk) is not bytes:
                        raise FactFailure('invalid_chunk')
                    if len(data) + len(chunk) > policy.max_bytes:
                        raise FactFailure('body_limit')
                    data.extend(chunk)
                    await asyncio.sleep(0)  # let total deadline / cancellation run
                if declared_length is not None and declared_length != len(data):
                    raise FactFailure('content_length_mismatch')
                self._checkpoint(cancelled, deadline)
                return parse_document(source_url=target, retrieved_at=retrieved_at,
                                      content_type=response.content_type, body=bytes(data),
                                      policy=policy, synthetic=True)
            finally:
                if isinstance(response, InjectedResponse):
                    await response.close()
