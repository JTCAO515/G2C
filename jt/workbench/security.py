"""Workbench password hashing, password policy and session token primitives."""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass


USERNAME = re.compile(r"[a-z][a-z0-9_-]{2,31}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
PASSWORD_MIN = 12
PASSWORD_MAX = 128


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


def valid_password(password: str) -> bool:
    return PASSWORD_MIN <= len(password) <= PASSWORD_MAX


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()
