"""Synthetic atomic adapter only; NOT durable storage or a production authority."""
from contextlib import contextmanager
from threading import RLock
from .core import Binding, State, Conflict
from .usage_binding import UsageBinding


class MemoryRepository:
    def __init__(self):
        self.rows = {}
        self.lock = RLock()
        self.revision = 0

    @contextmanager
    def transaction(self):
        with self.lock:
            revision = self.revision
            def check_current():
                if revision != self.revision:
                    raise Conflict('repository changed during callback')
            tx = _Transaction(self.rows.copy(), check_current)
            yield tx
            # A nested transaction commits independently. Never roll it back when
            # an older callback/outer transaction fails or attempts a stale commit.
            if revision != self.revision:
                raise Conflict('repository changed during callback')
            if tx.rows != self.rows:
                self.rows = tx.rows
                self.revision += 1


class _Transaction:
    def __init__(self, rows, check_current):
        self.rows, self.check_current = rows, check_current

    def accept(self, binding: Binding, usage=None, require_new=False):
        self.check_current()
        if type(binding) is not Binding:
            raise ValueError('binding required')
        if usage is not None:
            if type(usage) is not UsageBinding:
                raise ValueError('usage binding required')
            usage.check_run(binding.run_id)
        for old in self.rows.values():
            b = old.binding
            if ((b.scope, b.run_id) == (binding.scope, binding.run_id) or
                (b.scope, b.message_id) == (binding.scope, binding.message_id) or
                (b.chat, b.message_sequence) == (binding.chat, binding.message_sequence)):
                if require_new or b != binding or (usage is not None and old.usage != usage):
                    raise Conflict('binding reuse')
                return old
        state = State(binding, usage=usage)
        self.put(state)
        return state

    def get(self, binding):
        # A reentrant committed cancel must be visible before caller-owned outflow,
        # not only rejected at this snapshot transaction's eventual commit.
        self.check_current()
        state = self.rows.get((binding.scope, binding.run_id))
        if state is None or state.binding != binding:
            raise Conflict('unavailable')
        return state

    def put(self, state):
        self.check_current()
        old = self.rows.get((state.binding.scope, state.binding.run_id))
        if old is not None and old.usage != state.usage:
            raise Conflict('immutable usage association')
        self.rows[state.binding.scope, state.binding.run_id] = state

    def previous_terminal(self, binding):
        self.check_current()
        from .core import TERMINAL
        predecessors = {s.binding.message_sequence: s for s in self.rows.values()
                        if s.binding.chat == binding.chat and
                        s.binding.message_sequence < binding.message_sequence}
        return (len(predecessors) == binding.message_sequence - 1 and
                all(s.status in TERMINAL - {'unknown'} for s in predecessors.values()))
