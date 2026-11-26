"""Local workbench credentials and session token primitives."""

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass


USERNAME = re.compile(r"[a-z][a-z0-9_-]{2,31}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
TOTP_SEED = re.compile(r"[A-Z2-7]{32}")
TOTP_CODE = re.compile(r"[0-9]{6}")
TOTP_PERIOD = 30


@dataclass(frozen=True, repr=False)
class PasswordHash:
    salt: bytes
    digest: bytes

    @staticmethod
    def _derive(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode(), salt=salt, n=2**17, r=8, p=1, maxmem=2**28)

    @classmethod
    def make(cls, password: str) -> "PasswordHash":
        salt = secrets.token_bytes(16)
        return cls(salt, cls._derive(password, salt))

    def matches(self, password: str) -> bool:
        return hmac.compare_digest(self.digest, self._derive(password, self.salt))


def decode_totp_seed(seed: str) -> bytes:
    normalized = seed.replace(" ", "").upper()
    if not TOTP_SEED.fullmatch(normalized):
        raise ValueError("invalid TOTP seed")
    return base64.b32decode(normalized)


def totp_at_step(seed: bytes, step: int, *, digits: int = 6) -> str:
    digest = hmac.digest(seed, step.to_bytes(8, "big"), "sha1")
    offset = digest[-1] & 0x0F
    value = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def verify_totp(seed: bytes, code: str, now: float, last_step: int = -1) -> int | None:
    if not TOTP_CODE.fullmatch(code):
        return None
    step = int(now) // TOTP_PERIOD
    candidates = [candidate for candidate in (step - 1, step, step + 1)
                  if candidate >= 0 and hmac.compare_digest(totp_at_step(seed, candidate), code)]
    return candidates[-1] if candidates and candidates[0] > last_step else None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()
