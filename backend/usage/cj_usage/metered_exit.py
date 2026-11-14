"""Single local registered-exit accounting algorithm; no executor registry here."""
from dataclasses import dataclass
import sys
from psycopg import Error as DatabaseError
from cj_run.core import Denied
from .core import Blocked, Receipt, checked_clock_value
from .postgres import CommitUnknown, RepositoryUnavailable
from .codec import CorruptLedger
from .audit import audit_prepared, AuditUnavailable


class BudgetUnknown(Exception):
    pass


class BudgetExceeded(Exception):
    def __init__(self, step_key):
        super().__init__('local run budget exhausted')
        self.step_key=step_key


@dataclass(repr=False)
class _PreparedCall:
    step: object
    materialize: object
    step_key: str
    guard: object
    consumed: bool = False
    receipt: object = None
    materialize_with_guard: object = None


class MeteredExitCore:
    def __init__(self, config, resolve_meter, *, clock):
        self.config,self.resolve_meter,self.clock=config,resolve_meter,clock

    def _original_meter(self, binding, account):
        meter=self.resolve_meter(binding,account)
        if meter.repo.scope != account or meter.config != self.config:
            raise BudgetUnknown('original budget partition unavailable')
        return meter

    def _now(self, previous):
        try: return checked_clock_value(self.clock(),previous)
        except Blocked: raise BudgetUnknown('budget clock unavailable') from None

    def _stopped_before_reserve(self, meter, command, reason):
        """A refused reserve wrote nothing; only a proven deadline/period end is exhaustion.

        A cancelled run, an existing attempt, a clock before the period start or
        an unreadable ledger stays unknown.
        """
        if reason not in ('run_stopped','period_closed'): return False
        with meter.repo.transaction() as ledger:
            if command.attempt_id in ledger.attempts: return False
            run=ledger.runs.get(command.run_id)
            now=self._now(ledger.last_clock)
        if now >= self.config.period_end: return run is None or not run.cancelled
        if now < self.config.period_start: return False
        return run is not None and not run.cancelled and now-run.started >= self.config.max_seconds

    def stream(self, call):
        """First next() MUST be under RUN fence. Later reads are an in-flight call.

        The in-process consumed flag is conservative sequencing, not the durable
        authority: immutable step uniqueness and Meter.claim prevent redispatch.
        """
        if call.consumed:
            raise BudgetUnknown('original prepared call unavailable')
        call.consumed=True
        step=call.step
        meter=self._original_meter(step.binding,step.ledger_scope)
        command=step.command
        stream=None
        try:
            audit_prepared(command,self.config.unit)
            if call.guard() is not True: raise Denied('original authority unavailable before reserve')
            try: meter.reserve(command)
            except Blocked as error:
                if error.reason == 'limit_exceeded' or self._stopped_before_reserve(meter,command,error.reason):
                    raise BudgetExceeded(call.step_key) from None
                raise BudgetUnknown('budget admission unavailable') from None
            meter.claim(command.attempt_id)
            with meter.repo.transaction() as ledger:
                run_started=ledger.runs[command.run_id].started
                previous=ledger.last_clock
            now=self._now(previous)
            def final_guard():
                nonlocal now
                if call.guard() is not True:return False
                now=self._now(now)
                if (not self.config.period_start<=now<self.config.period_end
                        or now-run_started>=self.config.max_seconds):
                    raise BudgetExceeded(call.step_key)
                return True
            if not final_guard():raise Denied('original authority unavailable before materialization')
            invoke=(call.materialize() if call.materialize_with_guard is None else
                    call.materialize_with_guard(final_guard))
            # All ledger IO/cleanup and input materialization precede final admission.
            if final_guard() is not True: raise Denied('original authority unavailable before call')
            stream=invoke()
            output=0
            for chunk in stream:
                if type(chunk) is not str: raise BudgetUnknown('invalid local provider chunk')
                chunk.encode('utf-8')
                output+=len(chunk)
                now=self._now(now)
                if output>command.output_limit or now-run_started>=self.config.max_seconds:
                    raise BudgetExceeded(call.step_key)
                yield chunk
            # EOF can itself arrive after the deadline without yielding a chunk.
            now=self._now(now)
            if now-run_started>=self.config.max_seconds: raise BudgetExceeded(call.step_key)
            if call.guard() is not True: raise Denied('original authority unavailable at completion')
            # Only a complete local invocation supplies its original receipt.
            receipt=(Receipt(command.attempt_id,'local:'+command.attempt_id,self.config.unit,1,output)
                     if call.receipt is None else call.receipt(command.attempt_id,self.config.unit,output))
            meter.settle(receipt)
        except (CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError,Blocked,UnicodeError,AuditUnavailable):
            raise BudgetUnknown('original budget outcome unavailable') from None
        finally:
            if stream is not None:
                primary=sys.exception()
                try: stream.close()
                except Exception:
                    if primary is not None:
                        primary.add_note('provider stream cleanup failed; original failure retained')
                    else:
                        raise BudgetUnknown('provider stream cleanup unavailable') from None

    def check_publication(self, binding):
        """Recheck total run time after settlement/source work, under RUN fence."""
        self.prepare_publication(binding)()

    def prepare_publication(self,binding):
        """Read original start/clock before effect leases; returned check does no SQL.

        This is data preparation, never a permit. The final check must run after
        every lease/source preparation, immediately before actual publication.
        """
        from cj_run.step_usage import ledger_scope_for
        account=ledger_scope_for(binding.scope,self.config)
        meter=self._original_meter(binding,account)
        try:
            with meter.repo.transaction() as ledger:
                started=ledger.runs[binding.run_id].started
                previous=ledger.last_clock
        except (CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError,Blocked):
            raise BudgetUnknown('original publication budget outcome unavailable') from None
        return self._deadline(started,previous)

    def _deadline(self,started,previous):
        """SQL-free total run time check from an already read start and clock."""
        def check():
            nonlocal previous
            previous=self._now(previous)
            if previous-started>=self.config.max_seconds:
                raise BudgetExceeded('draft')
        return check

    def stop(self, binding):
        """After RUN terminal is durable, cancel original unclaimed reserves only.

        Missing run is expected when Stage A committed but reserve never happened;
        terminal RUN prevents any future reserve. A missing/corrupt ledger is NOT
        treated as an empty run or reset. A failed cancellation never reopens RUN.
        """
        from cj_run.step_usage import ledger_scope_for
        account=ledger_scope_for(binding.scope,self.config)
        meter=self._original_meter(binding,account)
        try:
            with meter.repo.transaction() as ledger:
                exists=binding.run_id in ledger.runs
            if exists: meter.cancel(binding.run_id)
        except (CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError,Blocked):
            raise BudgetUnknown('original budget cancellation unavailable') from None
