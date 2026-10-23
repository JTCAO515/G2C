"""CJ-AUTH-SESSION-BINDING@0.1.0-rc.1: verified session reference, never a permission grant."""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID
from .interfaces import (AdmissionDecision, AdmissionStatus, CJAccessFacts, Fact, JWTVerifier,
                         TrustedPrincipal, VerificationStatus)

SESSION_BINDING_VERSION = 'CJ-AUTH-SESSION-BINDING@0.1.0-rc.1'


@dataclass(frozen=True, repr=False)
class VerifiedSessionBinding:
    principal: TrustedPrincipal
    session_id: UUID

    def __post_init__(self):
        if not isinstance(self.principal, TrustedPrincipal) or not isinstance(self.session_id, UUID):
            raise ValueError('verified principal and canonical session UUID required')


@dataclass(frozen=True)
class SessionVerificationResult:
    status: VerificationStatus
    binding: VerifiedSessionBinding | None = None

    def __post_init__(self):
        if not isinstance(self.status, VerificationStatus): raise ValueError('invalid status')
        if self.status is VerificationStatus.VALID:
            if not isinstance(self.binding, VerifiedSessionBinding): raise ValueError('valid result requires binding')
        elif self.binding is not None:
            raise ValueError('non-valid result must not carry binding')


class SessionBindingVerifier(JWTVerifier, Protocol):
    def verify_session(self, token: str) -> SessionVerificationResult: ...


@dataclass(frozen=True)
class SessionAccessFacts:
    binding: VerifiedSessionBinding
    access: CJAccessFacts
    session_active: Fact


class SessionAccessProvider(Protocol):
    """One host-owned authoritative lookup of exact session + existing CJ access facts.

    Missing/stale/unknown session evidence must never become YES. No caller/session claim
    or JWT email/metadata substitutes for current server evidence.
    """
    def evaluate_session(self, binding: VerifiedSessionBinding) -> SessionAccessFacts: ...


@dataclass(frozen=True)
class SessionAdmissionResult:
    decision: AdmissionDecision
    binding: VerifiedSessionBinding | None = None

    def __post_init__(self):
        if not isinstance(self.decision, AdmissionDecision): raise ValueError('canonical decision required')
        if self.decision.status is AdmissionStatus.ALLOWED:
            if not isinstance(self.binding, VerifiedSessionBinding) or self.binding.principal != self.decision.principal:
                raise ValueError('allowed session decision requires matching binding')
        elif self.binding is not None:
            raise ValueError('blocked decision must not carry binding')
