"""Existing AUTH admission consumer; no alternate identity or wire contract."""
from cj_auth.interfaces import AdmissionStatus, TrustedPrincipal
from .domain import Denied
from .postgres import Repository


class Boundary:
    def __init__(self, checker=None, resolve=None, confirm=None):
        self.checker, self.resolve, self.confirm = checker, resolve, confirm

    def _repository(self, token):
        if self.checker is None or self.resolve is None: raise Denied('AUTH unconfigured')
        first = self.checker.check(token)
        if first.status is not AdmissionStatus.ALLOWED or not isinstance(first.principal, TrustedPrincipal): raise Denied('AUTH denied or unknown')
        # Only trusted host maps verified principal + environment to connect/scope.
        connect, scope = self.resolve(first.principal)
        def guard(stage):
            current = self.checker.check(token)
            if current.status is not AdmissionStatus.ALLOWED or current.principal != first.principal:
                error = Denied('AUTH changed')
                error.commit_possible = stage == 'return'
                raise error
        return Repository(connect, scope, self.confirm, guard)

    def act(self, token, action): return self._repository(token).act(action)
    def query_action(self, token, action_id): return self._repository(token).query_action(action_id)
    def detail(self, token, trip_id): return self._repository(token).detail(trip_id)
    def list_trips(self, token, after='', limit=20): return self._repository(token).list_trips(after,limit)
