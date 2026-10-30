"""Internal consumer of CJ007's fixed interface. No JWT implementation or routes."""
from contextlib import contextmanager
import inspect
import hashlib
import threading
from contextvars import ContextVar
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import INTERFACE_VERSION, AdmissionStatus, TrustedPrincipal
from .domain import Service, Stored, Receipt, Command, InvalidInput, Unavailable

EXPECTED_AUTH = 'CJ-AUTH-SERVER@0.1.0-rc.1'
_HISTORY_CONTEXT_FACTORY = object()
_ACTIVE_HISTORY_CONTEXT = ContextVar("cj_message_history_context", default=None)


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
        self._thread = threading.current_thread()

    def _check(self):
        if (not self._active or threading.current_thread() is not self._thread
                or _ACTIVE_HISTORY_CONTEXT.get() is not self):
            raise RuntimeError('history context expired')

    @property
    def principal(self):
        self._check()
        return self._principal

    @property
    def scope(self):
        self._check()
        return self._scope

    def query_message(self, message_id: str) -> Stored | None:
        """Current scoped receipt + original input; never a RUN completion assertion."""
        self._check()
        if type(message_id) is not str or not message_id.strip():
            raise InvalidInput('message ID required')
        stored = self._service.query(message_id)
        self._check()
        if stored is None:
            return None
        if type(stored) is not Stored or type(stored.receipt) is not Receipt:
            raise Unavailable()
        try:
            command = Command.parse_stored(stored.raw)
        except InvalidInput:
            raise Unavailable() from None
        receipt = stored.receipt
        if (command.message_id != message_id or receipt.message_id != message_id
                or command.conversation_id != receipt.conversation_id
                or hashlib.sha256(stored.raw).hexdigest() != receipt.input_sha256
                or type(receipt.sequence) is not int or receipt.sequence < 1
                or type(receipt.generation) is not str or not receipt.generation.strip()
                or type(receipt.run_id) is not str or not receipt.run_id.strip()):
            raise Unavailable()
        return stored

    def conversations(self, cursor=None, limit=20):
        self._check()
        return self._service.conversations(cursor, limit)

    def send_status(self, conversation_id, message_id=None):
        self._check()
        result = self._service.send_status(conversation_id, message_id)
        self._check()
        if result.stored is not None:
            stored = result.stored
            try:
                command = Command.parse_stored(stored.raw)
            except InvalidInput:
                raise Unavailable() from None
            if (stored.receipt.message_id != message_id or command.message_id != message_id
                    or stored.receipt.conversation_id != conversation_id
                    or command.conversation_id != conversation_id
                    or hashlib.sha256(stored.raw).hexdigest() != stored.receipt.input_sha256):
                raise Unavailable()
        return result

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
    def __init__(self, checker, resolve_repository, new_run_id, *, resolve_travel_repository=None):
        if INTERFACE_VERSION != EXPECTED_AUTH or not isinstance(checker, AdmissionChecker):
            raise ValueError('fixed AUTH interface required')
        self.checker = checker
        self.resolve_repository = resolve_repository
        self.new_run_id = new_run_id
        self.resolve_travel_repository = resolve_travel_repository

    def _bind(self, token, *, travel=False):
        first = self.checker.check(token)
        if first.status is not AdmissionStatus.ALLOWED:
            raise AccessBlocked(first, 'entry')
        if not isinstance(first.principal, TrustedPrincipal):
            raise ValueError('AUTH allowed result missing principal')
        resolver = self.resolve_travel_repository if travel else self.resolve_repository
        if resolver is None:
            raise Unavailable('travel identity composition unavailable')
        repository = resolver(first.principal)
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
        if _ACTIVE_HISTORY_CONTEXT.get() is not None:
            raise RuntimeError('nested history context unavailable')
        # Reserve entry before invoking injected checker/resolver callbacks as well.
        active_token = _ACTIVE_HISTORY_CONTEXT.set(_HISTORY_CONTEXT_FACTORY)
        context = None
        try:
            service, principal, scope, guard = self._bind(token)
            context = HistoryReadContext(principal, scope, service, _factory=_HISTORY_CONTEXT_FACTORY)
            _ACTIVE_HISTORY_CONTEXT.set(context)
            guard('transaction')  # resolver/codec boundary; same captured principal
            result = operation(context)
            if result is context or inspect.isawaitable(result) or inspect.isgenerator(result) or inspect.isasyncgen(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError('history callback must return a materialized response')
            guard('return')  # after cursor encoding/projection, before publication
            return result
        finally:
            if context is not None:
                context._active = False
            _ACTIVE_HISTORY_CONTEXT.reset(active_token)

    def receive(self, token, raw):
        return self._service(token).receive(raw)

    def travel_action(self, token, raw):
        from .travel import Service as TravelService
        return TravelService(self._bind(token, travel=True)[0].repository).apply(raw)

    def travel_action_status(self, token, action_id):
        from .travel import Service as TravelService
        return TravelService(self._bind(token, travel=True)[0].repository).query_action(action_id)

    def travel_context(self, token, context_id):
        from .travel import Service as TravelService
        return TravelService(self._bind(token, travel=True)[0].repository).get(context_id)

    def query(self, token, message_id):
        return self._service(token).query(message_id)

    def open_conversation(self, token, conversation_id):
        return self._service(token).open_conversation(conversation_id)

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
