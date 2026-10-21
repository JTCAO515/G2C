"""Restricted-business admission, invoked afresh at each authoritative boundary."""
import time
from collections.abc import Callable
from .interfaces import (
    AdmissionDecision, AdmissionReason as R, AdmissionStatus as S,
    CJAccessFacts, CJAccessProvider, Fact, JWTVerifier, VerificationResult, VerificationStatus as V,
)


class AdmissionChecker:
    def __init__(self, verifier: JWTVerifier, access: CJAccessProvider | None = None,
                 *, clock: Callable[[], float] = time.time):
        self._verifier, self._access, self._clock = verifier, access, clock

    def check(self, token: str) -> AdmissionDecision:
        try:
            result = self._verifier.verify(token)
        except Exception:
            return AdmissionDecision(S.UNKNOWN, R.IDENTITY_UNKNOWN)
        if not isinstance(result, VerificationResult) or result.status is V.UNKNOWN:
            return AdmissionDecision(S.UNKNOWN, R.IDENTITY_UNKNOWN)
        if result.status is V.INVALID:
            return AdmissionDecision(S.DENIED, R.IDENTITY_INVALID)
        principal = result.principal
        if self._access is None:
            return AdmissionDecision(S.UNKNOWN, R.FACTS_UNKNOWN)
        try:
            facts = self._access.evaluate(principal)
            now = self._clock()
        except Exception:
            return AdmissionDecision(S.UNKNOWN, R.FACTS_UNKNOWN)
        # A slow policy lookup must not extend an expired identity.
        if now >= principal.expires_at or now < principal.not_before:
            return AdmissionDecision(S.DENIED, R.IDENTITY_INVALID)
        if (not isinstance(facts, CJAccessFacts) or facts.principal != principal
                or any(not isinstance(f, Fact) or f is Fact.UNKNOWN
                       for f in (facts.member, facts.email_verified, facts.invited))):
            return AdmissionDecision(S.UNKNOWN, R.FACTS_UNKNOWN)
        for fact, reason in ((facts.member, R.NOT_CJ_MEMBER),
                             (facts.email_verified, R.EMAIL_UNVERIFIED), (facts.invited, R.NOT_INVITED)):
            if fact is Fact.NO:
                return AdmissionDecision(S.DENIED, reason)
        return AdmissionDecision(S.ALLOWED, R.ACCEPTED, principal)
