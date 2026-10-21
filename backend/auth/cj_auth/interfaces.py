"""CJ-AUTH-SERVER@0.1.0-rc.1: internal Python interface, not a wire contract."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

INTERFACE_VERSION = "CJ-AUTH-SERVER@0.1.0-rc.1"


class VerificationStatus(Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass(frozen=True, repr=False)
class TrustedPrincipal:
    issuer: str
    subject: str
    audience: str
    issued_at: int
    not_before: int
    expires_at: int


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    principal: TrustedPrincipal | None = None

    def __post_init__(self):
        if not isinstance(self.status, VerificationStatus):
            raise ValueError("invalid verification status")
        if self.status is VerificationStatus.VALID:
            if not isinstance(self.principal, TrustedPrincipal):
                raise ValueError("valid verification requires a trusted principal")
        elif self.principal is not None:
            raise ValueError("non-valid verification must not carry a principal")


class JWTVerifier(Protocol):
    def verify(self, token: str) -> VerificationResult: ...


class Fact(Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CJAccessFacts:
    principal: TrustedPrincipal
    member: Fact
    email_verified: Fact
    invited: Fact


class CJAccessProvider(Protocol):
    """Server-owned authoritative lookup, never token metadata or request owner/email."""
    def evaluate(self, principal: TrustedPrincipal) -> CJAccessFacts: ...


class AdmissionStatus(Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    UNKNOWN = "unknown"


class AdmissionReason(Enum):
    ACCEPTED = "accepted"
    IDENTITY_INVALID = "identity_invalid"
    IDENTITY_UNKNOWN = "identity_unknown"
    FACTS_UNKNOWN = "facts_unknown"
    NOT_CJ_MEMBER = "not_cj_member"
    EMAIL_UNVERIFIED = "email_unverified"
    NOT_INVITED = "not_invited"


@dataclass(frozen=True)
class AdmissionDecision:
    status: AdmissionStatus
    reason: AdmissionReason
    principal: TrustedPrincipal | None = None
