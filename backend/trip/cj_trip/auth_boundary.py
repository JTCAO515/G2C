"""Existing AUTH admission consumer; no alternate identity or wire contract."""
from cj_auth.interfaces import AdmissionStatus, TrustedPrincipal
from .domain import Denied
from .postgres import Repository


class Boundary:
    def __init__(self, checker=None, resolve=None, confirm=None, *, structured=False):
        self.checker, self.resolve, self.confirm = checker, resolve, confirm
        self.structured = structured

    def _bind(self, token):
        if self.checker is None or self.resolve is None: raise Denied('AUTH unconfigured')
        checker, resolve, confirm = self.checker, self.resolve, self.confirm
        structured = self.structured
        first = checker.check(token)
        if first.status is not AdmissionStatus.ALLOWED or not isinstance(first.principal, TrustedPrincipal): raise Denied('AUTH denied or unknown')
        # Only trusted host maps verified principal + environment to connect/scope.
        connect, scope = resolve(first.principal)
        def guard(stage):
            if (self.checker is not checker or self.resolve is not resolve
                    or self.confirm is not confirm or self.structured is not structured
                    or repository.structured is not structured or repository.scope != scope
                    or repository.connect is not connect or repository.confirm is not confirm):
                raise Denied('TRIP binding changed')
            current = checker.check(token)
            if (self.checker is not checker or self.resolve is not resolve
                    or self.confirm is not confirm or self.structured is not structured
                    or repository.structured is not structured or repository.scope != scope
                    or repository.connect is not connect or repository.confirm is not confirm):
                raise Denied('TRIP binding changed')
            if current.status is not AdmissionStatus.ALLOWED or current.principal != first.principal:
                error = Denied('AUTH changed')
                error.commit_possible = stage == 'return'
                raise error
        repository = (Repository(connect, scope, confirm, guard, structured=True) if structured
                      else Repository(connect, scope, confirm, guard))
        return repository, first.principal, guard

    def _repository(self, token):
        return self._bind(token)[0]

    def with_operation(self, token, operation):
        from .operation import with_operation
        return with_operation(self, token, operation)

    # Internal compatibility only: HTTP routes must use with_operation.

    def act(self, token, action): return self._repository(token).act(action)
    def proposal_detail(self, token, proposal_id): return self._repository(token).proposal_detail(proposal_id)
    def query_action(self, token, action_id): return self._repository(token).query_action(action_id)
    def detail(self, token, trip_id): return self._repository(token).detail(trip_id)
    def list_trips(self, token, after='', limit=20): return self._repository(token).list_trips(after,limit)
