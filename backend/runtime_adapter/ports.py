"""Trusted B composition seam. Implementations must keep B's original guards.

No adapter callback may mint identity, bootstrap state, bypass a registration,
reserve in a second fee ledger, or interpret a model reply as execution proof.
"""
from dataclasses import dataclass, field
from typing import Protocol

from .contract import Binding


@dataclass(frozen=True)
class PreparedOriginal:
    """One-use B capability; never serialized, minted or reconstructed by G."""
    fresh: bool
    capability: object = field(repr=False)


class RuntimeBackend(Protocol):
    def binding(self) -> Binding:
        """Resolve the current original authenticated context, not cached ALLOWED."""
        ...

    def pins(self) -> bytes:
        """Read actual process/image/model/prompt/tool pins as canonical JSON."""
        ...

    def require(self, *, binding: Binding, pins_sha256: str, purpose: str,
                deadline: float, read_only: bool) -> None:
        """Original ownership/auth/cancel fence; for sends also B window and
        stricter original limits. Each underlying provider/tool send must still
        use RegisteredExit/MeteredDashScopeProvider/AuthorizationBudget guards.
        Query has no reserve/release/settlement or new login/session behavior.
        """
        ...

    def prepare_task(self, task: dict, language: str) -> None:
        """Read-only all-task setup/recipe availability check; no paid setup.
        Raise Unavailable when any required existing legal setup is absent.
        Do not populate observed state from task variants' expected fields.
        """
        ...

    def claim(self, request: bytes, *, deadline: float) -> PreparedOriginal:
        """Atomic original-ID admission in B's existing host. No provider send.
        Existing IDs return fresh=False even if G lost its local mapping. Absence
        from query is never a substitute for this canonical fresh claim. A lost
        claim ACK is UNKNOWN and not retried. No new financial ledger is allowed.
        """
        ...

    def dispatch(self, request: bytes, *, capability: object, deadline: float) -> None:
        """One original client operation. May lose ACK: G persists before entry.
        B performs only this registered primitive, with actual MESSAGE/RUN/action
        references. Root task setup includes all its metered preparatory calls.
        Reflection must use model.runtime_reflection.1 without write tools.
        No retry, alternate ID, route, account or ledger inside this method.
        """
        ...

    def inspect(self, attempt_id: str, step_id: str, *, deadline: float) -> bytes:
        """Protected read of the original client operation and exhaustive RUN
        provider/Meter inventory, including setup, failure, cancelled and memory
        model calls. Missing originals are UNKNOWN, never authority to resend.
        Return the evidence envelope documented in README.
        """
        ...

    def original(self, reference: str, *, deadline: float) -> bytes:
        """Read only a B-issued opaque original reference under the same current
        owner/authority lifetime. Never arbitrary URL/file fetch or SQL setup.
        """
        ...
