"""Integer-unit accounting. Repository transactions must serialize the entire scope."""
from dataclasses import dataclass, field, replace
from typing import Protocol, ContextManager
import math


class Blocked(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise Blocked('invalid_configuration_or_input')


def label(value):
    if not isinstance(value, str) or not value or len(value) > 200:
        raise Blocked('invalid_configuration_or_input')


@dataclass(frozen=True)
class Config:
    unit: str
    budget: int
    period_start: int
    period_end: int
    max_steps: int
    max_tools: int
    max_output: int
    max_seconds: int

    def __post_init__(self):
        label(self.unit)
        for value in (self.budget, self.max_steps, self.max_tools,
                      self.max_output, self.max_seconds):
            integer(value, 1)
        integer(self.period_start)
        integer(self.period_end, self.period_start + 1)


@dataclass(frozen=True)
class Command:
    attempt_id: str
    operation_id: str
    run_id: str
    kind: str
    input_digest: str
    reserve: int
    output_limit: int

    def __post_init__(self):
        for value in (self.attempt_id, self.operation_id, self.run_id):
            label(value)
        if self.kind not in ('model', 'tool', 'memory'):
            raise Blocked('invalid_configuration_or_input')
        if (not isinstance(self.input_digest, str) or len(self.input_digest) != 64
                or any(c not in '0123456789abcdef' for c in self.input_digest)):
            raise Blocked('invalid_configuration_or_input')
        integer(self.reserve, 1)
        integer(self.output_limit, 1)


@dataclass(frozen=True)
class Receipt:
    attempt_id: str
    receipt_id: str
    unit: str
    actual: int
    output: int

    def __post_init__(self):
        for value in (self.attempt_id, self.receipt_id, self.unit):
            label(value)
        integer(self.actual)
        integer(self.output)


@dataclass(frozen=True)
class Attempt:
    command: Command
    state: str = 'reserved'
    receipt: Receipt | None = None
    cancelled: bool = False
    exceeded: bool = False


@dataclass
class Run:
    started: float
    steps: int = 0
    tools: int = 0
    cancelled: bool = False


@dataclass
class Ledger:
    config: Config | None = None
    attempts: dict[str, Attempt] = field(default_factory=dict)
    runs: dict[str, Run] = field(default_factory=dict)
    last_clock: float | None = None


class Repository(Protocol):
    """Bound by trusted composition to ONE user/environment/budget period.

    Atomic serializable read-modify-write; rollback on exception, commit before
    return, immutable snapshots on read. Unknown commit ACK prohibits dispatch.
    No caller-selected scope; no in-memory implementation shipped for services.
    """
    def transaction(self) -> ContextManager[Ledger]: ...


class Meter:
    def __init__(self, repository: Repository, config: Config, clock):
        if not isinstance(config, Config) or not callable(clock):
            raise Blocked('configuration_required')
        self.repo, self.config, self.clock = repository, config, clock

    def _now(self, ledger):
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise Blocked('clock_invalid')
        if ledger.last_clock is not None and now < ledger.last_clock:
            raise Blocked('clock_regressed')
        ledger.last_clock = now
        return now

    def _bind(self, ledger):
        if ledger.config is None:
            ledger.config = self.config
        if ledger.config != self.config:
            raise Blocked('configuration_conflict')

    @staticmethod
    def exposure(ledger):
        return sum(a.receipt.actual if a.receipt else
                   (0 if a.state == 'released' else a.command.reserve)
                   for a in ledger.attempts.values())

    @staticmethod
    def output_exposure(ledger, run_id):
        return sum(a.receipt.output if a.receipt else
                   (0 if a.state == 'released' else a.command.output_limit)
                   for a in ledger.attempts.values() if a.command.run_id == run_id)

    def reserve(self, command):
        if not isinstance(command, Command):
            raise Blocked('invalid_configuration_or_input')
        with self.repo.transaction() as ledger:
            self._bind(ledger)
            previous = ledger.attempts.get(command.attempt_id)
            if previous:
                if previous.command != command:
                    raise Blocked('id_conflict')
                return previous
            now = self._now(ledger)
            c = self.config
            if not c.period_start <= now < c.period_end:
                raise Blocked('period_closed')
            run = ledger.runs.setdefault(command.run_id, Run(now))
            if run.cancelled or now - run.started >= c.max_seconds:
                raise Blocked('run_stopped')
            if (run.steps >= c.max_steps or
                    (command.kind == 'tool' and run.tools >= c.max_tools) or
                    self.output_exposure(ledger, command.run_id) + command.output_limit > c.max_output or
                    self.exposure(ledger) + command.reserve > c.budget):
                raise Blocked('limit_exceeded')
            run.steps += 1
            run.tools += command.kind == 'tool'
            result = Attempt(command)
            ledger.attempts[command.attempt_id] = result
            return result

    def query(self, attempt_id):
        with self.repo.transaction() as ledger:
            self._bind(ledger)
            return ledger.attempts[attempt_id]

    def claim(self, attempt_id):
        """One durable claim only; crash after claim remains unknown, never re-dispatch."""
        with self.repo.transaction() as ledger:
            self._bind(ledger)
            a = ledger.attempts[attempt_id]
            now = self._now(ledger)
            run = ledger.runs[a.command.run_id]
            if a.state != 'reserved':
                raise Blocked('already_claimed_or_terminal')
            if (run.cancelled or now - run.started >= self.config.max_seconds or
                    not self.config.period_start <= now < self.config.period_end or
                    self.exposure(ledger) > self.config.budget or
                    self.output_exposure(ledger, a.command.run_id) > self.config.max_output):
                raise Blocked('run_stopped')
            ledger.attempts[attempt_id] = replace(a, state='unknown')
            return ledger.attempts[attempt_id]

    def cancel(self, run_id):
        with self.repo.transaction() as ledger:
            self._bind(ledger)
            ledger.runs[run_id].cancelled = True
            for key, a in list(ledger.attempts.items()):
                if a.command.run_id == run_id:
                    ledger.attempts[key] = replace(a, cancelled=True,
                        state='released' if a.state == 'reserved' else a.state)

    def settle(self, receipt):
        """Trusted adapter receipt only; no public/caller-submitted usage amounts."""
        if not isinstance(receipt, Receipt) or receipt.unit != self.config.unit:
            raise Blocked('receipt_invalid')
        with self.repo.transaction() as ledger:
            self._bind(ledger)
            a = ledger.attempts[receipt.attempt_id]
            if a.receipt:
                if a.receipt != receipt:
                    raise Blocked('receipt_conflict')
                return a
            if a.state != 'unknown':
                raise Blocked('not_dispatched')
            if any(x.receipt and x.receipt.receipt_id == receipt.receipt_id
                   for x in ledger.attempts.values()):
                raise Blocked('receipt_conflict')
            result = replace(a, state='settled', receipt=receipt,
                exceeded=(receipt.actual > a.command.reserve or
                          receipt.output > a.command.output_limit))
            if result.exceeded:
                ledger.runs[a.command.run_id].cancelled = True
            ledger.attempts[receipt.attempt_id] = result
            return result
