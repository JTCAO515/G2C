"""Server-issued review binding; issuance never accepts or changes a Trip.

The trusted host supplies a dedicated key. No key generation, environment lookup,
credential persistence or account policy lives here. Clients must retain the exact
prepared action and reconcile it after unknown outcomes, never mint a replacement.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import math
import re
import time

from .domain import Action, Conflict, Denied, ProposalDetail, identifier, packed


@dataclass(frozen=True, repr=False)
class PreparedConfirmation:
    action: Action
    expires_at: int


@dataclass(frozen=True, repr=False)
class ConfirmationSigner:
    key: bytes = field(repr=False)
    lifetime_seconds: int = 300
    clock: object = field(default=time.time, repr=False, compare=False)

    def __post_init__(self):
        if (type(self.key) is not bytes or len(self.key) < 32
                or type(self.lifetime_seconds) is not int or not 1 <= self.lifetime_seconds <= 600
                or not callable(self.clock)):
            raise ValueError('dedicated key, bounded lifetime and clock required')

    def _now(self):
        value = self.clock()
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise Denied('confirmation clock unavailable')
        return value

    def _mac(self, scope, action, proposal, expires_at):
        payload = packed(['trip-confirmation-v1', scope, action.action_id, action.kind,
                          proposal.proposal_id, action.candidate_hash, proposal.expected_version, expires_at])
        return hmac.new(self.key, payload, hashlib.sha256).hexdigest()

    def issue(self, scope, detail, *, action_id, kind, candidate_hash):
        """Called inside the authenticated TRIP operation, using its canonical proposal."""
        identifier(scope)
        if type(detail) is not ProposalDetail:
            raise ValueError('canonical proposal detail required')
        proposal = detail.proposal
        action = Action(action_id, kind, proposal.proposal_id, candidate_hash, 'pending')
        if (detail.status != 'pending' or detail.candidate_hash != proposal.digest(scope)
                or candidate_hash != detail.candidate_hash):
            raise Conflict('candidate changed or unavailable')
        now = self._now()
        expires_at = min(proposal.expires_at, int(now) + self.lifetime_seconds)
        if expires_at <= now:
            raise Conflict('candidate expired')
        ref = f'tc1.{expires_at}.{self._mac(scope, action, proposal, expires_at)}'
        return PreparedConfirmation(Action(action_id, kind, proposal.proposal_id, candidate_hash, ref), expires_at)

    def __call__(self, scope, action, proposal):
        return self._valid_at(scope, action, proposal, self._now())

    def _valid_at(self, scope, action, proposal, now):
        identifier(scope)
        match = re.fullmatch(r'tc1\.([1-9][0-9]{0,11})\.([0-9a-f]{64})', action.confirmation_ref)
        if match is None:
            return False
        expires_at = int(match[1])
        if (not now < expires_at <= proposal.expires_at
                or action.proposal_id != proposal.proposal_id
                or action.candidate_hash != proposal.digest(scope)):
            return False
        return hmac.compare_digest(match[2], self._mac(scope, action, proposal, expires_at))

    def check_before_commit(self, scope, action, proposal, database_now):
        """Recheck after the final AUTH guard, while the existing scope lock is held."""
        if self._valid_at(scope, action, proposal, database_now) is not True:
            raise Denied('confirmation expired or changed before commit')
