"""CJ-AUTH-READ-CONTEXT@0.1.0-rc.1: synchronous read lifetime, no storage/dispatch authority."""
import inspect
import threading
from collections.abc import Callable
from enum import Enum

from .admission import AdmissionChecker
from .interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal

READ_CONTEXT_VERSION = 'CJ-AUTH-READ-CONTEXT@0.1.0-rc.1'
_CONTEXT_CREATION_KEY = object()


class ReadViolationCode(Enum):
    INACTIVE = 'inactive'
    WRONG_THREAD = 'wrong_thread'
    REENTRY = 'reentry'
    CANCELLED = 'cancelled'
    IDENTITY_CHANGED = 'identity_changed'
    INVALID_CALLBACK = 'invalid_callback'
    INVALID_RESULT = 'invalid_result'
    RESULT_TOO_LARGE = 'result_too_large'


class ReadContextViolation(RuntimeError):
    def __init__(self, code: ReadViolationCode):
        super().__init__('protected read context unavailable')
        self.code = code


class ReadAdmissionFailure(RuntimeError):
    def __init__(self, status: AdmissionStatus, reason: AdmissionReason):
        super().__init__('protected read access unavailable')
        self.status, self.reason = status, reason


class ProtectedReadContext:
    """Host callback receives this object; do not construct/deserialize it from requests.

    A captured principal is a snapshot, not a permanent grant. require_current must
    surround the host's external callbacks; only the outer boundary returns bytes.
    """
    def __init__(self, checker: AdmissionChecker, token: str, *, _creation_key=None):
        if _creation_key is not _CONTEXT_CREATION_KEY:
            raise ValueError('read contexts must be created by ProtectedReadBoundary')
        self._checker, self._token = checker, token
        self._thread = threading.get_ident()
        self._lock = threading.RLock()
        self._active, self._checking = True, False
        self._principal = None
        self._failure = None

    def __repr__(self): return '<protected read context>'

    def _fail_locked(self, failure):
        if self._failure is None: self._failure = failure
        self._active = False
        return self._failure

    def _ensure_alive_locked(self):
        if not self._active:
            raise self._failure or ReadContextViolation(ReadViolationCode.INACTIVE)
        if threading.get_ident() != self._thread:
            raise self._fail_locked(ReadContextViolation(ReadViolationCode.WRONG_THREAD))

    @property
    def principal(self) -> TrustedPrincipal:
        with self._lock:
            self._ensure_alive_locked()
            if self._checking:
                raise self._fail_locked(ReadContextViolation(ReadViolationCode.REENTRY))
            if self._principal is None:
                raise self._fail_locked(ReadContextViolation(ReadViolationCode.INACTIVE))
            return self._principal

    def require_current(self) -> None:
        with self._lock:
            self._ensure_alive_locked()
            if self._checking:
                raise self._fail_locked(ReadContextViolation(ReadViolationCode.REENTRY))
            self._checking = True
        try:
            decision = self._checker.check(self._token)
        except Exception:
            decision = AdmissionDecision(AdmissionStatus.UNKNOWN, AdmissionReason.IDENTITY_UNKNOWN)
        except BaseException:
            with self._lock:
                self._checking = False
                self._fail_locked(ReadContextViolation(ReadViolationCode.CANCELLED))
            raise
        with self._lock:
            try:
                # A checker/provider callback may have invalidated/reentered this read.
                self._ensure_alive_locked()
                if (not isinstance(decision, AdmissionDecision)
                        or decision.status not in (AdmissionStatus.ALLOWED, AdmissionStatus.DENIED, AdmissionStatus.UNKNOWN)):
                    raise self._fail_locked(ReadAdmissionFailure(AdmissionStatus.UNKNOWN, AdmissionReason.IDENTITY_UNKNOWN))
                if decision.status is not AdmissionStatus.ALLOWED:
                    raise self._fail_locked(ReadAdmissionFailure(decision.status, decision.reason))
                if not isinstance(decision.principal, TrustedPrincipal):
                    raise self._fail_locked(ReadAdmissionFailure(AdmissionStatus.UNKNOWN, AdmissionReason.IDENTITY_UNKNOWN))
                if self._principal is None: self._principal = decision.principal
                elif decision.principal != self._principal:
                    raise self._fail_locked(ReadContextViolation(ReadViolationCode.IDENTITY_CHANGED))
            finally:
                self._checking = False

    def guard(self) -> None:
        self.require_current()

    def invalidate(self) -> None:
        """Abort only this read lifetime; never cancels/claims work or changes authority."""
        with self._lock:
            self._fail_locked(ReadContextViolation(ReadViolationCode.CANCELLED))

    def _reject_reentry(self):
        with self._lock:
            self._fail_locked(ReadContextViolation(ReadViolationCode.REENTRY))

    def _close(self):
        with self._lock:
            self._active = False
            self._token = None


class ProtectedReadBoundary:
    """One active callback per boundary. No process-wide fence or Python sandbox.

    Environment/budget period/repository resolver belong to trusted host composition,
    not this module. Checker and bounds are captured at construction, never request fields.
    """
    def __init__(self, checker: AdmissionChecker, *, max_response_bytes: int):
        if not isinstance(checker, AdmissionChecker): raise ValueError('canonical AdmissionChecker required')
        if type(max_response_bytes) is not int or max_response_bytes <= 0:
            raise ValueError('explicit positive byte bound required')
        self._checker, self._max_bytes = checker, max_response_bytes
        self._lock, self._active = threading.Lock(), None

    def with_read_context(self, token: str, callback: Callable[[ProtectedReadContext], bytes]) -> bytes:
        with self._lock:
            if self._active is not None:
                self._active._reject_reentry()
                raise ReadContextViolation(ReadViolationCode.REENTRY)
            context = ProtectedReadContext(self._checker, token, _creation_key=_CONTEXT_CREATION_KEY)
            self._active = context # claim before admission/provider callbacks can reenter
        try:
            if not callable(callback) or inspect.iscoroutinefunction(callback):
                raise ReadContextViolation(ReadViolationCode.INVALID_CALLBACK)
            context.require_current()
            result = callback(context)
            if type(result) is not bytes:
                if inspect.iscoroutine(result): result.close()
                raise ReadContextViolation(ReadViolationCode.INVALID_RESULT)
            if len(result) > self._max_bytes:
                raise ReadContextViolation(ReadViolationCode.RESULT_TOO_LARGE)
            context.require_current() # after projection/cleanup, immediately before private bytes escape
            return result
        finally:
            context._close()
            with self._lock:
                if self._active is context: self._active = None
