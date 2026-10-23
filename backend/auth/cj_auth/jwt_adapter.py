"""Strict configurable PyJWT verifier. No HTTP/JWKS fetcher or environment defaults."""
import base64
import json
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit
from uuid import UUID
from types import MappingProxyType
from typing import Protocol

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from .interfaces import TrustedPrincipal, VerificationResult, VerificationStatus as V
from .session_binding import VerifiedSessionBinding, SessionVerificationResult


class JWTProfile(Enum):
    STRICT_V1 = "CJ-JWT-STRICT@0.1.0"
    SUPABASE_ACCESS_RC1 = "CJ-JWT-SUPABASE-ACCESS@0.1.0-rc.1"


@dataclass(frozen=True)
class JWTConfiguration:
    issuer: str
    audience: str
    algorithm: str
    clock_skew_seconds: int
    max_token_bytes: int = 16384  # local input bound, not a provider limit
    profile: JWTProfile = JWTProfile.STRICT_V1  # keep the previously tested path unchanged

    def __post_init__(self):
        if (not isinstance(self.issuer, str) or not self.issuer.strip()
                or not isinstance(self.audience, str) or not self.audience.strip()
                or self.algorithm not in ('RS256', 'ES256')
                or type(self.clock_skew_seconds) is not int or self.clock_skew_seconds < 0
                or type(self.max_token_bytes) is not int or self.max_token_bytes <= 0):
            raise ValueError('invalid explicit JWT configuration')
        if not isinstance(self.profile, JWTProfile):
            raise ValueError('explicit supported JWT profile required')
        if self.profile is JWTProfile.SUPABASE_ACCESS_RC1:
            issuer = urlsplit(self.issuer)
            if (issuer.scheme != 'https' or not issuer.hostname or issuer.username or issuer.password
                    or issuer.query or issuer.fragment or self.issuer != self.issuer.strip()
                    or self.audience != self.audience.strip()):
                raise ValueError('invalid explicit Supabase access configuration')


@dataclass(frozen=True, repr=False)
class VerificationKey:
    algorithm: str
    public_pem: bytes

    def load(self):
        key = serialization.load_pem_public_key(self.public_pem)
        if self.algorithm == 'RS256' and isinstance(key, rsa.RSAPublicKey) and key.key_size >= 2048:
            return key
        if (self.algorithm == 'ES256' and isinstance(key, ec.EllipticCurvePublicKey)
                and isinstance(key.curve, ec.SECP256R1)):
            return key
        raise ValueError('unsupported public verification key')


class KeyProvider(Protocol):
    def resolve(self, key_id: str) -> VerificationKey | None: ...


class StaticPublicKeys:
    """Explicit server-provisioned key set; missing kid is UNKNOWN, never auto-fetch."""
    def __init__(self, keys: dict[str, VerificationKey]):
        for kid, key in keys.items():
            if not isinstance(kid, str) or not kid.strip() or not isinstance(key, VerificationKey):
                raise ValueError('invalid public key configuration')
            key.load()  # reject private/malformed/wrong-size/curve keys at composition time
        self._keys = MappingProxyType(dict(keys))

    def resolve(self, key_id: str) -> VerificationKey | None:
        return self._keys.get(key_id)


def _object(segment: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON member')
            result[key] = value
        return result
    raw = base64.urlsafe_b64decode(segment + '=' * (-len(segment) % 4))
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if not isinstance(value, dict):
        raise ValueError('JWT object required')
    return value


class PyJWTVerifier:
    def __init__(self, configuration: JWTConfiguration | None = None, keys: KeyProvider | None = None):
        self._configuration, self._keys = configuration, keys

    def verify(self, token: str) -> VerificationResult:
        return self._verify(token)

    def verify_session(self, token: str) -> SessionVerificationResult:
        config = self._configuration
        if config is None or config.profile is not JWTProfile.SUPABASE_ACCESS_RC1:
            return SessionVerificationResult(V.UNKNOWN)
        result = self._verify(token, include_session=True)
        if isinstance(result, SessionVerificationResult): return result
        return SessionVerificationResult(result.status)

    def _verify(self, token: str, *, include_session=False):
        config = self._configuration
        if config is None or self._keys is None:
            return VerificationResult(V.UNKNOWN)
        try:
            if not isinstance(token, str) or len(token.encode('utf-8')) > config.max_token_bytes:
                return VerificationResult(V.INVALID)
            segments = token.split('.')
            if len(segments) != 3:
                return VerificationResult(V.INVALID)
            header, payload = _object(segments[0]), _object(segments[1])
            # Token headers may only select an existing kid, never a URL/key/algorithm policy.
            if (set(header) - {'alg', 'typ', 'kid'} or header.get('alg') != config.algorithm
                    or header.get('typ') != 'JWT' or not isinstance(header.get('kid'), str)
                    or not header['kid'].strip()):
                return VerificationResult(V.INVALID)
            required_times = ('exp', 'iat', 'nbf') if config.profile is JWTProfile.STRICT_V1 else ('exp', 'iat')
            if (any(type(payload.get(k)) is not int for k in required_times)
                    or ('nbf' in payload and type(payload['nbf']) is not int)
                    or payload['exp'] <= max(payload['iat'], payload.get('nbf', payload['iat']))
                    or not isinstance(payload.get('sub'), str) or not payload['sub'].strip()):
                return VerificationResult(V.INVALID)
            if config.profile is JWTProfile.SUPABASE_ACCESS_RC1:
                # User access-token shape, not a grant from role/email/metadata.
                if (payload.get('role') != 'authenticated' or payload.get('is_anonymous') is not False
                        or payload.get('aal') not in ('aal1', 'aal2')
                        or any(not isinstance(payload.get(k), str) for k in ('email', 'phone'))
                        or any(not isinstance(payload.get(k), str) or str(UUID(payload[k])) != payload[k]
                               for k in ('sub', 'session_id'))):
                    return VerificationResult(V.INVALID)
                audience = payload.get('aud')
                if not (isinstance(audience, str) and audience.strip()
                        or isinstance(audience, list) and audience
                        and all(isinstance(item, str) and item.strip() for item in audience)
                        and len(set(audience)) == len(audience)):
                    return VerificationResult(V.INVALID)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return VerificationResult(V.INVALID)
        try:
            material = self._keys.resolve(header['kid'])
            if not isinstance(material, VerificationKey) or material.algorithm != config.algorithm:
                return VerificationResult(V.UNKNOWN)
            key = material.load()
        except Exception:
            # Broken/unavailable key infrastructure is not evidence of invalid credentials.
            return VerificationResult(V.UNKNOWN)
        try:
            claims = jwt.decode(
                token, key, algorithms=[config.algorithm], issuer=config.issuer,
                audience=config.audience, leeway=config.clock_skew_seconds,
                options={'require': ['iss', 'aud', 'sub', 'exp', 'iat']
                         + (['nbf'] if config.profile is JWTProfile.STRICT_V1 else []),
                         'verify_signature': True, 'verify_exp': True, 'verify_iat': True,
                         'verify_nbf': True, 'verify_iss': True, 'verify_aud': True,
                         'verify_sub': True, 'strict_aud': config.profile is JWTProfile.STRICT_V1,
                         'enforce_minimum_key_length': True},
            )
        except jwt.InvalidTokenError:
            return VerificationResult(V.INVALID)
        except Exception:
            return VerificationResult(V.UNKNOWN)
        principal = TrustedPrincipal(claims['iss'], claims['sub'], config.audience, claims['iat'],
                                     claims.get('nbf', claims['iat']), claims['exp'])
        if include_session:
            # Read only the claim returned by the SAME successful signature/claim validation.
            return SessionVerificationResult(V.VALID, VerifiedSessionBinding(principal, UUID(claims['session_id'])))
        return VerificationResult(V.VALID, principal)
