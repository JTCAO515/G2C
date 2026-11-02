"""ACCOUNT-REVOCATION@1. Additive #27 local account/session invalidation boundary."""
from .admission import AdmissionChecker
from .interfaces import AdmissionDecision,AdmissionStatus,AdmissionReason,Fact
from dataclasses import replace


class AccountRevocationAccess:
    """Compose the canonical access facts with a fresh local retirement fence.

    A retired account is no longer a CJ member; other actual facts are preserved,
    never fabricated to turn an unknown provider result into success.
    """
    def __init__(self,base,revocations):self.base,self.revocations=base,revocations

    def evaluate(self,principal):
        facts=self.base.evaluate(principal)
        retired=self.revocations(principal)
        if retired is Fact.NO:return facts
        return replace(facts,member=Fact.NO if retired is Fact.YES else Fact.UNKNOWN)


class AccountRevocationChecker(AdmissionChecker):
    """Canonical verified identity/admission first, then fresh authoritative fence.

    The host supplies principal→revocation lookup. No caller subject/scope, token
    metadata membership, new identity source or progress credential is accepted.
    Ordinary routes never accept cleanup-purpose capabilities.
    """
    def __init__(self,verifier,access,revocations,*,clock):
        super().__init__(verifier,access,clock=clock)
        self.revocations=revocations

    def check(self,token):
        decision=super().check(token)
        if decision.status is not AdmissionStatus.ALLOWED:return decision
        try:
            retired=self.revocations(decision.principal)
            now=self._clock()
        except Exception:
            return AdmissionDecision(AdmissionStatus.UNKNOWN,AdmissionReason.FACTS_UNKNOWN)
        if retired is Fact.YES:
            return AdmissionDecision(AdmissionStatus.DENIED,AdmissionReason.NOT_CJ_MEMBER)
        if retired is not Fact.NO:
            return AdmissionDecision(AdmissionStatus.UNKNOWN,AdmissionReason.FACTS_UNKNOWN)
        principal=decision.principal
        if not principal.not_before<=now<principal.expires_at:
            return AdmissionDecision(AdmissionStatus.DENIED,AdmissionReason.IDENTITY_INVALID)
        return decision
