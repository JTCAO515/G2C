"""Explicit session-aware extension of existing admission. No access provider/default grant."""
import time
import math
from .admission import AdmissionChecker, _decide_verified_access
from .interfaces import AdmissionDecision, AdmissionReason as R, AdmissionStatus as S, Fact, VerificationStatus as V
from .session_binding import (SessionBindingVerifier, SessionAccessProvider, SessionAccessFacts,
                              SessionVerificationResult, SessionAdmissionResult)


class SessionAdmissionChecker(AdmissionChecker):
    """check keeps the old result shape, so existing protected read lifetimes can consume it.

    check_session additionally exposes the exact allowed binding, not a new storage scope.
    Every invocation verifies token and re-queries current session/access; nothing is cached.
    """
    def __init__(self, verifier: SessionBindingVerifier, access: SessionAccessProvider | None = None,
                 *, clock=time.time):
        super().__init__(verifier, None, clock=clock)
        self._session_access = access

    def check(self, token: str) -> AdmissionDecision:
        return self.check_session(token).decision

    def check_session(self, token: str) -> SessionAdmissionResult:
        def blocked(status, reason): return SessionAdmissionResult(AdmissionDecision(status, reason))
        try:
            result = self._verifier.verify_session(token)
        except Exception:
            return blocked(S.UNKNOWN, R.IDENTITY_UNKNOWN)
        if not isinstance(result, SessionVerificationResult) or result.status is V.UNKNOWN:
            return blocked(S.UNKNOWN, R.IDENTITY_UNKNOWN)
        if result.status is V.INVALID:
            return blocked(S.DENIED, R.IDENTITY_INVALID)
        binding = result.binding
        if self._session_access is None:
            return blocked(S.UNKNOWN, R.FACTS_UNKNOWN)
        try:
            facts = self._session_access.evaluate_session(binding)
            now = self._clock()
        except Exception:
            return blocked(S.UNKNOWN, R.FACTS_UNKNOWN)
        if type(now) not in (int, float) or not math.isfinite(now):
            return blocked(S.UNKNOWN, R.FACTS_UNKNOWN)
        if (not isinstance(facts, SessionAccessFacts) or facts.binding != binding
                or not isinstance(facts.session_active, Fact) or facts.session_active is Fact.UNKNOWN):
            return blocked(S.UNKNOWN, R.FACTS_UNKNOWN)
        if facts.session_active is Fact.NO:
            return blocked(S.DENIED, R.IDENTITY_INVALID)
        # Reuse the original post-provider expiry/binding/membership/email/invitation rules.
        try:
            decision = _decide_verified_access(binding.principal, facts.access, now)
        except Exception:
            return blocked(S.UNKNOWN, R.FACTS_UNKNOWN)
        return SessionAdmissionResult(decision, binding if decision.status is S.ALLOWED else None)
