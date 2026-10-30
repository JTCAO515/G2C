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
from cj_usage.local_provider_exit import BudgetExceeded, BudgetUnknown
from cj_memory.runtime import RuntimeDenied, RuntimeUnknown

from .draft import DRAFT_SYSTEM, DraftRejected
from .provider import FakeProvider, ProviderFailed, ProviderUnknown

FLUSH_CHARS = 24
_END = object()


class _MemoryProvider(FakeProvider):
    """Local Fake adapter retains the budget exit's existing provider policy."""
    def __init__(self, original, memory):
        self.original, self.memory = original, memory

    def stream(self, messages, system=None):
        stream = self.original.stream(messages, system=system)
        primary = None
        try:
            self.memory.check()
            yield from stream
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                stream.close()
            except BaseException:
                if primary is None:
                    raise RuntimeUnknown('memory provider cleanup unavailable') from None
                primary.add_note('memory provider cleanup unavailable')


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
    def __init__(self, *, scope, messages, runs, provider, drafts=None, needs_lease=None, budget_exit=None, execution_guard=None, memory=None, message_context=None, tools=None):
        """`messages`: cj_message.domain.Service and `runs`: cj_run.core.Service, both bound to `scope`.

        `drafts`: optional cj_agent.draft.DraftPublisher for this user's TRIP scope; messages
        with creation_intent `consider_trip` then also get a reviewable proposal.
        """
        self.scope, self.messages, self.runs, self.provider, self.drafts = scope, messages, runs, provider, drafts
        self.needs_lease = needs_lease
        self.budget_exit = budget_exit
        self.execution_guard = execution_guard
        self.memory = memory
        self.memory_run = None
        self.message_context=message_context
        self._publication_check=None
        self.tools=tools

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
            event = Event(binding, sequence, f'{binding.run_id}:{sequence}', kind, value)
            memory_effect=self.memory_run is not None and kind in {'text_delta','completed','draft_outcome'}
            travel_effect=self.message_context is not None and kind in {'started','text_delta','completed','effect_committed'}
            if not memory_effect and not travel_effect:
                return self.runs.apply(event)
            with ExitStack() as leases:
                with self.runs.repository.transaction() as tx:
                    old = tx.get(binding)
                    context=(leases.enter_context(self.message_context.hold_for_effect(binding)) if travel_effect else None)
                    check_memory=leases.enter_context(self.memory_run.hold(binding)) if memory_effect else None
                    updated = advance(old, event, self.runs.valid)
                    if tx.get(binding) != old:
                        raise Conflict('state changed during memory publication')
                    if context is not None:context.check(binding)
                    if check_memory is not None:check_memory()
                    tx.put(updated)
            return updated
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
                    deadline=(self.budget_exit.prepare_publication(binding)
                              if self.message_context is not None and draft and effect is not None
                              and self.budget_exit is not None else None)
                    context=(leases.enter_context(self.message_context.hold_for_effect(binding))
                             if self.message_context is not None else None)
                    if self.runs.valid(binding) is not True:
                        raise Denied('context invalid or unknown')
                    if tx.get(binding) != state:
                        raise Conflict('state changed during step guard')
                    check_memory = (leases.enter_context(self.memory_run.hold(binding))
                                    if self.memory_run is not None else None)
                    if draft and state.draft_outcome is not None:
                        raise Conflict('draft result already recorded before invocation')
                    check_needs=None
                    if draft and self.needs_lease is not None:
                        if effect is not None:
                            check_needs = leases.enter_context(self.needs_lease(binding))
                            check_needs()
                        else:
                            # Do not hold a NEEDS lease over provider/source network IO.
                            with self.needs_lease(binding) as check_needs:
                                check_needs()
                            check_needs=None
                    if draft and effect is not None and self.budget_exit is not None:
                        if deadline is None:self.budget_exit.check_publication(binding)
                        if self.runs.valid(binding) is not True:
                            raise Denied('authority changed before budgeted publication')
                    publication_started = effect is not None
                    if check_memory is not None and self.message_context is None:
                        check_memory()
                    def final_check():
                        if context is not None:context.check(binding)
                        if check_memory is not None:check_memory()
                        if check_needs is not None:check_needs()
                        if deadline is not None:deadline()
                    previous_check=self._publication_check
                    if self.message_context is not None and effect is not None:
                        self._publication_check=final_check
                    try:
                        if self.message_context is not None:final_check()
                        result = invoke()
                    finally:
                        self._publication_check=previous_check
                    if effect is not None:
                        updated = advance(state, Event(binding, state.sequence + 1,
                                          f'{binding.run_id}:{state.sequence + 1}', 'effect_committed', effect(result)), self.runs.valid)
                        if tx.get(binding) != state:
                            raise Conflict('state changed during publication')
                        tx.put(updated)
                        state = updated
        except (NeedsDenied, LeaseUnavailable, Denied, RuntimeDenied, RuntimeUnknown) as error:
            if publication_started:
                raise _PublicationUncertain() from error
            raise
        return state, result

    def _stream(self, binding, messages, system=None):
        prepared = None
        if self.budget_exit is not None:
            prepared = self.budget_exit.prepare(self.runs,binding,'draft' if system is not None else 'answer',
                                                messages,system,self.provider)
        def source():
            return (self.budget_exit.stream(prepared) if prepared is not None else
                    self.provider.stream(messages) if system is None else self.provider.stream(messages,system=system))
        yield from self._stream_source(binding,source,draft=system is not None)

    def _registered_stream(self,binding,key,registration,argument):
        prepared=self.budget_exit.prepare_operation(self.runs,binding,key,registration,argument,stage='answer')
        yield from self._stream_source(binding,lambda:self.budget_exit.stream(prepared),draft=False)

    def _stream_source(self,binding,source,*,draft):
        stream=None
        def start():
            nonlocal stream
            stream=source()
            return next(stream, _END)
        try:
            _, chunk = self._step(binding, start, draft=draft)
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
            if self.budget_exit is not None and state.status != 'completed':
                self.budget_exit.stop(self._binding(receipt))
            self.messages.acknowledge(receipt)
        return Outcome(receipt.message_id, receipt.run_id, state.status, proposal_id)

    def _budget_rejection(self, binding, step):
        with self.runs.repository.transaction() as tx:
            state=tx.get(binding)
            if state.status in TERMINAL: raise _Stopped(state)
            for kind,value in [('budget_denied',step),
                               ('failed','') if step=='answer' else ('draft_outcome','budget_exhausted')]:
                sequence=state.sequence+1
                state=advance(state,Event(binding,sequence,f'{binding.run_id}:{sequence}',kind,value),self.runs.valid)
                tx.put(state)
        return state

    def _draft(self, binding, state, text, original):
        """Provider draft failures preserve the answer; accounting uncertainty stops RUN as unknown."""
        try:
            messages = ([{'role': 'user', 'content': text}] if self.memory_run is None
                        else self.memory_run.messages(text))
            reply = ''.join(self._stream(binding, messages, system=DRAFT_SYSTEM))
            if self.drafts.content_version == 'legacy':
                def publish():
                    check=self._publication_check or (self.memory_run.check if self.memory_run is not None else None)
                    return self.drafts.publish(binding.run_id,reply,**({'before_publish':check} if check is not None else {}))
                state, draft = self._step(binding, publish,
                                          lambda value: 'trip_proposal:' + value.proposal_id, draft=True)
            else:
                _, sources = self._step(binding, lambda: self.drafts.sources_for(binding), draft=True)
                def publish():
                    check=self._publication_check or (self.memory_run.check if self.memory_run is not None else None)
                    current=(self.message_context.active_original(binding) if self.message_context is not None
                             else self.messages.query(binding.message_id))
                    return self.drafts.publish_for_message(binding,original,current,reply,sources,
                        **({'before_publish':check} if check is not None else {}))
                state, draft = self._step(binding, publish,
                    lambda value: 'trip_proposal:' + value.proposal_id, draft=True)
        except BudgetExceeded:
            return self._budget_rejection(binding,'draft'), None
        except (DraftRejected, ProviderFailed, ProviderUnknown) as error:
            outcome = ('validation_failed' if isinstance(error, DraftRejected) else
                       'provider_failed' if isinstance(error, ProviderFailed) else 'provider_unknown')
            state = self._event(binding, self.runs.snapshot(binding), 'draft_outcome', outcome)
            return state, None
        return state, draft.proposal_id

    def _one(self, receipt):
        binding = self._binding(receipt)
        if self.execution_guard is not None:
            self.execution_guard(binding)
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
                              needs_lease=self.needs_lease, budget_exit=self.budget_exit,
                              memory=self.memory,
                              message_context=self.message_context,
                              tools=self.tools,
                              runs=Service(OwnedRepository(), runs.valid))
            return owned._owned(receipt, binding)

    def _owned(self, receipt, binding):
        try:
            return self._execute(receipt, binding)
        except _Stopped as stopped:
            return self._finish(receipt, stopped.state)
        except BudgetUnknown:
            current = self.runs.snapshot(binding)
            if current.status != 'running':
                # No execution retry/terminal rewrite for queued or terminal RUN.
                # Terminal RUN is durable; expose failed stop reconciliation rather
                # than retrying the accounting mutation inside this invocation.
                raise
            current = self._event(binding, current, 'unknown')
            return self._finish(receipt, current)
        except (LeaseUnavailable, _PublicationUncertain, RuntimeUnknown):
            current = self.runs.snapshot(binding)
            if self.message_context is not None and current.status=='queued':
                raise
            if current.status not in TERMINAL:
                current = self._event(binding, current, 'unknown')
            return self._finish(receipt, current)
        except (Denied, NeedsDenied, RuntimeDenied):
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
        if self.budget_exit is not None:
            self.budget_exit = self.budget_exit.for_run(binding,state)
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
        if self.memory is not None:
            self.memory_run = self.memory.capture(binding)
            self.provider = _MemoryProvider(self.provider, self.memory_run)
        if self.needs_lease is not None and command['creation_intent'] == 'consider_trip':
            with self.needs_lease(binding) as check_needs:
                check_needs()
        proposal_id = None
        buffer = ''
        try:
            inputs = ([{'role': 'user', 'content': text}] if self.memory_run is None
                      else self.memory_run.messages(text))
            chunks=self._stream(binding,inputs) if self.tools is None else self.tools.answer(self,binding,inputs)
            for chunk in chunks:
                buffer += chunk
                if len(buffer) >= FLUSH_CHARS:
                    state, buffer = self._event(binding, state, 'text_delta', buffer), ''
            if buffer:
                state = self._event(binding, state, 'text_delta', buffer)
            if self.drafts is not None and command['creation_intent'] == 'consider_trip':
                state, proposal_id = self._draft(binding, state, text, stored)
            state = self._event(binding, state, 'completed')
        except BudgetExceeded:
            state = self._budget_rejection(binding,'answer')
        except ProviderFailed:
            state = self._event(binding, self.runs.snapshot(binding), 'failed')
        except ProviderUnknown:
            state = self._event(binding, self.runs.snapshot(binding), 'unknown')
        return self._finish(receipt, state, proposal_id)
