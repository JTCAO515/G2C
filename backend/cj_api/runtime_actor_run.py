"""Native simulator RUN custody, without admitting a product MESSAGE.

The B composition supplies the original account, AUTH/window/pin guard, a
protected DUT observation and an existing owner-only canonical directory. This
module does not create accounts, profiles, providers or another fee journal.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import time

from cj_agent.provider import ProviderFailed, ProviderUnknown
from cj_agent.worker import RunWorker, _Stopped
from cj_run.core import Service, TERMINAL
from cj_run.step_usage import ledger_scope_for
from cj_usage.core import Meter
from cj_usage.metered_exit import BudgetExceeded, BudgetUnknown
from cj_usage.postgres import PostgresRepository
from cj_usage.registered_exit import RegisteredExit
from runtime_adapter.contract import Unavailable

from .runtime_actor import ActorInput, OPERATION, REGISTRATION, actor_registration
from .runtime_claims import CanonicalClaims


@dataclass(frozen=True)
class RetainedActorRun:
    """Read-only original after a restart; has no dispatch capability or exit."""
    argument: ActorInput
    claim: object
    repository: object
    guard: object

    def inspect(self):
        self.guard(read_only=True, purpose='query')
        self.claim.read(self.argument.binding.message_id)
        state = self.repository.snapshot_optional(self.argument.binding)
        self.guard(read_only=True, purpose='query')
        return state


class ActorClaim(CanonicalClaims):
    """A new typed purpose over the accepted canonical O_EXCL claim mechanism."""
    def __init__(self, directory, original_binding, argument, *, guard, repository):
        self.argument = argument
        @contextmanager
        def admission():
            with repository.worker_lease(argument.binding) as check:
                if check is None:
                    raise Unavailable('ACTOR_ORIGINAL_BUSY')
                check()
                yield
                check()
        super().__init__(directory, original_binding, argument.specification, guard=guard,
            original_exists=lambda step: repository.snapshot_optional(argument.binding) is not None,
            admission_lock=admission)

    def _request(self, raw):
        # Both values came through the ActorInput trust boundary. Equality also
        # rejects changed source/prompt/choice schema under the same original ID.
        if raw != self.argument.original():
            raise Unavailable('ACTOR_ORIGINAL_INPUT_CHANGED')
        import json
        return json.loads(raw)


class NativeActorRun:
    """One registered model operation; interrupted originals are query-only."""
    def __init__(self, database, tools, argument, claim, *, guard, profile):
        if type(argument) is not ActorInput or claim.argument != argument:
            raise ValueError('same typed original actor required')
        self.database, self.tools, self.argument, self.claim = database, tools, argument, claim
        self.guard, self.profile = guard, profile
        # Existing original account only. This validates v1/v2 bytes and never
        # provisions or converts an account, and does not select native4 limits.
        database.require_budget_account(argument.binding.scope, profile=profile)
        self.repository = database.run_repository(argument.binding.scope, usage_profile=profile)
        self.runs = Service(self.repository, self._valid)
        def meter(binding, account):
            if binding != argument.binding or account != ledger_scope_for(binding.scope, profile.meter):
                raise BudgetUnknown('original actor account changed')
            return Meter(PostgresRepository(lambda: database.connect(binding.scope, usage_profile=profile),
                account, read_binder=lambda connection, cursor: connection.bind_scope(cursor)), profile.meter, time.time)
        self.exit = RegisteredExit(profile.meter, meter, clock=time.time,
            output_limits=profile.output_limits, environment='local',
            registrations={REGISTRATION: actor_registration(tools, argument.specification)})

    def _valid(self, binding):
        if binding != self.argument.binding:
            return False
        self.guard(read_only=True, purpose='query')
        self.claim.read(binding.message_id)
        self.argument.check()
        return True

    def dispatch(self, capability):
        """A capability is consumed once before native RUN acceptance.

        No capability is recreated after a lost ACK. A retained running RUN is
        stopped UNKNOWN; no supplier call is replayed or refunded here.
        """
        argument = self.argument
        self.claim.consume(argument.original(), capability)
        self.guard(read_only=False, purpose='actor')
        with self.repository.worker_lease(argument.binding) as owned:
            if owned is None:
                raise Unavailable('ACTOR_ORIGINAL_BUSY')
            owned()
            repository = self.repository
            class OwnedRepository:
                @contextmanager
                def transaction(self):
                    with repository.transaction() as transaction:
                        owned()
                        yield transaction
                        owned()
                    owned()
            def valid(binding):
                owned()
                return self._valid(binding)
            runs = Service(OwnedRepository(), valid)
            state = runs.accept(argument.binding)
            worker = RunWorker(scope=argument.binding.scope, messages=None, runs=runs,
                provider=self.tools.services.model, budget_exit=self.exit)
            if state.status in TERMINAL:
                return state
            if state.status == 'running':
                return worker._event(argument.binding, state, 'unknown')
            try:
                state = worker._event(argument.binding, state, 'started')
                self.guard(read_only=False, purpose='actor')
                for chunk in worker._registered_stream(argument.binding, OPERATION, REGISTRATION, argument):
                    owned()
                    if chunk:
                        state = worker._event(argument.binding, state, 'text_delta', chunk)
                owned()
                state = worker._event(argument.binding, state, 'completed')
            except BudgetExceeded:
                state = worker._budget_rejection(argument.binding, 'answer')
            except ProviderFailed:
                state = worker._event(argument.binding, self.runs.snapshot(argument.binding), 'failed')
            except (ProviderUnknown, BudgetUnknown, Unavailable):
                current = self.runs.snapshot(argument.binding)
                if current.status in TERMINAL:
                    return current
                if current.status != 'running':
                    raise
                state = worker._event(argument.binding, current, 'unknown')
            except _Stopped as stopped:
                state = stopped.state
            # Database/commit ACK errors propagate unchanged: inspect the same
            # original RUN/operation/financial attempt rather than dispatch again.
            return state

    def inspect(self):
        # Status/fees remain queryable under current actor ownership even after
        # the DUT source is gone. This method does not return copied DUT input.
        self.guard(read_only=True, purpose='query')
        self.claim.read(self.argument.binding.message_id)
        state = self.repository.snapshot_optional(self.argument.binding)
        self.guard(read_only=True, purpose='query')
        return state
