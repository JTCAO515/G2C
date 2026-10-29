"""Host-side worker: MESSAGE pending deliveries -> RUN events via one model provider (P2a).

Runs inside the trusted host, already bound to one internal scope. It never takes
owner or scope from request data. Recovery rules (ADR-0003):

- a run found `running` after a restart is marked `unknown` and is NOT resent;
- a provider result that may have been processed is `unknown`, a definite rejection
  is `failed`; neither is retried automatically;
- a delivery is acknowledged only after RUN holds a terminal status.
"""
from dataclasses import dataclass
from contextlib import contextmanager, ExitStack
import json

# The worker must be ready (or fail startup) before accepting any work (#176).
from cj_feasibility import solver as _solver_runtime

from cj_run.core import Binding, Conflict, Denied, Event, Service, TERMINAL, advance
from cj_message.domain import Unavailable as MessageUnavailable

from cj_needs.domain import Denied as NeedsDenied
from cj_needs.revision_lease import LeaseUnavailable

from .draft import DRAFT_SYSTEM, DraftRejected
from .provider import ProviderFailed, ProviderUnknown

FLUSH_CHARS = 24
_END = object()


def original_context_valid(binding, messages, admitted):
    """Current host admission plus the same original MESSAGE binding.

    None denotes an unreadable admission source, never permission. This says
    whether context may be used, not whether an in-flight model was charged.
    """
    try:
        allowed = admitted()
    except (OSError, ValueError):
        return None
    if allowed is not True: return False
    try:
        stored = messages.query(binding.message_id)
    except MessageUnavailable:
        return False
    if stored is None: return False
    receipt = stored.receipt
    return (messages.repository.scope == binding.scope
            and (receipt.message_id, receipt.conversation_id, receipt.generation, receipt.run_id, receipt.sequence)
            == (binding.message_id, binding.conversation_id, binding.generation, binding.run_id, binding.message_sequence))


class _PublicationUncertain(Exception):
    pass


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
    def __init__(self, *, scope, messages, runs, provider, drafts=None, needs_lease=None):
        """`messages`: cj_message.domain.Service and `runs`: cj_run.core.Service, both bound to `scope`.

        `drafts`: optional cj_agent.draft.DraftPublisher for this user's TRIP scope; messages
        with creation_intent `consider_trip` then also get a reviewable proposal.
        """
        self.scope, self.messages, self.runs, self.provider, self.drafts = scope, messages, runs, provider, drafts
        self.needs_lease = needs_lease

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

    def _step(self, binding, invoke, effect=None, *, draft=False):
        """Serialize this worker's actual step start/publication against cancellation.

        This does not enable Service.dispatch or create a new execution authority.
        A provider's first advance starts under the RUN fence; later stream reads
        are an already-started call and do not hold the fence. Committed publication
        and its RUN receipt are ordered before any subsequent cancellation.
        """
        publication_started = False
        try:
            with ExitStack() as leases:
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
                    if draft and state.draft_outcome is not None:
                        raise Conflict('draft result already recorded before invocation')
                    if draft and self.needs_lease is not None:
                        if effect is not None:
                            check_needs = leases.enter_context(self.needs_lease(binding))
                            check_needs()
                        else:
                            # Do not hold a NEEDS lease over provider/source network IO.
                            with self.needs_lease(binding) as check_needs:
                                check_needs()
                    publication_started = effect is not None
                    result = invoke()
                    if effect is not None:
                        updated = advance(state, Event(binding, state.sequence + 1,
                                          f'{binding.run_id}:{state.sequence + 1}', 'effect_committed', effect(result)), self.runs.valid)
                        if tx.get(binding) != state:
                            raise Conflict('state changed during publication')
                        tx.put(updated)
                        state = updated
        except (NeedsDenied, LeaseUnavailable, Denied) as error:
            if publication_started:
                raise _PublicationUncertain() from error
            raise
        return state, result

    def _stream(self, binding, messages, system=None):
        stream = None
        def start():
            nonlocal stream
            stream = self.provider.stream(messages) if system is None else self.provider.stream(messages, system=system)
            return next(stream, _END)
        try:
            _, chunk = self._step(binding, start, draft=system is not None)
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

    def _draft(self, binding, state, text, original):
        """Second, non-streamed model call. A bad or unknown draft never fails the answer."""
        try:
            reply = ''.join(self._stream(binding, [{'role': 'user', 'content': text}], system=DRAFT_SYSTEM))
            if self.drafts.content_version == 'legacy':
                state, draft = self._step(binding, lambda: self.drafts.publish(binding.run_id, reply),
                                          lambda value: 'trip_proposal:' + value.proposal_id, draft=True)
            else:
                _, sources = self._step(binding, lambda: self.drafts.sources_for(binding), draft=True)
                state, draft = self._step(binding, lambda: self.drafts.publish_for_message(
                    binding, original, self.messages.query(binding.message_id), reply, sources),
                    lambda value: 'trip_proposal:' + value.proposal_id, draft=True)
        except (DraftRejected, ProviderFailed, ProviderUnknown) as error:
            outcome = ('validation_failed' if isinstance(error, DraftRejected) else
                       'provider_failed' if isinstance(error, ProviderFailed) else 'provider_unknown')
            state = self._event(binding, self.runs.snapshot(binding), 'draft_outcome', outcome)
            return state, None
        return state, draft.proposal_id

    def _one(self, receipt):
        binding = self._binding(receipt)
        messages, runs, provider, drafts = self.messages, self.runs, self.provider, self.drafts
        with runs.repository.worker_lease(binding) as check:
            if check is None:
                return Outcome(receipt.message_id, receipt.run_id, 'waiting')
            class OwnedRepository:
                @contextmanager
                def transaction(self):
                    with runs.repository.transaction() as tx:
                        check()
                        yield tx
                        check()
                    check()
            owned = RunWorker(scope=binding.scope, messages=messages, provider=provider, drafts=drafts,
                              needs_lease=self.needs_lease,
                              runs=Service(OwnedRepository(), runs.valid))
            return owned._owned(receipt, binding)

    def _owned(self, receipt, binding):
        try:
            return self._execute(receipt, binding)
        except _Stopped as stopped:
            return self._finish(receipt, stopped.state)
        except (LeaseUnavailable, _PublicationUncertain):
            current = self.runs.snapshot(binding)
            if current.status not in TERMINAL:
                current = self._event(binding, current, 'unknown')
            return self._finish(receipt, current)
        except (Denied, NeedsDenied):
            current = self.runs.snapshot(binding)
            if current.status not in TERMINAL:
                current = self._event(binding, current, 'context_invalid')
            return self._finish(receipt, current)
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
        if self.needs_lease is not None and command['creation_intent'] == 'consider_trip':
            with self.needs_lease(binding) as check_needs:
                check_needs()
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
                state, proposal_id = self._draft(binding, state, text, stored)
            state = self._event(binding, state, 'completed')
        except ProviderFailed:
            state = self._event(binding, self.runs.snapshot(binding), 'failed')
        except ProviderUnknown:
            state = self._event(binding, self.runs.snapshot(binding), 'unknown')
        return self._finish(receipt, state, proposal_id)
