"""Trusted local MEMORY composition; no source registration or runtime defaults.

Fresh AUTH checks run through the producer public request-lifetime guard.
No atomic distributed account/database revocation guarantee is claimed.
"""
from dataclasses import dataclass
from .composition import CompositionUnavailable, _pinned_modules


class MemoryAccessBlocked(Exception):
    def __init__(self, decision=None, *, commit_possible=False):
        self.decision, self.commit_possible = decision, commit_possible


class MemorySourceRejected(Exception):
    pass


@dataclass(frozen=True)
class MemoryBinding:
    scope: str
    service: object


@dataclass(frozen=True)
class MemoryWireConfiguration:
    max_body_bytes: int
    max_page_limit: int
    max_private_response_bytes: int

    def __post_init__(self):
        for value, maximum in ((self.max_body_bytes, 32768), (self.max_page_limit, 100),
                               (self.max_private_response_bytes, (1 << 31) - 1)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise CompositionUnavailable('Explicit bounded memory configuration required')


class MemoryBoundary:
    def __init__(self, checker, resolve_binding, source_policy, modules):
        self.checker, self.resolve_binding = checker, resolve_binding
        self.source_policy, self.modules = source_policy, modules

    def invoke(self, token, kind, argument, project):
        from cj_auth.interfaces import AdmissionStatus, TrustedPrincipal
        domain = self.modules['cj_memory.domain']
        command = domain.Command.parse(argument) if kind == 'save' else None
        last_fault = None
        captured = None

        def resolve():
            nonlocal captured
            decision = self.checker.check(token)
            principal = decision.principal
            if (decision.status is not AdmissionStatus.ALLOWED
                    or type(principal) is not TrustedPrincipal
                    or captured is not None and principal != captured):
                raise MemoryAccessBlocked(decision)
            if captured is None:
                captured = principal
            binding = self.resolve_binding(principal)
            if (type(binding) is not MemoryBinding or type(binding.scope) is not str
                    or not binding.scope.strip() or type(binding.service) is not domain.Service):
                raise CompositionUnavailable('Explicit principal-bound public Memory Service required')
            return principal, binding

        _, binding = resolve()

        def guard(stage):
            nonlocal last_fault
            try:
                principal, fresh_binding = resolve()
                # Re-resolve the trusted host mapping at every authoritative stage.
                # Producer also compares this scope with its ACTUAL bound repository.
                if fresh_binding.scope != binding.scope:
                    raise MemoryAccessBlocked()
                if self.source_policy(principal, binding.scope, kind, command, argument, stage) is not True:
                    raise MemorySourceRejected()
                # Resolver and domain policy may have waited. Require current AUTH
                # again before giving this stage's existing TrustedPrincipal back.
                decision = self.checker.check(token)
                if decision.status is not AdmissionStatus.ALLOWED or decision.principal != captured:
                    raise MemoryAccessBlocked(decision)
                return decision.principal, binding.scope
            except Exception as exc:
                last_fault = exc
                raise

        def operation(context):
            if kind == 'save': value = context.save(argument)
            elif kind == 'query': value = context.query(argument)
            elif kind == 'detail': value = context.detail(argument)
            elif kind == 'groups': value = context.groups()
            elif kind == 'list': value = context.list_items(*argument)
            else: raise ValueError('Unsupported memory operation')
            return project(value)  # fully encoded bytes; no private object escapes

        try:
            return binding.service.with_operation(guard, operation)
        except self.modules['cj_memory.operation'].OperationWithheld as exc:
            if not exc.commit_possible and exc.stage in ('entry','transaction','transaction_ready'):
                if last_fault is not None: raise last_fault from None
            if kind != 'save' and not exc.commit_possible and last_fault is not None:
                raise last_fault from None
            # Precommit denial is not evidence about an earlier unknown same-ID
            # attempt. Preserve original action/reconcile even for this rollback.
            raise


def build_memory_boundary(*, environment, jwt_configuration, verification_keys,
                          access_provider, resolve_binding, source_policy):
    if (environment != 'local' or not callable(resolve_binding) or not callable(source_policy)
            or not callable(getattr(verification_keys, 'resolve', None))
            or not callable(getattr(access_provider, 'evaluate', None))):
        raise CompositionUnavailable('Explicit local memory AUTH/binding/source policy required')
    modules = _pinned_modules(manifest_name='memory_pins.json')
    auth = modules['cj_auth.jwt_adapter']
    if (not isinstance(jwt_configuration, auth.JWTConfiguration)
            or jwt_configuration.profile is not auth.JWTProfile.STRICT_V1):
        raise CompositionUnavailable('Fixed strict AUTH profile required')
    verifier = auth.PyJWTVerifier(jwt_configuration, verification_keys)
    checker = modules['cj_auth.admission'].AdmissionChecker(verifier, access_provider)
    return MemoryBoundary(checker, resolve_binding, source_policy, modules)


def create_memory_composed_app(*, configuration, **dependencies):
    if type(configuration) is not MemoryWireConfiguration:
        raise CompositionUnavailable('Explicit memory wire configuration required')
    boundary = build_memory_boundary(**dependencies)
    from .app import create_app
    return create_app(_memory_boundary=boundary, _memory_configuration=configuration)
