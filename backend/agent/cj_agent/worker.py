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

# The worker must be ready (or fail startup) before accepting any work (#176).
from cj_feasibility import solver as _solver_runtime

from cj_run.core import Binding, Conflict, Denied, Event, TERMINAL, advance

from .draft import DRAFT_SYSTEM, DraftRejected
from .provider import ProviderFailed, ProviderUnknown

FLUSH_CHARS = 24
_END = object()


class _Stopped(Exception):
    def __init__(self, state):
        super().__init__('original RUN is terminal')
        self.state = state


@dataclass(frozen=True)
class Outcome:
    message_id: str
    run_id: str
    status: str  # completed | failed | unknown | waiting
    proposal_id: str | None = None


class RunWorker:
    def __init__(self, *, scope, messages, runs, provider, drafts=None):
        """`messages`: cj_message.domain.Service and `runs`: cj_run.core.Service, both bound to `scope`.

        `drafts`: optional cj_agent.draft.DraftPublisher for this user's TRIP scope; messages
        with creation_intent `consider_trip` then also get a reviewable proposal.
        """
        self.scope, self.messages, self.runs, self.provider, self.drafts = scope, messages, runs, provider, drafts

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
        try:
            return self.runs.apply(Event(binding, sequence, f'{binding.run_id}:{sequence}', kind, value))
        except Conflict:
            current = self.runs.snapshot(binding)
            if current.status in TERMINAL:
                raise _Stopped(current) from None
            raise

    def _running(self, binding):
        state = self.runs.snapshot(binding)
        if state.status in TERMINAL:
            raise _Stopped(state)
        return state

    def _step(self, binding, invoke, effect=None):
        """Serialize this worker's actual step start/publication against cancellation.

        This does not enable Service.dispatch or create a new execution authority.
        A provider's first advance starts under the RUN fence; later stream reads
        are an already-started call and do not hold the fence. Committed publication
        and its RUN receipt are ordered before any subsequent cancellation.
        """
        with self.runs.repository.transaction() as tx:
            state = tx.get(binding)
            if state.status in TERMINAL:
                raise _Stopped(state)
            if state.status != 'running':
                raise Conflict('step requires original running state')
            if self.runs.valid(binding) is not True:
                raise Denied('context invalid or unknown')
            if tx.get(binding) != state:
                raise Conflict('state changed during step guard')
            result = invoke()
            if effect is not None:
                updated = advance(state, Event(binding, state.sequence + 1,
                                  f'{binding.run_id}:{state.sequence + 1}', 'effect_committed', effect(result)), self.runs.valid)
                if tx.get(binding) != state:
                    raise Conflict('state changed during publication')
                tx.put(updated)
                state = updated
        return state, result

    def _stream(self, binding, messages, system=None):
        stream = None
        def start():
            nonlocal stream
            stream = self.provider.stream(messages) if system is None else self.provider.stream(messages, system=system)
            return next(stream, _END)
        try:
            _, chunk = self._step(binding, start)
            while chunk is not _END:
                self._running(binding)
                yield chunk
                self._running(binding)
                chunk = next(stream, _END)
        finally:
            if stream is not None:
                stream.close()

    def _finish(self, receipt, state, proposal_id=None):
        if state.status in TERMINAL:
            self.messages.acknowledge(receipt)
        return Outcome(receipt.message_id, receipt.run_id, state.status, proposal_id)

    def _draft(self, binding, state, text):
        """Second, non-streamed model call. A bad or unknown draft never fails the answer."""
        try:
            reply = ''.join(self._stream(binding, [{'role': 'user', 'content': text}], system=DRAFT_SYSTEM))
            state, draft = self._step(binding, lambda: self.drafts.publish(binding.run_id, reply),
                                      lambda value: 'trip_proposal:' + value.proposal_id)
        except (DraftRejected, ProviderFailed, ProviderUnknown):
            return state, None
        return state, draft.proposal_id

    def _one(self, receipt):
        binding = self._binding(receipt)
        try:
            return self._execute(receipt, binding)
        except _Stopped as stopped:
            return self._finish(receipt, stopped.state)
        except Conflict:
            current = self.runs.snapshot(binding)
            if current.status in TERMINAL:
                return self._finish(receipt, current)
            raise

    def _execute(self, receipt, binding):
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
        command = json.loads(stored.raw)
        text = command['text']
        proposal_id = None
        buffer = ''
        try:
            for chunk in self._stream(binding, [{'role': 'user', 'content': text}]):
                buffer += chunk
                if len(buffer) >= FLUSH_CHARS:
                    state, buffer = self._event(binding, state, 'text_delta', buffer), ''
            if buffer:
                state = self._event(binding, state, 'text_delta', buffer)
            if self.drafts is not None and command['creation_intent'] == 'consider_trip':
                state, proposal_id = self._draft(binding, state, text)
            state = self._event(binding, state, 'completed')
        except ProviderFailed:
            state = self._event(binding, self.runs.snapshot(binding), 'failed')
        except ProviderUnknown:
            state = self._event(binding, self.runs.snapshot(binding), 'unknown')
        return self._finish(receipt, state, proposal_id)
