"""Gated local FakeProvider exit. Caller owns the original RUN start/cancel fence."""
from dataclasses import dataclass
import json
import math
from psycopg import Error as DatabaseError
from cj_run.step_usage import StepStore, OriginalStepOnly
from cj_run.postgres import CommitUnknown as RunCommitUnknown
from cj_run.core import Denied
from .core import Blocked, Receipt
from .postgres import CommitUnknown, RepositoryUnavailable
from .codec import CorruptLedger


class BudgetUnknown(Exception):
    pass


class BudgetExceeded(Exception):
    def __init__(self, step_key):
        super().__init__('local run budget exhausted')
        self.step_key=step_key


@dataclass(repr=False)
class _PreparedCall:
    step: object
    provider: object
    guard: object
    consumed: bool = False


class LocalProviderExit:
    def __init__(self, config, resolve_meter, *, clock, output_limits, environment):
        if (environment != 'local' or config.unit != 'provider_call'
                or set(output_limits) != {'answer','draft'}
                or any(type(v) is not int or not 1 <= v <= config.max_output for v in output_limits.values())):
            raise ValueError('explicit local provider_call limits required')
        self.config,self.resolve_meter,self.clock=config,resolve_meter,clock
        self.output_limits=dict(output_limits)

    def prepare(self, runs, binding, step_key, messages, system, provider):
        """Stage A is separate from the later RUN-fenced first stream advance."""
        from cj_agent.provider import FakeProvider
        if not isinstance(provider,FakeProvider):
            raise BudgetUnknown('only local FakeProvider may use this exit')
        try:
            raw=json.dumps({'messages':messages,'system':system},ensure_ascii=False,
                           separators=(',',':'),allow_nan=False).encode('utf-8')
        except UnicodeError:
            raise BudgetUnknown('original input encoding unavailable') from None
        try:
            step=StepStore(runs,self.config).create(binding,step_key,raw,self.output_limits[step_key])
        except (OriginalStepOnly,RunCommitUnknown,DatabaseError,ValueError):
            raise BudgetUnknown('original step preparation unavailable') from None
        return _PreparedCall(step,provider,lambda:runs.valid(binding))

    def _meter(self, step):
        meter=self.resolve_meter(step.binding,step.ledger_scope)
        if meter.repo.scope != step.ledger_scope or meter.config != self.config:
            raise BudgetUnknown('original budget partition unavailable')
        return meter

    def _now(self, previous):
        now=self.clock()
        if type(now) not in (int,float) or not math.isfinite(now) or now < previous:
            raise BudgetUnknown('budget clock unavailable')
        return now

    def stream(self, call):
        """First next() MUST be under RUN fence. Later reads are an in-flight call.

        The in-process consumed flag is conservative sequencing, not the durable
        authority: immutable step uniqueness and Meter.claim prevent redispatch.
        """
        if type(call) is not _PreparedCall or call.consumed:
            raise BudgetUnknown('original prepared call unavailable')
        call.consumed=True
        step=call.step
        meter=self._meter(step)
        command=step.command
        stream=None
        try:
            if call.guard() is not True: raise Denied('original authority unavailable before reserve')
            try: meter.reserve(command)
            except Blocked as error:
                if error.reason == 'limit_exceeded': raise BudgetExceeded(step.step_key) from None
                raise BudgetUnknown('budget admission unavailable') from None
            meter.claim(command.attempt_id)
            # Same RUN fence still held; no cancellation can interleave before call.
            if call.guard() is not True: raise Denied('original authority unavailable after claim')
            with meter.repo.transaction() as ledger:
                run_started=ledger.runs[command.run_id].started
                previous=ledger.last_clock
            now=self._now(previous)
            if now-run_started >= self.config.max_seconds: raise BudgetExceeded(step.step_key)
            inputs=json.loads(step.original.input_bytes)
            stream=call.provider.stream(inputs['messages'],system=inputs['system'])
            output=0
            for chunk in stream:
                if type(chunk) is not str: raise BudgetUnknown('invalid local provider chunk')
                chunk.encode('utf-8')
                output+=len(chunk)
                now=self._now(now)
                if output>command.output_limit or now-run_started>=self.config.max_seconds:
                    raise BudgetExceeded(step.step_key)
                yield chunk
            # Only a complete local invocation supplies its original receipt.
            meter.settle(Receipt(command.attempt_id,'local:'+command.attempt_id,
                                 self.config.unit,1,output))
        except (CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError,Blocked,UnicodeError):
            raise BudgetUnknown('original budget outcome unavailable') from None
        finally:
            if stream is not None: stream.close()

    def stop(self, binding):
        """After RUN terminal is durable, cancel original unclaimed reserves only.

        Missing run is expected when Stage A committed but reserve never happened;
        terminal RUN prevents any future reserve. A missing/corrupt ledger is NOT
        treated as an empty run or reset. A failed cancellation never reopens RUN.
        """
        from cj_run.step_usage import ledger_scope_for
        account=ledger_scope_for(binding.scope,self.config)
        meter=self.resolve_meter(binding,account)
        if meter.repo.scope!=account or meter.config!=self.config:
            raise BudgetUnknown('original cancellation partition unavailable')
        try:
            with meter.repo.transaction() as ledger:
                exists=binding.run_id in ledger.runs
            if exists: meter.cancel(binding.run_id)
        except (CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError,Blocked):
            raise BudgetUnknown('original budget cancellation unavailable') from None
