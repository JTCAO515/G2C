"""Observe CJ024's ORIGINAL reducer; never create an item-deletion protocol."""
from dataclasses import dataclass, replace

from cj_cleanup.core import Manifest, Operation, Scope, STATES, identifier, receipt, request
from cj_memory.domain import Unavailable

from .domain import Action, OriginalAction


@dataclass(frozen=True, repr=False)
class CleanupLink:
    """Trusted-host observation binding, not a capability or confirmation issuer.

    No real producer currently issues this binding for CJ021. In particular, an
    account-cleanup operation must NOT be created for a single-item withdrawal.
    """
    scope: Scope
    operation_id: str
    confirmation_digest: str
    manifest: Manifest
    memory_scope: str
    withdrawal_original_input: bytes


@dataclass(frozen=True)
class CleanupProgress:
    state: str
    manifest_digest: str
    # All steps remain visible even when one outcome takes reducer precedence.
    steps: tuple[tuple[str, str], ...]
    gaps: tuple[str, ...]


def observe_cleanup(operation, link):
    """Read only. No receipt import, intent, retry, storage mutation or hook call."""
    if type(operation) is not Operation or type(link) is not CleanupLink:
        raise Unavailable('original cleanup operation unavailable')
    Action.parse(link.withdrawal_original_input)
    if type(link.memory_scope) is not str or not link.memory_scope.strip():
        raise Unavailable('original memory binding unavailable')
    if (operation.scope, operation.operation_id, operation.confirmation_digest, operation.manifest) != (
            link.scope, link.operation_id, link.confirmation_digest, link.manifest):
        raise Unavailable('original cleanup binding mismatch')
    # Check the original full target shape. Never omit an account barrier or
    # manufacture a narrower manifest from the single visible item.
    template = request(operation.scope, operation.operation_id, operation.confirmation_digest,
                       operation.manifest, tuple(s.target for s in operation.steps if s.available))
    if tuple((s.target, s.version, s.available) for s in operation.steps) != tuple(
            (s.target, s.version, s.available) for s in template.steps):
        raise Unavailable('original cleanup target coverage mismatch')
    for step in operation.steps:
        if step.state not in STATES:
            raise Unavailable('invalid original cleanup state')
        if step.state == 'pending':
            if step.invocation is not None or step.receipt_bytes is not None:
                raise Unavailable('invalid pending cleanup observation')
            continue
        identifier(step.invocation)
        if not step.available or (step.state == 'in_progress' and step.receipt_bytes is not None):
            raise Unavailable('invalid original cleanup invocation')
        if step.receipt_bytes is None:
            if step.state not in ('in_progress', 'unknown'):
                raise Unavailable('original cleanup receipt missing')
            continue  # Original restart may produce unknown without a result.
        # Revalidate exact bytes via the original receipt decoder/reducer. A bare
        # confirmed flag, mismatched outcome, or terminal dataclass is not proof.
        baseline = replace(operation, steps=tuple(
            replace(s, state='in_progress', receipt_bytes=None) if s.target == step.target else s
            for s in operation.steps))
        checked = receipt(baseline, step.target, step.receipt_bytes)
        if next(s for s in checked.steps if s.target == step.target) != step:
            raise Unavailable('original cleanup receipt state mismatch')
    state = operation.status  # Single canonical reducer, including precedence.
    if state == 'complete':
        state = 'limited_complete'
    return CleanupProgress(state, operation.manifest.registry_digest,
                           tuple((s.target, s.state) for s in operation.steps),
                           operation.gaps + operation.manifest.gaps)


@dataclass(frozen=True)
class Progress:
    stop_use: str
    cleanup: CleanupProgress | None
    blockers: tuple[str, ...]

    @property
    def state(self):
        if self.stop_use == 'unknown':
            return 'unknown'
        if self.blockers:
            return 'blocked'
        return self.cleanup.state if self.cleanup else 'stopped'


# Fixed input has neither a withdrawal producer nor a per-item cleanup mapping.
# These cannot be cleared by caller booleans, digests, fabricated hooks or UI.
BLOCKERS = ('same_tx_withdrawal_history_retombstone_producer_missing',
            'item_cleanup_confirmation_and_hook_mapping_missing',
            'retained_chat_all_ingress_fence_integration_unverified')


def project(scope, original=None, *, cleanup=None, link=None):
    """Internal observation only; never report end-to-end deletion complete.

    A missing receipt means UNKNOWN, not failure or permission to resend. Even a
    synthetic valid withdrawn receipt proves no physical removal. CJ024 finite
    completion is displayed separately, bounded to its original frozen manifest.
    """
    stopped = 'unknown'
    if original is not None:
        if type(original) is not OriginalAction or original.scope != scope:
            raise Unavailable('original action unavailable')
        original.validate()
        stopped = 'stopped'
    if (cleanup is None) != (link is None):
        raise Unavailable('original cleanup binding unavailable')
    observed = observe_cleanup(cleanup, link) if cleanup is not None else None
    if link is not None and (link.memory_scope != scope or (
            original is not None and link.withdrawal_original_input != original.original_input)):
        raise Unavailable('cleanup-to-original-withdrawal binding mismatch')
    return Progress(stopped, observed, BLOCKERS)
