"""Host-injected history cursor policy and explicit limits. Not authorization or defaults."""
from dataclasses import dataclass, field
from typing import Protocol


class CursorResyncRequired(Exception):
    pass


class CursorUnavailable(Exception):
    pass


@dataclass(frozen=True, repr=False)
class CursorBinding:
    """Construct only from one trusted server context. Never deserialize caller scope.

    Binding metadata is not a capability. Current AUTH/resource checks are still
    required at every operation and before publishing private results. Token time
    claims are deliberately absent; this is not a session-revocation mechanism.
    """
    environment: str
    issuer: str
    subject: str
    audience: str
    scope: str
    purpose: str
    conversation_id: str | None
    # Live owner callback reference only: never serialize/asdict/cache/log.
    context: object | None = field(default=None,repr=False,compare=False)


class AuthenticatedCursorCodec(Protocol):
    """Host must authenticate/version/expire tokens and compare the entire binding.

    No default implementation, key, clock, lifetime or retention is supplied.
    Internal cursor fields, including decoded scope, never select repository.
    """
    def encode(self, cursor, *, binding: CursorBinding, ttl_seconds: int) -> str: ...
    def decode(self, token: str, *, binding: CursorBinding, ttl_seconds: int): ...


def _positive(value):
    return type(value) is int and value > 0


@dataclass(frozen=True)
class CursorPolicy:
    codec: AuthenticatedCursorCodec
    ttl_seconds: int
    max_token_bytes: int

    def __post_init__(self):
        if (not _positive(self.ttl_seconds) or not _positive(self.max_token_bytes)
                or not callable(getattr(self.codec,'encode',None))
                or not callable(getattr(self.codec,'decode',None))):
            raise ValueError('Explicit authenticated codec, TTL and token bound required')

    def decode(self, token, binding):
        if not isinstance(token,str) or not token or len(token.encode('utf-8')) > self.max_token_bytes:
            raise CursorResyncRequired()
        return self.codec.decode(token,binding=binding,ttl_seconds=self.ttl_seconds)

    def encode(self, cursor, binding):
        token = self.codec.encode(cursor,binding=binding,ttl_seconds=self.ttl_seconds)
        if not isinstance(token,str) or not token or len(token.encode('utf-8')) > self.max_token_bytes:
            raise CursorUnavailable()
        return token


@dataclass(frozen=True)
class HistoryWireConfiguration:
    max_page_limit: int
    max_draft_bytes: int
    max_private_response_bytes: int
    cursor_policy: CursorPolicy | None

    def __post_init__(self):
        # 100 is the fixed domain ceiling, not a selected product quota/default.
        if (not _positive(self.max_page_limit) or self.max_page_limit > 100
                or not _positive(self.max_draft_bytes) or not _positive(self.max_private_response_bytes)
                or self.cursor_policy is not None and not isinstance(self.cursor_policy,CursorPolicy)):
            raise ValueError('Explicit compatible page/draft/private-response limits required')
