"""CJ-JWKS-PROVIDER@0.1.0-rc.1: injected transport only, no default HTTP client."""
import json
import math
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
import jwt
from cryptography.hazmat.primitives import serialization
from .jwt_adapter import JWTConfiguration, VerificationKey

JWKS_PROVIDER_VERSION = 'CJ-JWKS-PROVIDER@0.1.0-rc.1'


def _https(value):
    if not isinstance(value, str) or any(c.isspace() for c in value): return False
    try:
        url = urlsplit(value)
        _ = url.port
        return bool(url.scheme == 'https' and url.hostname and not url.username
                    and not url.password and not url.query and not url.fragment)
    except ValueError: return False


@dataclass(frozen=True)
class JWKSConfiguration:
    issuer: str
    url: str
    algorithm: str
    cache_ttl_seconds: float
    refresh_interval_seconds: float
    request_timeout_seconds: float
    max_response_bytes: int
    max_chunks: int
    max_keys: int
    max_kid_bytes: int
    max_rsa_bits: int

    def __post_init__(self):
        if not _https(self.issuer) or not _https(self.url) or self.algorithm not in ('RS256', 'ES256'):
            raise ValueError('explicit trusted HTTPS binding required')
        for v in (self.cache_ttl_seconds, self.refresh_interval_seconds, self.request_timeout_seconds):
            if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
                raise ValueError('positive finite explicit timing required')
        for v in (self.max_response_bytes, self.max_chunks, self.max_keys, self.max_kid_bytes, self.max_rsa_bits):
            if type(v) is not int or v <= 0: raise ValueError('positive integer bound required')
        if self.max_rsa_bits < 2048: raise ValueError('RSA bound below minimum strength')


@dataclass(frozen=True)
class JWKSRequest:
    url: str
    timeout_seconds: float
    max_response_bytes: int
    cancelled: threading.Event


class JWKSResponse(Protocol):
    status: int
    final_url: str
    content_type: str
    chunks: Iterable[bytes]
    def close(self) -> None: ...


class JWKSTransport(Protocol):
    """Must enforce connect/read deadlines and cancellation, and never follow redirects."""
    def fetch(self, request: JWKSRequest) -> JWKSResponse: ...


class BoundedJWKSProvider:
    def __init__(self, *, verification: JWTConfiguration | None = None,
                 configuration: JWKSConfiguration | None = None,
                 transport: JWKSTransport | None = None, clock=time.monotonic):
        if configuration is not None and verification is not None:
            if configuration.issuer != verification.issuer or configuration.algorithm != verification.algorithm:
                raise ValueError('JWKS binding must match explicit verifier issuer/algorithm')
        self._enabled = configuration is not None and verification is not None and transport is not None
        self._config, self._transport, self._clock = configuration, transport, clock
        self._lock = threading.Lock()
        self._cache = {}
        self._expires_at = self._next_refresh = self._last_clock = float('-inf')
        self._inflight = None
        self._closed = False

    def _now(self):
        value = self._clock()
        if type(value) not in (int, float) or not math.isfinite(value) or value < self._last_clock:
            raise ValueError('invalid monotonic clock')
        self._last_clock = value
        return value

    def resolve(self, key_id: str) -> VerificationKey | None:
        if not self._enabled or not isinstance(key_id, str): return None
        request = None
        try:
            if (len(key_id) > self._config.max_kid_bytes or
                    len(key_id.encode('utf-8')) > self._config.max_kid_bytes or not key_id.strip()): return None
            with self._lock:
                if self._closed: return None
                now = self._now()
                if now < self._expires_at and key_id in self._cache: return self._cache[key_id]
                # One refresh across all kids. No unbounded negative-kid cache or waiter queue.
                if self._inflight is not None or now < self._next_refresh: return None
                request = JWKSRequest(self._config.url, self._config.request_timeout_seconds,
                                      self._config.max_response_bytes, threading.Event())
                self._inflight = request
                self._next_refresh = now + self._config.refresh_interval_seconds
                started = now
            keys = self._fetch(request, started)
            with self._lock:
                finished = self._now()
                if self._closed or request.cancelled.is_set() or self._inflight is not request: return None
                if keys is None or finished >= started + request.timeout_seconds: return None
                self._cache = keys  # atomic replacement; removed keys are not retained
                self._expires_at = started + self._config.cache_ttl_seconds
                if finished >= self._expires_at: return None
                return keys.get(key_id)
        except Exception:
            return None  # infrastructure/parse failures are UNKNOWN, never invalid identity
        finally:
            if request is not None:
                with self._lock:
                    if self._inflight is request: self._inflight = None

    def cancel_refresh(self):
        with self._lock:
            if self._inflight is not None: self._inflight.cancelled.set()
            # Do not reset cooldown: cancellation cannot create a request storm.

    def close(self):
        with self._lock:
            self._closed = True
            self._cache = {}
            self._expires_at = float('-inf')
            if self._inflight is not None: self._inflight.cancelled.set()

    def _within_budget(self, request, started):
        with self._lock:
            return not request.cancelled.is_set() and not self._closed and self._now() < started + request.timeout_seconds

    def _fetch(self, request, started):
        response = None
        try:
            if not self._within_budget(request, started): return None
            response = self._transport.fetch(request)
            if (response.status != 200 or response.final_url != request.url or
                    response.content_type.split(';', 1)[0].strip().lower()
                    not in ('application/json', 'application/jwk-set+json')): return None
            data = bytearray()
            for index, chunk in enumerate(response.chunks):
                if (index >= self._config.max_chunks or not self._within_budget(request, started)
                        or not isinstance(chunk, bytes) or len(data)+len(chunk) > request.max_response_bytes): return None
                data.extend(chunk)
            if not self._within_budget(request, started): return None
            return self._parse(bytes(data))
        except Exception:
            return None
        finally:
            if response is not None: response.close()

    def _parse(self, data):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError('duplicate JWKS member')
                result[key] = value
            return result
        document = json.loads(data.decode('utf-8'), object_pairs_hook=unique)
        if (not isinstance(document, dict) or set(document) != {'keys'} or
                not isinstance(document['keys'], list) or len(document['keys']) > self._config.max_keys):
            raise ValueError('bounded JWKS object required')
        keys, seen = {}, set()
        for item in document['keys']:
            if not isinstance(item, dict): raise ValueError('JWK object required')
            kid = item.get('kid')
            if (not isinstance(kid, str) or not kid.strip() or len(kid.encode('utf-8')) > self._config.max_kid_bytes
                    or kid in seen or set(item) & {'d', 'p', 'q', 'dp', 'dq', 'qi', 'oth', 'k'}):
                raise ValueError('ambiguous/private JWK rejected')
            seen.add(kid)
            if item.get('alg') != self._config.algorithm: continue
            if item.get('use', 'sig') != 'sig' or item.get('key_ops', ['verify']) != ['verify']:
                raise ValueError('verification key required')
            expected = 'RSA' if self._config.algorithm == 'RS256' else 'EC'
            if item.get('kty') != expected: raise ValueError('algorithm/key type mismatch')
            public = jwt.PyJWK.from_dict(item, algorithm=self._config.algorithm).key
            if expected == 'RSA' and public.key_size > self._config.max_rsa_bits:
                raise ValueError('RSA size exceeds configured bound')
            material = VerificationKey(self._config.algorithm, public.public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
            material.load()
            keys[kid] = material
        return keys
