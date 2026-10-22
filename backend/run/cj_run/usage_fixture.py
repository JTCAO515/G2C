"""Synchronous synthetic first-step composition ONLY; never register in a host.

Consumes CJ008 a6693615 core. No shared transaction exists between these domains.
An arbitrary injected callable is trusted test code, NOT a network sandbox.
"""
from dataclasses import dataclass, asdict
import json
from cj_usage.core import Command, Receipt
from .core import Binding, Event, State, Denied, Conflict
from .usage_binding import UsageBinding


class ReconcileOriginal(Exception):
    """Stop this invocation. Observe original attempt/run; do not execute a retry."""
    def __init__(self, stage):
        self.stage = stage
        super().__init__(stage)


@dataclass(frozen=True)
class Observation:
    run: State
    attempt: object
    # Observation is never a dispatch capability, even when usage is only reserved.
    recovery: str = 'reconcile_original'


class SyntheticFirstStep:
    def __init__(self, run_service, meter, *, original_binding, original_command, original_input_bytes, synthetic_executor=None):
        if type(original_binding) is not Binding or type(original_command) is not Command or original_command.run_id != original_binding.run_id:
            raise Conflict('fixed original fixture binding required')
        self.association = UsageBinding(
            json.dumps(asdict(original_command), ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
            original_input_bytes)
        self.original_binding, self.original_command = original_binding, original_command
        self._fresh_create_ack = False
        self.run = run_service
        self.meter = meter
        self.executor = synthetic_executor

    def create_fixture(self):
        # Require a genuinely new row, not replayed acceptance. A failed/unknown
        # ACK never arms execution; existing rows are query/reconcile only here.
        self._fresh_create_ack = False
        state = self.run.accept_with_usage(self.original_binding, self.association, require_new=True)
        self._fresh_create_ack = True
        return state

    def _binding(self, binding, command):
        if type(binding) is not Binding or type(command) is not Command or command.run_id != binding.run_id:
            raise Conflict('original run/attempt binding required')
        if binding != self.original_binding or command != self.original_command:
            raise Conflict('fixture may only reconcile its fixed original action')
        stored = self.run.snapshot(binding)
        if stored.usage != self.association:
            raise Conflict('stored original usage association absent or changed')
        # Scope equivalence is a trusted fixture composition prerequisite. Meter has
        # no public authority/scope accessor; do not invent one or infer from run_id.

    def observe(self, binding, command):
        self._binding(binding, command)
        attempt = self.meter.query(command.attempt_id)
        if attempt.command != command:
            raise Conflict('original attempt changed')
        return Observation(self.run.snapshot(binding), attempt)

    def execute_fixture(self, binding, command, started):
        if self.executor is None:
            raise Denied('synthetic executor absent; real dispatch disabled')
        self._binding(binding, command)
        if type(started) is not Event or started.binding != binding or started.kind != 'started' or started.sequence != 1:
            raise Conflict('explicit original start event required')
        if not self._fresh_create_ack:
            raise ReconcileOriginal('original_binding_query_only')
        # One synthetic invocation per acknowledged NEW row. Never re-arm after
        # reserve/claim/write ACK uncertainty, including in a reconstructed instance.
        self._fresh_create_ack = False
        stage = 'preflight'
        try:
            if self.run.snapshot(binding).status != 'queued':
                raise Conflict('only original queued first step supported')
            stage = 'reserve'
            self.meter.reserve(command)
            if self.run.snapshot(binding).status != 'queued':
                raise Conflict('run stopped during reservation')
            stage = 'claim'
            claimed = self.meter.claim(command.attempt_id)
            if claimed.command != command or claimed.state != 'unknown' or claimed.cancelled:
                raise Conflict('claim not usable')
            # A claim ACK is not an execution ACK. Failure/unknown here must never
            # release the reservation or cause an executor call on a later retry.
            stage = 'run_started'
            self.run.apply(started)
            stage = 'pre_executor_check'
            attempt = self.meter.query(command.attempt_id)
            if attempt.command != command or attempt.state != 'unknown' or attempt.cancelled:
                raise Conflict('attempt stopped')
            if self.run.snapshot(binding).status != 'running':
                raise Conflict('run stopped')
            # These checks are NOT an atomic dispatch fence. No real executor may
            # use this class; cancellation/claim integration remains a domain gap.
            stage = 'executor'
            receipt = self.executor(command)
            if type(receipt) is not Receipt or receipt.attempt_id != command.attempt_id:
                raise Conflict('original trusted receipt required')
            stage = 'settle'
            self.meter.settle(receipt)
            # A fee receipt never fabricates a RUN completed event or answer.
            stage = 'observe'
            return self.observe(binding, command)
        except Exception as exc:
            raise ReconcileOriginal(stage) from exc

    def cancel_fixture(self, binding, command, cancelled):
        """After reservation only. Partial stop is explicit, never compensated."""
        self._binding(binding, command)
        if type(cancelled) is not Event or cancelled.binding != binding or cancelled.kind != 'cancelled':
            raise Conflict('explicit original cancel event required')
        stage = 'cancel_query'
        try:
            attempt = self.meter.query(command.attempt_id)
            if attempt.command != command:
                raise Conflict('original attempt changed')
            # Stop further usage first. A failed RUN write does not undo this stop.
            stage = 'usage_cancel'
            self.meter.cancel(command.run_id)
            stage = 'run_cancel'
            self.run.apply(cancelled)
            stage = 'observe'
            return self.observe(binding, command)
        except Exception as exc:
            raise ReconcileOriginal(stage) from exc

    def settle_original_fixture(self, binding, command, receipt):
        """Only explicit trusted synthetic receipt reconciliation, no execution."""
        self._binding(binding, command)
        if type(receipt) is not Receipt or receipt.attempt_id != command.attempt_id:
            raise Conflict('original trusted receipt required')
        stage = 'settlement_query'
        try:
            attempt = self.meter.query(command.attempt_id)
            if attempt.command != command:
                raise Conflict('original attempt changed')
            stage = 'settle'
            self.meter.settle(receipt)
            stage = 'observe'
            return self.observe(binding, command)
        except Exception as exc:
            raise ReconcileOriginal(stage) from exc
