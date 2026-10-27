"""Host-side worker: MESSAGE pending deliveries -> RUN events via one model provider (P2a).

Runs inside the trusted host, already bound to one internal scope. It never takes
owner or scope from request data. Recovery rules (ADR-0003):

- a run found `running` after a restart is marked `unknown` and is NOT resent;
- a provider result that may have been processed is `unknown`, a definite rejection
  is `failed`; neither is retried automatically;
- a delivery is acknowledged only after RUN holds a terminal status.
"""
from dataclasses import dataclass
import json

from cj_run.core import Binding, Conflict, Event, TERMINAL

from .provider import ProviderFailed, ProviderUnknown

FLUSH_CHARS = 24


@dataclass(frozen=True)
class Outcome:
    message_id: str
    run_id: str
    status: str  # completed | failed | unknown | waiting | skipped


class RunWorker:
    def __init__(self, *, scope, messages, runs, provider):
        """`messages`: cj_message.domain.Service and `runs`: cj_run.core.Service, both bound to `scope`."""
        self.scope, self.messages, self.runs, self.provider = scope, messages, runs, provider

    def process(self, limit=20):
        outcomes = []
        blocked = set()  # conversations whose earlier message is not terminal yet
        for receipt in self.messages.pending(limit):
            if receipt.conversation_id in blocked:
                outcomes.append(Outcome(receipt.message_id, receipt.run_id, 'waiting'))
                continue
            outcome = self._one(receipt)
            if outcome.status == 'waiting':
                blocked.add(receipt.conversation_id)
            outcomes.append(outcome)
        return outcomes

    def _binding(self, receipt):
        return Binding(self.scope, receipt.conversation_id, receipt.generation,
                       receipt.message_id, receipt.run_id, receipt.sequence)

    def _event(self, binding, state, kind, value=''):
        sequence = state.sequence + 1
        return self.runs.apply(Event(binding, sequence, f'{binding.run_id}:{sequence}', kind, value))

    def _finish(self, receipt, state):
        if state.status in TERMINAL:
            self.messages.acknowledge(receipt)
        return Outcome(receipt.message_id, receipt.run_id, state.status)

    def _one(self, receipt):
        binding = self._binding(receipt)
        state = self.runs.accept(binding)
        if state.status in TERMINAL:
            return self._finish(receipt, state)
        if state.status == 'running':
            # Interrupted by a crash or restart: the provider may have billed or answered.
            return self._finish(receipt, self._event(binding, state, 'unknown'))
        try:
            state = self._event(binding, state, 'started')
        except Conflict:
            return Outcome(receipt.message_id, receipt.run_id, 'waiting')
        stored = self.messages.query(receipt.message_id)
        text = json.loads(stored.raw)['text']
        buffer = ''
        try:
            for chunk in self.provider.stream([{'role': 'user', 'content': text}]):
                buffer += chunk
                if len(buffer) >= FLUSH_CHARS:
                    state, buffer = self._event(binding, state, 'text_delta', buffer), ''
            if buffer:
                state = self._event(binding, state, 'text_delta', buffer)
            state = self._event(binding, state, 'completed')
        except ProviderFailed:
            state = self._event(binding, self.runs.snapshot(binding), 'failed')
        except ProviderUnknown:
            state = self._event(binding, self.runs.snapshot(binding), 'unknown')
        return self._finish(receipt, state)
