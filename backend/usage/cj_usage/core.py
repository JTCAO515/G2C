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


def checked_clock_value(now, previous=None):
    """Mutable server clock boundary, shared by ledger and in-flight limits."""
    if type(now) not in (int, float) or not math.isfinite(now):
        raise Blocked('clock_invalid')
    if previous is not None and now < previous:
        raise Blocked('clock_regressed')
    return now


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


NATIVE4_PROFILE = 'lio-native4.1'
# Character reservations are independent of the actual model's 1536-token cap.
NATIVE4_MODEL_CALLS = 6
NATIVE4_AMAP_CALLS = 45
NATIVE4_MODEL_OUTPUT = 12000
NATIVE4_TOOL_OUTPUT = 8192


@dataclass(frozen=True)
class RunLimits:
    steps: int
    tools: int
    output: int
    models: int | None = None


def run_limits(ledger, run_id):
    c = ledger.config
    if run_profile_of(ledger, run_id) == NATIVE4_PROFILE:
        tools = NATIVE4_AMAP_CALLS + c.max_tools
        return RunLimits(NATIVE4_MODEL_CALLS + tools, tools,
                         NATIVE4_MODEL_CALLS*NATIVE4_MODEL_OUTPUT + tools*NATIVE4_TOOL_OUTPUT,
                         NATIVE4_MODEL_CALLS)
    return RunLimits(c.max_steps, c.max_tools, c.max_output)


def model_attempts(ledger, run_id):
    return sum(a.command.kind in ('model', 'memory') for a in ledger.attempts.values()
               if a.command.run_id == run_id)


def provider_attempts(ledger, run_id, provider_kind):
    return sum(ledger.attempt_providers.get(key) == provider_kind for key,a in ledger.attempts.items()
               if a.command.run_id == run_id)


@dataclass
class Ledger:
    config: Config | None = None
    attempts: dict[str, Attempt] = field(default_factory=dict)
    runs: dict[str, Run] = field(default_factory=dict)
    last_clock: float | None = None


@dataclass
class LedgerV2(Ledger):
    run_profiles: dict[str, str] = field(default_factory=dict)
    attempt_providers: dict[str, str] = field(default_factory=dict)


def run_profile_of(ledger, run_id):
    return ledger.run_profiles.get(run_id) if isinstance(ledger, LedgerV2) else None


class Repository(Protocol):
    """Bound by trusted composition to ONE user/environment/budget period.

    Atomic serializable read-modify-write; rollback on exception, commit before
    return, immutable snapshots on read. Unknown commit ACK prohibits dispatch.
    No caller-selected scope; no in-memory implementation shipped for services.
    """
    def transaction(self) -> ContextManager[Ledger]: ...


class Meter:
    def __init__(self, repository: Repository, config: Config, clock, *, run_profile=None):
        if not isinstance(config, Config) or clock is None:
            raise Blocked('configuration_required')
        if run_profile not in (None, NATIVE4_PROFILE) or (run_profile is not None and config.unit != 'provider_call'):
            raise Blocked('invalid_run_profile')
        self.repo, self.config, self.clock = repository, config, clock
        self.run_profile = run_profile

    def _now(self, ledger):
        now = checked_clock_value(self.clock(), ledger.last_clock)
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

    def reserve(self, command, *, provider_kind=None):
        if not isinstance(command, Command):
            raise Blocked('invalid_configuration_or_input')
        if self.run_profile is None and provider_kind is not None:
            raise Blocked('invalid_provider_kind')
        if self.run_profile is not None:
            if command.kind in ('model', 'memory'):
                if provider_kind not in (None, 'model'):raise Blocked('invalid_provider_kind')
                provider_kind = 'model'
            elif provider_kind not in ('amap', 'local'):
                raise Blocked('explicit_registered_tool_provider_required')
        with self.repo.transaction() as ledger:
            if self.run_profile is not None and not isinstance(ledger, LedgerV2):
                raise Blocked('version_2_ledger_required')
            self._bind(ledger)
            if command.run_id in ledger.runs and run_profile_of(ledger, command.run_id) != self.run_profile:
                raise Blocked('original_run_profile_conflict')
            previous = ledger.attempts.get(command.attempt_id)
            if previous:
                if (previous.command != command or (self.run_profile is not None
                        and ledger.attempt_providers[command.attempt_id] != provider_kind)):
                    raise Blocked('id_conflict')
                return previous
            now = self._now(ledger)
            c = self.config
            if not c.period_start <= now < c.period_end:
                raise Blocked('period_closed')
            run = ledger.runs.setdefault(command.run_id, Run(now))
            if self.run_profile is not None:
                ledger.run_profiles[command.run_id] = self.run_profile
            limits = run_limits(ledger, command.run_id)
            if run.cancelled or now - run.started >= c.max_seconds:
                raise Blocked('run_stopped')
            if (run.steps >= limits.steps or
                    (command.kind == 'tool' and run.tools >= limits.tools) or
                    (self.run_profile is not None and provider_kind == 'amap'
                     and provider_attempts(ledger, command.run_id, 'amap') >= NATIVE4_AMAP_CALLS) or
                    (self.run_profile is not None and provider_kind == 'local'
                     and provider_attempts(ledger, command.run_id, 'local') >= c.max_tools) or
                    (limits.models is not None and command.kind in ('model', 'memory')
                     and model_attempts(ledger, command.run_id) >= limits.models) or
                    (self.run_profile is not None and command.output_limit >
                     (NATIVE4_TOOL_OUTPUT if command.kind == 'tool' else NATIVE4_MODEL_OUTPUT)) or
                    self.output_exposure(ledger, command.run_id) + command.output_limit > limits.output or
                    self.exposure(ledger) + command.reserve > c.budget):
                raise Blocked('limit_exceeded')
            run.steps += 1
            run.tools += command.kind == 'tool'
            result = Attempt(command)
            ledger.attempts[command.attempt_id] = result
            if self.run_profile is not None:
                ledger.attempt_providers[command.attempt_id] = provider_kind
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
                    self.output_exposure(ledger, a.command.run_id) > run_limits(ledger, a.command.run_id).output):
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
