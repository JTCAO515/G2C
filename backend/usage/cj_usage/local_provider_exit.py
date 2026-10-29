"""Frozen M1 source facade over the single metered execution core."""
import json
from psycopg import Error as DatabaseError
from cj_run.step_usage import StepStore, OriginalStepOnly
from cj_run.postgres import CommitUnknown as RunCommitUnknown
from .metered_exit import MeteredExitCore, _PreparedCall, BudgetUnknown, BudgetExceeded


class LocalProviderExit(MeteredExitCore):
    def __init__(self, config, resolve_meter, *, clock, output_limits, environment):
        if (environment != 'local' or config.unit != 'provider_call'
                or set(output_limits) != {'answer','draft'}
                or any(type(v) is not int or not 1 <= v <= config.max_output for v in output_limits.values())):
            raise ValueError('explicit local provider_call limits required')
        super().__init__(config,resolve_meter,clock=clock)
        self.output_limits=dict(output_limits)

    def for_run(self, binding, state): return self

    def prepare(self, runs, binding, step_key, messages, system, provider):
        from cj_agent.provider import FakeProvider
        if not isinstance(provider,FakeProvider):
            raise BudgetUnknown('only local FakeProvider may use this exit')
        try:
            raw=json.dumps({'messages':messages,'system':system},ensure_ascii=False,
                           separators=(',',':'),allow_nan=False).encode('utf-8')
            inputs=json.loads(raw)  # private materialization, no caller-owned mutable aliases
            step=StepStore(runs,self.config).create(binding,step_key,raw,self.output_limits[step_key])
        except (OriginalStepOnly,RunCommitUnknown,DatabaseError,ValueError):
            raise BudgetUnknown('original step preparation unavailable') from None
        # Fresh, internally encoded arguments. Original reads cannot produce this call.
        def materialize():
            send=provider.stream
            return lambda:send(inputs['messages'],system=inputs['system'])
        return _PreparedCall(step,materialize,step_key,lambda:runs.valid(binding))
