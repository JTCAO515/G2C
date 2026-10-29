"""Code-owned registrations over the single accounting engine."""
from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Literal
from psycopg import Error as DatabaseError
from cj_run.operation_usage import OperationStore
from cj_run.step_usage import OriginalStepOnly
from cj_run.postgres import CommitUnknown as RunCommitUnknown
from .metered_exit import MeteredExitCore, _PreparedCall, BudgetUnknown


@dataclass(frozen=True)
class InvocationInput:
    original_bytes: bytes
    materialize: object


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
        raw=json.dumps({'messages':messages,'system':system},ensure_ascii=False,
                       separators=(',',':'),allow_nan=False).encode('utf-8')
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

    def prepare_operation(self,runs,binding,operation_key,registration_id,argument,*,stage):
        try: registration=self.registrations[registration_id]
        except KeyError: raise BudgetUnknown('operation adapter is not registered') from None
        prepared_input=registration.prepare_input(argument)
        try:
            operation=OperationStore(runs,self.config).create(binding,operation_key,registration_id,
                registration.kind,prepared_input.original_bytes,self.output_limits[registration.kind])
        except (OriginalStepOnly,RunCommitUnknown,DatabaseError,ValueError):
            raise BudgetUnknown('original operation preparation unavailable') from None
        return _PreparedCall(operation,prepared_input.materialize,stage,lambda:runs.valid(binding))

    def prepare(self,runs,binding,step_key,messages,system,provider):
        registration_id='model.'+step_key
        return self.prepare_operation(runs,binding,registration_id,registration_id,
                                      (messages,system,provider),stage=step_key)
