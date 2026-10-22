"""Internal whitelist read. NOT an authenticated API or caller-selected scope.

Trusted server composition must resolve the repository and original full Binding
inside the MESSAGE-owned protected context, and guard identity/ownership again
before publishing the materialized result. This module grants no authority.
"""
from dataclasses import dataclass
from .core import Binding, Event, State, Repository, TERMINAL, Conflict, ResyncRequired


@dataclass(frozen=True)
class RunDiagnostic:
    binding: Binding
    status: str
    event_highwater: int


def read_diagnostic(repository: Repository, binding: Binding) -> RunDiagnostic:
    """Return only original references, read-time status and event highwater.

    Missing, expired, denied, corrupt, cancelled reads and uncertain transaction
    completion propagate. There is no nullable-success fallback or retry here.
    A cancelled RUN is a valid status, distinct from cancellation of this read.
    """
    if type(binding) is not Binding:
        raise ValueError('complete original internal Binding required')
    with repository.transaction() as tx:
        state = tx.get(binding)  # Existing adapter checks exact scope/ref/active/expiry.
        if type(state) is not State or state.binding != binding:
            raise Conflict('original run binding unavailable')
        if type(state.status) is not str or state.status not in TERMINAL | {'queued', 'running'}:
            raise ResyncRequired('unknown run status')
        if type(state.events) is not tuple:
            raise ResyncRequired('invalid event boundary')
        for sequence, event in enumerate(state.events, 1):
            if type(event) is not Event or event.binding != binding or event.sequence != sequence:
                raise ResyncRequired('invalid event boundary')
        # Construct by allowlist, never asdict(State), __dict__, event payload or UsageBinding.
        result = RunDiagnostic(binding, state.status, len(state.events))
    return result  # Transaction/guard failure must withhold this result.
