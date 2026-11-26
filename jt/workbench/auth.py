"""Authentication, replay protection and audited staff access for the local workbench."""

import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from .security import TOKEN, USERNAME, PasswordHash, decode_totp_seed, new_token, token_digest, verify_totp
from .store import Account, AuditAction, AuditEvent, AuditResult, Failures, Role, Session, SetupGrant, Store


SESSION_LIFETIME = 60 * 60
SESSION_IDLE = 15 * 60
FAILURE_LIMIT = 5
LOCKOUT = 15 * 60
RATE_WINDOW = 60
RATE_LIMIT = 20
SETUP_LIFETIME = 15 * 60


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
    DISABLE = "disable"
    UNLOCK = "unlock"
    CHANGE_ROLE = "change_role"
    REBIND = "rebind"


ACCOUNT_ACTIONS = {
    AccountAction.CREATE: AuditAction.ACCOUNT_CREATED,
    AccountAction.DISABLE: AuditAction.ACCOUNT_DISABLED,
    AccountAction.UNLOCK: AuditAction.ACCOUNT_UNLOCKED,
    AccountAction.CHANGE_ROLE: AuditAction.ROLE_CHANGED,
    AccountAction.REBIND: AuditAction.TOTP_REBIND_AUTHORIZED,
}


@dataclass(frozen=True)
class AccountStatus:
    username: str
    role: Role
    enabled: bool
    locked: bool
    setup_pending: bool


def _binding(password: str, seed: str, code: str, timestamp: float) -> tuple[bytes, int]:
    if not 12 <= len(password) <= 128:
        raise InvalidAccount
    try:
        secret = decode_totp_seed(seed)
    except ValueError:
        raise InvalidAccount from None
    step = verify_totp(secret, code, timestamp)
    if step is None:
        raise InvalidAccount
    return secret, step


class Auth:
    def __init__(
        self, store: Store, *, clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.clock = clock
        self.monotonic = monotonic
        self._unknown_password = PasswordHash.make(new_token())

    def bootstrap_admin(self, username: str, password: str, seed: str, code: str) -> None:
        with self.store.locked():
            if self.store.accounts():
                raise AccessDenied
            if not USERNAME.fullmatch(username):
                raise InvalidAccount
            timestamp = self.clock()
            secret, step = _binding(password, seed, code, timestamp)
            self.store.save_account(Account(username, Role.ADMIN, PasswordHash.make(password), secret, step))
            self.store.append_audit(AuditEvent(timestamp, AuditAction.ACCOUNT_CREATED, staff_target=username))

    def inspect_accounts(self, token: str) -> tuple[Session, tuple[AccountStatus, ...]]:
        with self.store.locked():
            now = self.monotonic()
            session = self._require_session(token, now, role=Role.ADMIN)
            accounts = tuple(AccountStatus(account.username, account.role, account.enabled,
                                           self.store.failures(account.username, now).count >= FAILURE_LIMIT,
                                           account.setup is not None)
                             for account in sorted(self.store.accounts(), key=lambda item: item.username))
            return session, accounts

    def manage_account(
        self, token: str, csrf: str, action: AccountAction, username: str, role: str,
    ) -> str | None:
        with self.store.locked():
            now = self.monotonic()
            session = self._require_session(token, now, role=Role.ADMIN, csrf=csrf)
            account = self.store.account(username)
            try:
                setup_code = self._manage_account(session, action, account, username, role, now)
            except InvalidAccount as error:
                rejection = error
                self.store.append_audit(AuditEvent(self.clock(), ACCOUNT_ACTIONS[action], session.username,
                                                   result=AuditResult.DENIED,
                                                   staff_target=account.username if account else None))
            else:
                self.store.append_audit(AuditEvent(self.clock(), ACCOUNT_ACTIONS[action], session.username,
                                                   staff_target=username))
                return setup_code
        raise rejection

    def _manage_account(
        self, session: Session, action: AccountAction, account: Account | None, username: str, role: str, now: float,
    ) -> str | None:
        if action == AccountAction.CREATE:
            if account is not None or not USERNAME.fullmatch(username) or role not in Role:
                raise InvalidAccount
            account = Account(username, Role(role))
        elif account is None or not account.enabled or account.username == session.username:
            raise InvalidAccount
        if action in (AccountAction.CREATE, AccountAction.REBIND):
            setup_code = new_token()
            grant = SetupGrant(token_digest(setup_code), now + SETUP_LIFETIME)
            self.store.save_account(replace(account, totp_seed=None, last_totp_step=-1, setup=grant))
            self.store.revoke_staff_sessions(username)
            return setup_code
        if action == AccountAction.UNLOCK:
            self.store.save_failures(username, Failures())
        elif action == AccountAction.DISABLE:
            self.store.save_account(replace(account, enabled=False, setup=None))
            self.store.revoke_staff_sessions(username)
        else:
            if role not in Role:
                raise InvalidAccount
            self.store.save_account(replace(account, role=Role(role)))
            self.store.revoke_staff_sessions(username)
        return None

    def bind_account(self, username: str, setup_code: str, password: str, seed: str, code: str) -> bool:
        with self.store.locked():
            now = self.monotonic()
            timestamp = self.clock()
            account = self.store.account(username)
            actor = account.username if account else None
            allowed = self.store.allow_login_attempt(now, window=RATE_WINDOW, limit=RATE_LIMIT)
            if allowed and account and account.enabled and account.setup and TOKEN.fullmatch(setup_code):
                grant = account.setup
                if now < grant.expires_at and hmac.compare_digest(grant.digest, token_digest(setup_code)):
                    try:
                        bound_seed, step = _binding(password, seed, code, timestamp)
                    except InvalidAccount:
                        pass
                    else:
                        if account.password is None or account.password.matches(password):
                            digest = account.password or PasswordHash.make(password)
                            self.store.save_account(replace(account, password=digest, totp_seed=bound_seed,
                                                            last_totp_step=step, setup=None))
                            self.store.save_failures(username, Failures())
                            self.store.append_audit(AuditEvent(timestamp, AuditAction.TOTP_BOUND, actor))
                            return True
            self.store.append_audit(AuditEvent(timestamp, AuditAction.TOTP_BOUND, actor, result=AuditResult.DENIED))
            return False

    def login(self, username: str, password: str, code: str, *, previous_token: str = "") -> str | None:
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
            password_hash = account.password if account and account.password is not None else self._unknown_password
            matched = password_hash.matches(password)
            step = (verify_totp(account.totp_seed, code, timestamp, account.last_totp_step)
                    if account and account.enabled and account.totp_seed is not None and matched else None)
            if step is None:
                if account and account.enabled and account.totp_seed is not None:
                    self.store.save_failures(username, Failures(failures.count + 1, now + LOCKOUT))
                self.store.append_audit(AuditEvent(timestamp, AuditAction.LOGIN_FAILED, actor, result=AuditResult.DENIED))
                return None
            self.store.save_account(replace(account, last_totp_step=step))
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
