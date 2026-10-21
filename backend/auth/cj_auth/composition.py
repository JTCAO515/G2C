"""CJ-AUTH-COMPOSITION@0.1.0-rc.1: internal HTTP adapter, no route or network I/O."""
from dataclasses import dataclass
from .admission import AdmissionChecker
from .interfaces import AdmissionDecision, AdmissionReason as R, AdmissionStatus as S, CJAccessProvider
from .jwt_adapter import JWTConfiguration, KeyProvider, PyJWTVerifier

COMPOSITION_VERSION = 'CJ-AUTH-COMPOSITION@0.1.0-rc.1'


@dataclass(frozen=True)
class ErrorSemantics:
    outcome: str
    recovery: str
    message_en: str
    message_zh: str


@dataclass(frozen=True)
class BoundaryResult:
    decision: AdmissionDecision
    http_status_hint: int | None
    error: ErrorSemantics | None


def map_admission(decision: AdmissionDecision) -> BoundaryResult:
    """Entry-only mapping, before side effects; never overwrite a commit-possible outcome."""
    if decision.status is S.ALLOWED:
        return BoundaryResult(decision, None, None)
    if decision.status is S.UNKNOWN:
        return BoundaryResult(decision, 503, ErrorSemantics(
            'unknown', 'retry_safe_read', 'Unable to confirm access right now.', '暂时无法确认访问资格。'))
    if decision.reason is R.IDENTITY_INVALID:
        return BoundaryResult(decision, 401, ErrorSemantics(
            'failed', 'do_not_retry', 'Unable to verify this sign-in.', '无法验证此次登录。'))
    return BoundaryResult(decision, 403, ErrorSemantics(
        'failed', 'do_not_retry', 'This account cannot access this feature.', '当前账号无法使用此功能。'))


class AuthBoundary:
    """Host must reject multiple Authorization headers before passing one string.

    No request_id/code/category/WWW-Authenticate or response is invented here;
    the shared API owner must compose the final BASE response and trace metadata.
    """
    def __init__(self, checker: AdmissionChecker):
        self._checker = checker

    def authorize(self, authorization: str | None) -> BoundaryResult:
        if not isinstance(authorization, str):
            return map_admission(AdmissionDecision(S.DENIED, R.IDENTITY_INVALID))
        parts = authorization.split(' ')
        if (len(parts) != 2 or parts[0].lower() != 'bearer' or not parts[1]
                or any(c.isspace() or c == ',' for c in parts[1])):
            return map_admission(AdmissionDecision(S.DENIED, R.IDENTITY_INVALID))
        return map_admission(self._checker.check(parts[1]))


def build_auth(*, configuration: JWTConfiguration | None,
               keys: KeyProvider | None, access: CJAccessProvider | None) -> AuthBoundary:
    """All composition dependencies explicit. None yields a closed/unknown path, not defaults."""
    return AuthBoundary(AdmissionChecker(PyJWTVerifier(configuration, keys), access))
