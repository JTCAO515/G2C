"""Internal consumer of CJ007's fixed interface. No JWT implementation or routes."""
from contextlib import contextmanager
import inspect
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import INTERFACE_VERSION, AdmissionStatus, TrustedPrincipal
from .domain import Service

EXPECTED_AUTH = 'CJ-AUTH-SERVER@0.1.0-rc.1'
_HISTORY_CONTEXT_FACTORY = object()


class AccessBlocked(Exception):
    def __init__(self, decision, stage):
        super().__init__('message access unavailable')
        self.status = decision.status
        self.reason = decision.reason
        self.stage = stage
        # A return-stage denial does not roll back the committed original action.
        self.commit_possible = stage == 'return'


class IdentityChanged(Exception):
    def __init__(self, stage):
        super().__init__('message identity changed')
        self.stage = stage
        self.commit_possible = stage == 'return'


class HistoryReadContext:
    """Server-only, callback-lifetime context; never constructed from a request/token payload.

    Exposes current trusted metadata for codec binding, not a new identity format.
    No write method or raw repository is exposed.
    """
    def __init__(self, principal, scope, service, *, _factory=None):
        if _factory is not _HISTORY_CONTEXT_FACTORY:
            raise TypeError('history context must be issued by Boundary')
        self._principal, self._scope, self._service = principal, scope, service
        self._active = True

    def _check(self):
        if not self._active:
            raise RuntimeError('history context expired')

    @property
    def principal(self):
        self._check()
        return self._principal

    @property
    def scope(self):
        self._check()
        return self._scope

    def conversations(self, cursor=None, limit=20):
        self._check()
        return self._service.conversations(cursor, limit)

    def message_history(self, conversation_id, cursor=None, limit=20):
        self._check()
        return self._service.message_history(conversation_id, cursor, limit)

    def read_draft(self, conversation_id, generation):
        self._check()
        return self._service.read_draft(conversation_id, generation)


class Boundary:
    """Server composition only. resolve_repository is a server-owned mapping.

    Mapping/provisioning policy is intentionally not guessed here. It must bind a
    verified TrustedPrincipal to a repository scoped to that identity/environment.
    Caller bodies cannot supply a repository, scope or principal.
    """
    def __init__(self, checker, resolve_repository, new_run_id):
        if INTERFACE_VERSION != EXPECTED_AUTH or not isinstance(checker, AdmissionChecker):
            raise ValueError('fixed AUTH interface required')
        self.checker = checker
        self.resolve_repository = resolve_repository
        self.new_run_id = new_run_id

    def _bind(self, token):
        first = self.checker.check(token)
        if first.status is not AdmissionStatus.ALLOWED:
            raise AccessBlocked(first, 'entry')
        if not isinstance(first.principal, TrustedPrincipal):
            raise ValueError('AUTH allowed result missing principal')
        repository = self.resolve_repository(first.principal)
        bound_scope = repository.scope

        def guard(stage):
            current = self.checker.check(token)
            if current.status is not AdmissionStatus.ALLOWED:
                raise AccessBlocked(current, stage)
            if current.principal != first.principal or repository.scope != bound_scope:
                # Do not accept an identity replacement even if it independently passes.
                raise IdentityChanged(stage)

        class GuardedRepository:
            scope = bound_scope

            @contextmanager
            def transaction(self):
                with repository.transaction() as tx:
                    guard('transaction')
                    yield tx
                    guard('commit')
                guard('return')

        return Service(GuardedRepository(), self.new_run_id), first.principal, bound_scope, guard

    def _service(self, token):
        return self._bind(token)[0]

    def with_history_context(self, token, operation):
        """Run synchronous codec/decode/read/encode/projection under one identity binding.

        Callback returns the fully materialized response, never a deferred iterator or
        context. Caller supplies trusted environment/codec policy separately; no new
        principal claims are invented here. Draft writes use save_draft, outside this seam.
        """
        service, principal, scope, guard = self._bind(token)
        context = HistoryReadContext(principal, scope, service, _factory=_HISTORY_CONTEXT_FACTORY)
        try:
            guard('transaction')  # resolver/codec boundary; same captured principal
            result = operation(context)
            if result is context or inspect.isawaitable(result) or inspect.isgenerator(result) or inspect.isasyncgen(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError('history callback must return a materialized response')
            guard('return')  # after cursor encoding/projection, before publication
            return result
        finally:
            context._active = False

    def receive(self, token, raw):
        return self._service(token).receive(raw)

    def query(self, token, message_id):
        return self._service(token).query(message_id)

    def page(self, token, conversation_id, cursor=None, limit=20):
        return self._service(token).page(conversation_id, cursor, limit)

    def pending(self, token, limit=20):
        # Internal read only, never a model-dispatch authorization receipt.
        return self._service(token).pending(limit)

    def conversations(self, token, cursor=None, limit=20):
        return self._service(token).conversations(cursor, limit)

    def message_history(self, token, conversation_id, cursor=None, limit=20):
        return self._service(token).message_history(conversation_id, cursor, limit)

    def read_draft(self, token, conversation_id, generation):
        return self._service(token).read_draft(conversation_id, generation)

    def save_draft(self, token, conversation_id, generation, original_utf8, expected_revision):
        return self._service(token).save_draft(conversation_id, generation, original_utf8, expected_revision)
