"""Workstation-only storage. The interface owns the atomic operation boundary."""

from collections import deque
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock
from typing import Protocol

from .security import PasswordHash


class Role(StrEnum):
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class AuditAction(StrEnum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_DISABLED = "account_disabled"
    ACCOUNT_UNLOCKED = "account_unlocked"
    ROLE_CHANGED = "role_changed"
    TOTP_BOUND = "totp_bound"
    TOTP_REBIND_AUTHORIZED = "totp_rebind_authorized"
    VIEW = "view"
    ANNOTATE = "annotate"
    EXPORT = "export"
    REVEAL = "reveal"
    DECIDE = "decide"


class AuditResult(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"


@dataclass(frozen=True)
class SetupGrant:
    digest: bytes = field(repr=False)
    expires_at: float


@dataclass(frozen=True)
class Account:
    username: str
    role: Role
    password: PasswordHash | None = field(default=None, repr=False)
    totp_seed: bytes | None = field(default=None, repr=False)
    last_totp_step: int = -1
    setup: SetupGrant | None = field(default=None, repr=False)
    enabled: bool = True


@dataclass(frozen=True)
class Session:
    username: str
    role: Role
    csrf: str = field(repr=False)
    expires_at: float
    idle_until: float


@dataclass(frozen=True)
class CaseAuditDetail:
    action: str
    step_id: str | None = None
    revision: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    timestamp: float
    action: AuditAction
    actor: str | None = None
    case_id: str | None = None
    result: AuditResult = AuditResult.SUCCESS
    staff_target: str | None = None
    signal_reference: str | None = field(default=None, repr=False)
    case_detail: CaseAuditDetail | None = None


@dataclass(frozen=True)
class Failures:
    count: int = 0
    until: float = 0


class Store(Protocol):
    def locked(self) -> AbstractContextManager: ...
    def account(self, username: str) -> Account | None: ...
    def accounts(self) -> tuple[Account, ...]: ...
    def save_account(self, account: Account) -> None: ...
    def failures(self, username: str, now: float) -> Failures: ...
    def save_failures(self, username: str, failures: Failures) -> None: ...
    def allow_login_attempt(self, now: float, *, window: float, limit: int) -> bool: ...
    def session(self, digest: bytes) -> Session | None: ...
    def save_session(self, digest: bytes, session: Session) -> None: ...
    def revoke_session(self, digest: bytes) -> None: ...
    def prune_sessions(self, now: float) -> None: ...
    def revoke_staff_sessions(self, username: str) -> None: ...
    def append_audit(self, event: AuditEvent) -> None: ...
    def audit_events(self) -> tuple[AuditEvent, ...]: ...


class MemoryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._accounts: dict[str, Account] = {}
        self._failures: dict[str, Failures] = {}
        self._attempts: deque[float] = deque()
        self._sessions: dict[bytes, Session] = {}
        self._audit: list[AuditEvent] = []

    def locked(self) -> AbstractContextManager:
        return self._lock

    def account(self, username: str) -> Account | None:
        return self._accounts.get(username)

    def accounts(self) -> tuple[Account, ...]:
        return tuple(self._accounts.values())

    def save_account(self, account: Account) -> None:
        self._accounts[account.username] = account

    def failures(self, username: str, now: float) -> Failures:
        state = self._failures.get(username, Failures())
        return state if now < state.until else Failures()

    def save_failures(self, username: str, failures: Failures) -> None:
        self._failures[username] = failures

    def allow_login_attempt(self, now: float, *, window: float, limit: int) -> bool:
        while self._attempts and self._attempts[0] <= now - window:
            self._attempts.popleft()
        if len(self._attempts) >= limit:
            return False
        self._attempts.append(now)
        return True

    def session(self, digest: bytes) -> Session | None:
        return self._sessions.get(digest)

    def save_session(self, digest: bytes, session: Session) -> None:
        self._sessions[digest] = session

    def revoke_session(self, digest: bytes) -> None:
        self._sessions.pop(digest, None)

    def prune_sessions(self, now: float) -> None:
        for digest, session in tuple(self._sessions.items()):
            if now >= min(session.expires_at, session.idle_until):
                self.revoke_session(digest)

    def revoke_staff_sessions(self, username: str) -> None:
        for digest, session in tuple(self._sessions.items()):
            if session.username == username:
                self.revoke_session(digest)

    def append_audit(self, event: AuditEvent) -> None:
        with self._lock:
            self._audit.append(event)

    def audit_events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._audit)
