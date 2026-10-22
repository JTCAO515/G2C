"""RUN internal candidate. No authentication, provider, tools or network entry point."""
from dataclasses import dataclass, replace
from typing import Callable, ContextManager, Protocol


class Conflict(Exception):
    pass


class ResyncRequired(Exception):
    pass


class Denied(Exception):
    pass


TERMINAL = frozenset({'completed', 'failed', 'cancelled', 'context_invalid', 'unknown'})
KINDS = frozenset({'started', 'text_delta', 'effect_committed'}) | TERMINAL


@dataclass(frozen=True)
class Binding:
    # Internal trusted repository partition; never populated from public owner fields.
    scope: str
    conversation_id: str
    generation: str
    message_id: str
    run_id: str
    message_sequence: int

    def __post_init__(self):
        if any(type(x) is not str or not x.strip() for x in
               (self.scope, self.conversation_id, self.generation, self.message_id, self.run_id)):
            raise ValueError('explicit binding required')
        if type(self.message_sequence) is not int or self.message_sequence < 1:
            raise ValueError('positive sequence required')

    @property
    def chat(self):
        return self.scope, self.conversation_id, self.generation


@dataclass(frozen=True)
class Event:
    binding: Binding
    sequence: int
    event_id: str
    kind: str
    value: str = ''

    def __post_init__(self):
        if (type(self.binding) is not Binding or type(self.sequence) is not int or
                self.sequence < 1 or type(self.event_id) is not str or not self.event_id.strip()
                or self.kind not in KINDS or type(self.value) is not str):
            raise ValueError('unsupported event')
        if self.kind in {'text_delta', 'effect_committed'} and not self.value:
            raise ValueError('empty payload')
        if self.kind not in {'text_delta', 'effect_committed'} and self.value:
            raise ValueError('status events have no payload')


@dataclass(frozen=True)
class State:
    binding: Binding
    status: str = 'queued'
    events: tuple[Event, ...] = ()
    text: str = ''
    effects: tuple[str, ...] = ()

    @property
    def sequence(self):
        return len(self.events)


def advance(state: State, event: Event, valid: Callable[[Binding], bool]) -> State:
    """Caller holds transactional run/chat fence. No mutation on rejected input."""
    if event.binding != state.binding:
        raise Conflict('binding changed')
    for old in state.events:
        if old.event_id == event.event_id or old.sequence == event.sequence:
            if old == event:
                return state
            raise Conflict('event identity reused')
    if event.sequence != state.sequence + 1:
        raise ResyncRequired('gap or out of order')
    if state.status in TERMINAL:
        raise Conflict('terminal run')
    # Failure/cancel remain possible after authority/context loss. These do not publish output.
    if event.kind not in {'cancelled', 'failed', 'context_invalid', 'unknown'}:
        if valid(state.binding) is not True:
            raise Denied('context invalid or unknown')
    if state.status == 'queued' and event.kind not in {'started', 'cancelled', 'failed', 'context_invalid'}:
        raise Conflict('not started')
    if state.status == 'running' and event.kind == 'started':
        raise Conflict('already started')
    effects = state.effects
    if event.kind == 'effect_committed':
        if event.value in effects:
            raise Conflict('effect requires original event replay')
        effects += (event.value,)
    return replace(state, events=state.events + (event,),
                   status='running' if event.kind == 'started' else
                   event.kind if event.kind in TERMINAL else state.status,
                   text=state.text + event.value if event.kind == 'text_delta' else state.text,
                   effects=effects)


@dataclass(frozen=True)
class Cursor:
    binding: Binding
    epoch: str
    through: int
    after: int


def page(state: State, epoch: str, cursor: Cursor, limit: int):
    """Internal cursor only; public token authentication is an unimplemented API concern."""
    if (type(limit) is not int or limit < 1 or type(cursor) is not Cursor or
            cursor.binding != state.binding or cursor.epoch != epoch or
            type(cursor.after) is not int or type(cursor.through) is not int or
            not 0 <= cursor.after <= cursor.through <= state.sequence):
        raise ResyncRequired('invalid or expired cursor')
    rows = state.events[cursor.after:min(cursor.after + limit, cursor.through)]
    if any(e.sequence != cursor.after + i + 1 for i, e in enumerate(rows)):
        raise ResyncRequired('missing event')
    after = cursor.after + len(rows)
    return rows, replace(cursor, after=after) if after < cursor.through else None


class Transaction(Protocol):
    def accept(self, binding: Binding) -> State: ...
    def get(self, binding: Binding) -> State: ...
    def put(self, state: State) -> None: ...
    def previous_terminal(self, binding: Binding) -> bool: ...


class Repository(Protocol):
    # Implementations must atomically fence scope/chat and run, rollback on exception,
    # and return only after durable commit. Unknown commit => query original binding.
    def transaction(self) -> ContextManager[Transaction]: ...


class Service:
    def __init__(self, repository: Repository, valid=None):
        self.repository = repository
        self.valid = valid or (lambda _: False)

    def accept(self, binding):
        with self.repository.transaction() as tx:
            state = tx.accept(binding)
        return state

    def apply(self, event):
        with self.repository.transaction() as tx:
            old = tx.get(event.binding)
            if event.kind == 'started' and not tx.previous_terminal(event.binding):
                raise Conflict('earlier message unfinished or missing')
            state = advance(old, event, self.valid)
            tx.put(state)
        return state

    def snapshot(self, binding):
        with self.repository.transaction() as tx:
            state = tx.get(binding)
        return state

    def dispatch(self, *args, **kwargs):
        # Deliberately no enable switch until AUTH/MESSAGE/USAGE consumption is fixed.
        raise Denied('dispatch disabled; no authenticated quota/context integration')
