"""AUTH-draft.1 synthetic semantics ONLY. No credential verifier or runtime adapter."""
from __future__ import annotations

from dataclasses import dataclass, field


def server_decision(verdict, resource_owners, caller_owner=None):
    """verdict is test authority output, NEVER an untrusted request payload.

    caller_owner intentionally cannot grant rights. Call again at a boundary;
    a previous allow is not a durable authorization capability.
    """
    if verdict['environment'] != 'synthetic-new-cj':
        return 'identity_denied'
    if verdict['identity'] == 'unknown':
        return 'identity_unknown'
    if verdict['identity'] != 'valid' or not verdict['principal']:
        return 'identity_denied'
    if verdict['session'] != 'current':
        return 'session_denied'
    if verdict['eligibility'] == 'unknown':
        return 'eligibility_unknown'
    if verdict['eligibility'] != 'allowed':
        return 'eligibility_denied'
    if any(owner != verdict['principal'] for owner in resource_owners):
        return 'resource_denied'
    return 'allow'


@dataclass
class Client:
    # Test harness supplies a different instance identity on every restart.
    instance: str
    generation: int = 0
    operation: int = 0
    pending: tuple | None = None
    principal: str | None = None
    revision: str | None = None
    state: str = 'anonymous'
    credentials_present: bool = False
    visible: list = field(default_factory=list)
    remote_logout: str = 'not_requested'

    def _clear(self):
        self.generation += 1
        self.pending = None
        self.principal = self.revision = None
        self.credentials_present = False
        self.visible.clear()

    def begin(self, new_login=False):
        if new_login:
            self._clear()
        self.operation += 1
        self.pending = (self.instance, self.generation, self.operation)
        self.state = 'checking'
        self.visible.clear()
        return self.pending

    def complete(self, ticket, result, principal=None, revision=None,
                 eligibility='unknown'):
        if ticket != self.pending or self.pending is None:
            return False
        if result not in ('valid', 'invalid', 'unknown'):
            raise ValueError('unsupported synthetic identity outcome')
        if result == 'valid' and (not principal or not revision or eligibility not in
                                  ('allowed', 'denied', 'unknown')):
            raise ValueError('incomplete synthetic authority result')
        self.pending = None  # duplicate callbacks are consumed exactly once
        if result == 'invalid':
            self._clear()
            self.state = 'invalid'
        elif result == 'unknown':
            self.state = 'unknown'  # retain credentials; never claim invalid
        else:
            # A restore/refresh cannot silently switch an already bound account.
            if self.principal is not None and self.principal != principal:
                self.state = 'unknown'
                return False
            self.principal, self.revision = principal, revision
            self.credentials_present = True
            self.state = {'allowed': 'eligible', 'denied': 'restricted',
                          'unknown': 'eligibility_unknown'}[eligibility]
        return True

    def logout(self):
        self._clear()
        self.state = 'anonymous'
        self.remote_logout = 'unknown'

    def capture(self):
        if self.state != 'eligible':
            return None
        return (self.instance, self.generation, self.principal, self.revision)

    def deliver(self, binding, text):
        if binding is None or self.state != 'eligible' or binding != self.capture():
            return False
        self.visible.append(text)
        return True
