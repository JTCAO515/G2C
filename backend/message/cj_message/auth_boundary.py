"""Internal consumer of CJ007's fixed interface. No JWT implementation or routes."""
from contextlib import contextmanager
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import INTERFACE_VERSION, AdmissionStatus, TrustedPrincipal
from .domain import Service

EXPECTED_AUTH = 'CJ-AUTH-SERVER@0.1.0-rc.1'


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

    def _service(self, token):
        first = self.checker.check(token)
        if first.status is not AdmissionStatus.ALLOWED:
            raise AccessBlocked(first, 'entry')
        if not isinstance(first.principal, TrustedPrincipal):
            raise ValueError('AUTH allowed result missing principal')
        repository = self.resolve_repository(first.principal)

        def guard(stage):
            current = self.checker.check(token)
            if current.status is not AdmissionStatus.ALLOWED:
                raise AccessBlocked(current, stage)
            if current.principal != first.principal:
                # Do not accept an identity replacement even if it independently passes.
                raise IdentityChanged(stage)

        class GuardedRepository:
            scope = repository.scope

            @contextmanager
            def transaction(self):
                with repository.transaction() as tx:
                    guard('transaction')
                    yield tx
                    guard('commit')
                guard('return')

        return Service(GuardedRepository(), self.new_run_id)

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
