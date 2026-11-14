"""Code-owned registrations over the single accounting engine."""
from cj_strict_json import compact
from dataclasses import dataclass
import json
import os
from types import MappingProxyType
from typing import Literal
from psycopg import Error as DatabaseError
from cj_run.operation_usage import OperationStore
from cj_run.step_usage import OriginalStepOnly
from cj_run.postgres import CommitUnknown as RunCommitUnknown
from .metered_exit import MeteredExitCore, _PreparedCall, BudgetUnknown
from .postgres import CommitUnknown,RepositoryUnavailable
from .codec import CorruptLedger
from .core import Blocked, Meter, run_limits


@dataclass(frozen=True)
class InvocationInput:
    original_bytes: bytes
    materialize: object
    bind_operation: object = None
    receipt: object = None
    tool_output_limit: int | None = None

    def __post_init__(self):
        if self.tool_output_limit is not None and (type(self.tool_output_limit) is not int or self.tool_output_limit < 1):
            raise ValueError('positive code-owned tool output limit required')


@dataclass(frozen=True)
class Registration:
    kind: Literal['model','tool','memory']
    prepare_input: object


def _model_input(argument):
    from cj_agent.provider import FakeProvider
    messages,system,provider=argument
    # The enabled local provider policy is an execution boundary, not a shape probe.
    if not isinstance(provider,FakeProvider):
        raise BudgetUnknown('registered model adapter permits only FakeProvider')
    try:
        raw=compact({'messages':messages,'system':system})
    except UnicodeError:
        raise BudgetUnknown('registered model input encoding unavailable') from None
    inputs=json.loads(raw)
    def materialize():
        send=provider.stream
        return lambda:send(inputs['messages'],system=inputs['system'])
    return InvocationInput(raw,materialize)


MODEL_REGISTRY=MappingProxyType({
    'model.answer':Registration('model',_model_input),
    'model.draft':Registration('model',_model_input),
    'memory.lio_extract.1':Registration('memory',_model_input),
})


class RegisteredExit(MeteredExitCore):
    def __init__(self, config, resolve_meter, *, clock, output_limits, environment, registrations):
        if (environment!='local' or config.unit!='provider_call'
                or set(output_limits)!={'model','tool','memory'}
                or any(type(v) is not int or not 1<=v<=config.max_output for v in output_limits.values())):
            raise ValueError('explicit registered local limits required')
        if registrations is None: raise ValueError('registered adapters required')
        super().__init__(config,resolve_meter,clock=clock)
        self.output_limits=dict(output_limits)
        self.registrations=MappingProxyType(dict(registrations))

    def for_run(self,binding,state): return self

    def _provider_kind(self,registration_id,registration):
        return None

    def read_run_capacity(self,binding,*,guard,max_response_bytes=4096):
        """Read original base limits under caller's live authority; not a permit."""
        from cj_run.step_usage import ledger_scope_for
        account=ledger_scope_for(binding.scope,self.config)
        meter=self._original_meter(binding,account)
        return meter.repo.read_run_capacity(binding.run_id,guard=guard,
            max_response_bytes=max_response_bytes,
            expected_period=(self.config.period_start,self.config.period_end))

    def prepare_result_publication(self,runs,binding):
        """Zero-model original clock. No operation, reserve, claim or ledger write.

        The worker captures this before started/source preparation. Running RUNs
        are never resumed through this path, so a lost clock cannot be reset.
        """
        from cj_run.step_usage import ledger_scope_for
        try:OperationStore(runs,self.config).bind_period_without_operation(binding)
        except (OriginalStepOnly,RunCommitUnknown,DatabaseError):
            raise BudgetUnknown('original zero-model period unavailable') from None
        meter=self._original_meter(binding,ledger_scope_for(binding.scope,self.config))
        try:
            with meter.repo.transaction() as ledger:previous=ledger.last_clock
        except (CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError,Blocked):
            raise BudgetUnknown('original result clock unavailable') from None
        started=self._now(previous)
        return self._deadline(started,started)

    def prepare_operation(self,runs,binding,operation_key,registration_id,argument,*,stage,reserve_final_model=False):
        try: registration=self.registrations[registration_id]
        except KeyError: raise BudgetUnknown('operation adapter is not registered') from None
        provider_kind=self._provider_kind(registration_id,registration)
        prepared_input=registration.prepare_input(argument)
        output_limit=self.output_limits[registration.kind]
        if prepared_input.tool_output_limit is not None:
            if registration.kind!='tool' or prepared_input.tool_output_limit>output_limit:
                raise BudgetUnknown('tool output limit exceeds original registered profile')
            output_limit=prepared_input.tool_output_limit
        if reserve_final_model and registration.kind=='tool':
            from cj_run.step_usage import ledger_scope_for
            from .metered_exit import BudgetExceeded
            meter=self._original_meter(binding,ledger_scope_for(binding.scope,self.config))
            try:
                with meter.repo.transaction() as ledger:
                    available=run_limits(ledger,binding.run_id).output-Meter.output_exposure(ledger,binding.run_id)-self.output_limits['model']
            except (CommitUnknown,RepositoryUnavailable,CorruptLedger,DatabaseError,Blocked):
                raise BudgetUnknown('original tool output capacity unavailable') from None
            if available<1:raise BudgetExceeded(stage)
            output_limit=min(output_limit,available)
        try:
            from .authorization_budget import HK_PRODUCER
            from .sublimits import operation_id
            extra=({'new_id':lambda:operation_id(binding.scope)}
                   if os.environ.get('CJ_M4_BUDGET_PRODUCER')==HK_PRODUCER else {})
            operation=OperationStore(runs,self.config,**extra).create(binding,operation_key,registration_id,
                registration.kind,prepared_input.original_bytes,output_limit)
        except (OriginalStepOnly,RunCommitUnknown,DatabaseError,ValueError):
            raise BudgetUnknown('original operation preparation unavailable') from None
        bind=(None if prepared_input.bind_operation is None else
              lambda guard:prepared_input.bind_operation(operation,guard))
        return _PreparedCall(operation,prepared_input.materialize,stage,lambda:runs.valid(binding),
                             receipt=prepared_input.receipt,materialize_with_guard=bind,provider_kind=provider_kind)

    def prepare(self,runs,binding,step_key,messages,system,provider):
        registration_id='model.'+step_key
        return self.prepare_operation(runs,binding,registration_id,registration_id,
                                      (messages,system,provider),stage=step_key)


class Native4RegisteredExit(RegisteredExit):
    """Installed only for an operator-qualified account and checked actual Lio4 wire."""
    TOOL_PROVIDERS=MappingProxyType({
        'tool.lio_city.1':'amap',
        'tool.lio_poi2.1':'amap',
        'tool.lio_route.1':'amap',
        'tool.visitor_fact':'local',
    })

    def __init__(self,*args,output_limits,**kwargs):
        from .core import NATIVE4_TOOL_OUTPUT,NATIVE4_MODEL_OUTPUT
        limits={kind:min(value,NATIVE4_TOOL_OUTPUT if kind=='tool'else NATIVE4_MODEL_OUTPUT)
                for kind,value in output_limits.items()}
        super().__init__(*args,output_limits=limits,**kwargs)

    def _provider_kind(self,registration_id,registration):
        if registration.kind in ('model','memory'):return 'model'
        try:return self.TOOL_PROVIDERS[registration_id]
        except KeyError:raise BudgetUnknown('native4 tool provider is not registered')from None

    def read_run_capacity(self,binding,*,guard,max_response_bytes=4096):
        from cj_run.step_usage import ledger_scope_for
        account=ledger_scope_for(binding.scope,self.config)
        meter=self._original_meter(binding,account)
        return meter.repo.read_run_capacity_v2(binding.run_id,guard=guard,
            max_response_bytes=max_response_bytes,
            expected_period=(self.config.period_start,self.config.period_end))
