"""Password authentication and audited staff access for the workbench."""

import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from .security import TOKEN, USERNAME, PasswordHash, new_token, token_digest, valid_password
from .store import Account, AuditAction, AuditEvent, AuditResult, Failures, Role, Session, Store


SESSION_LIFETIME = 60 * 60
SESSION_IDLE = 15 * 60
FAILURE_LIMIT = 5
LOCKOUT = 15 * 60
RATE_WINDOW = 60
RATE_LIMIT = 20


class AuthenticationRequired(Exception):
    pass


class ExpiredSession(AuthenticationRequired):
    def __init__(self, digest: bytes) -> None:
        super().__init__()
        self.digest = digest


class AccessDenied(Exception):
    pass


class InvalidAccount(ValueError):
    pass


class AccountAction(StrEnum):
    CREATE = "create"
    RESET_PASSWORD = "reset_password"
    DISABLE = "disable"
    ENABLE = "enable"
    DELETE = "delete"
    UNLOCK = "unlock"
    CHANGE_ROLE = "change_role"


ACCOUNT_ACTIONS = {
    AccountAction.CREATE: AuditAction.ACCOUNT_CREATED,
    AccountAction.RESET_PASSWORD: AuditAction.PASSWORD_RESET,
    AccountAction.DISABLE: AuditAction.ACCOUNT_DISABLED,
    AccountAction.ENABLE: AuditAction.ACCOUNT_ENABLED,
    AccountAction.DELETE: AuditAction.ACCOUNT_DELETED,
    AccountAction.UNLOCK: AuditAction.ACCOUNT_UNLOCKED,
    AccountAction.CHANGE_ROLE: AuditAction.ROLE_CHANGED,
}


@dataclass(frozen=True)
class AccountStatus:
    username: str
    role: Role
    enabled: bool
    locked: bool
    has_password: bool


class Auth:
    def __init__(
        self, store: Store, *, clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.clock = clock
        self.monotonic = monotonic
        self._unknown_password = PasswordHash.make(new_token())

    def has_admin(self) -> bool:
        with self.store.locked():
            return any(account.role == Role.ADMIN and account.enabled and account.password is not None
                       for account in self.store.accounts())

    def bootstrap_admin(self, username: str, password: str) -> None:
        """Create the first administrator. Refused once any usable administrator exists."""
        with self.store.locked():
            if self.has_admin():
                raise AccessDenied
            if not USERNAME.fullmatch(username) or self.store.account(username) is not None or not valid_password(password):
                raise InvalidAccount
            self.store.save_account(Account(username, Role.ADMIN, PasswordHash.make(password)))
            self.store.append_audit(AuditEvent(self.clock(), AuditAction.ACCOUNT_CREATED, staff_target=username))

    def inspect_accounts(self, token: str) -> tuple[Session, tuple[AccountStatus, ...]]:
        with self.store.locked():
            now = self.monotonic()
            session = self._require_session(token, now, role=Role.ADMIN)
            accounts = tuple(AccountStatus(account.username, account.role, account.enabled,
                                           self.store.failures(account.username, now).count >= FAILURE_LIMIT,
                                           account.password is not None)
                             for account in sorted(self.store.accounts(), key=lambda item: item.username))
            return session, accounts

    def manage_account(
        self, token: str, csrf: str, action: AccountAction, username: str, role: str = "", password: str = "",
    ) -> None:
        with self.store.locked():
            session = self._require_session(token, self.monotonic(), role=Role.ADMIN, csrf=csrf)
            account = self.store.account(username)
            try:
                self._manage_account(session, action, account, username, role, password)
            except InvalidAccount as error:
                rejection = error
                self.store.append_audit(AuditEvent(self.clock(), ACCOUNT_ACTIONS[action], session.username,
                                                   result=AuditResult.DENIED,
                                                   staff_target=account.username if account else None))
            else:
                # The audit record names the actor, action and target only; never a password.
                self.store.append_audit(AuditEvent(self.clock(), ACCOUNT_ACTIONS[action], session.username,
                                                   staff_target=username))
                return
        raise rejection

    def _manage_account(
        self, session: Session, action: AccountAction, account: Account | None, username: str, role: str,
        password: str,
    ) -> None:
        if action == AccountAction.CREATE:
            if account is not None or not USERNAME.fullmatch(username) or role not in Role or not valid_password(password):
                raise InvalidAccount
            self.store.save_account(Account(username, Role(role), PasswordHash.make(password)))
            return
        if account is None:
            raise InvalidAccount
        if action == AccountAction.RESET_PASSWORD:
            # Also allowed on the administrator's own account; every session of the account ends.
            if not account.enabled or not valid_password(password):
                raise InvalidAccount
            self.store.save_account(replace(account, password=PasswordHash.make(password)))
            self.store.save_failures(username, Failures())
            self.store.revoke_staff_sessions(username)
            return
        if account.username == session.username:
            raise InvalidAccount
        if action == AccountAction.ENABLE:
            if account.enabled or account.password is None:
                raise InvalidAccount
            self.store.save_account(replace(account, enabled=True))
            self.store.save_failures(username, Failures())
        elif action == AccountAction.DELETE:
            # Retire only after disabling. The username stays reserved so audit references remain valid.
            if account.enabled or account.password is None:
                raise InvalidAccount
            self.store.save_account(replace(account, password=None))
            self.store.save_failures(username, Failures())
            self.store.revoke_staff_sessions(username)
        elif not account.enabled:
            raise InvalidAccount
        elif action == AccountAction.UNLOCK:
            self.store.save_failures(username, Failures())
        elif action == AccountAction.DISABLE:
            self.store.save_account(replace(account, enabled=False))
            self.store.revoke_staff_sessions(username)
        elif action == AccountAction.CHANGE_ROLE:
            if role not in Role:
                raise InvalidAccount
            self.store.save_account(replace(account, role=Role(role)))
            self.store.revoke_staff_sessions(username)
        else:
            raise InvalidAccount

    def login(self, username: str, password: str, *, previous_token: str = "") -> str | None:
        with self.store.locked():
            now = self.monotonic()
            timestamp = self.clock()
            if not self.store.allow_login_attempt(now, window=RATE_WINDOW, limit=RATE_LIMIT):
                self.store.append_audit(AuditEvent(timestamp, AuditAction.LOGIN_FAILED, result=AuditResult.DENIED))
                return None
            account = self.store.account(username)
            actor = account.username if account else None
            failures = self.store.failures(actor, now) if actor else Failures()
            if failures.count >= FAILURE_LIMIT:
                self.store.append_audit(AuditEvent(timestamp, AuditAction.LOGIN_FAILED, actor, result=AuditResult.DENIED))
                return None
            usable = account is not None and account.enabled and account.password is not None
            # Unknown, disabled and password-less accounts still pay the hash cost.
            password_hash = account.password if usable else self._unknown_password
            matched = password_hash.matches(password)
            if not (usable and matched):
                if usable:
                    self.store.save_failures(username, Failures(failures.count + 1, now + LOCKOUT))
                self.store.append_audit(AuditEvent(timestamp, AuditAction.LOGIN_FAILED, actor, result=AuditResult.DENIED))
                return None
            self.store.save_failures(username, Failures())
            self.store.prune_sessions(now)
            if TOKEN.fullmatch(previous_token):
                self.store.revoke_session(token_digest(previous_token))
            token = new_token()
            self.store.save_session(token_digest(token),
                                    Session(username, account.role, new_token(), now + SESSION_LIFETIME, now + SESSION_IDLE))
            self.store.append_audit(AuditEvent(timestamp, AuditAction.LOGIN, actor))
            return token

    def _require_session(
        self, token: str, now: float, *, role: Role | None = None, csrf: str | None = None, touch: bool = True,
    ) -> Session:
        if not TOKEN.fullmatch(token):
            raise AuthenticationRequired
        digest = token_digest(token)
        session = self.store.session(digest)
        if session is None:
            raise AuthenticationRequired
        if now >= min(session.expires_at, session.idle_until):
            self.store.revoke_session(digest)
            raise ExpiredSession(digest)
        if role is not None and session.role != role:
            raise AccessDenied
        if csrf is not None and (not TOKEN.fullmatch(csrf) or not hmac.compare_digest(session.csrf, csrf)):
            raise AccessDenied
        if not touch:
            return session
        renewed = replace(session, idle_until=min(now + SESSION_IDLE, session.expires_at))
        self.store.save_session(digest, renewed)
        return renewed

    def require_session(
        self, token: str, *, role: Role | None = None, csrf: str | None = None, touch: bool = True,
    ) -> Session:
        with self.store.locked():
            return self._require_session(token, self.monotonic(), role=role, csrf=csrf, touch=touch)

    def inspect_audit(self, token: str) -> tuple[Session, tuple[AuditEvent, ...]]:
        with self.store.locked():
            session = self._require_session(token, self.monotonic(), role=Role.ADMIN)
            self.store.append_audit(AuditEvent(self.clock(), AuditAction.VIEW, session.username))
            return session, self.store.audit_events()

    def logout(self, token: str, csrf: str) -> None:
        with self.store.locked():
            session = self._require_session(token, self.monotonic(), csrf=csrf)
            self.store.revoke_session(token_digest(token))
            self.store.append_audit(AuditEvent(self.clock(), AuditAction.LOGOUT, session.username))
