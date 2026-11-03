"""Explicit formal-reference consumer; a Trip never grants a Travel namespace."""
from dataclasses import dataclass
from typing import ClassVar

from cj_api.local_app import scope_for
from cj_message.travel_reference import MessageContextAuthority
from .domain import InvalidInput
from .runtime import RuntimeDenied
from .typed import ContextRef,decode,packed
from .typed_runtime import TypedRuntimeConfiguration,TypedRuntimeMemory,_bind_runtime
from .local import read_private_policy


class FormalRuntimeMemory(TypedRuntimeMemory):
    def context_for(self,binding,lease):
        reference=lease.reference
        if reference.context_kind in ('none','trip'):return None
        if reference.context_kind=='travel':return ContextRef('travel',reference.context_id)
        raise RuntimeDenied('explicit formal/Travel/none original reference required')


@dataclass(frozen=True)
class FormalRuntimeConfiguration(TypedRuntimeConfiguration):
    abi:ClassVar[str]='CJ-MESSAGE-FORMAL-MEMORY@1'

    @classmethod
    def from_bytes(cls,raw):
        value=decode(raw,maximum=262144)
        if set(value)!={'version','collection','selections'} or value['version']!='local-memory-formal-run.1':
            raise InvalidInput('explicit formal runtime Memory policy required')
        original=TypedRuntimeConfiguration.from_bytes(packed(dict(value,version='local-memory-run.2')))
        return cls(original.collection,original.selections)

    def bind(self,database,scope,identity,admit,*,message_context):
        return self._bind(database,scope,identity,admit,message_context,provision=True)

    def bind_readonly(self,database,scope,identity,admit,*,message_context):
        return self._bind(database,scope,identity,admit,message_context,provision=False)

    def _bind(self,database,scope,identity,admit,message_context,*,provision):
        if type(message_context) is not MessageContextAuthority or message_context.repository.scope!=scope:
            raise RuntimeDenied('canonical original formal-reference authority required')
        def current_principal():
            principal=admit()
            if scope_for(principal.issuer,principal.subject)!=scope:raise RuntimeDenied('formal Memory principal/owner mismatch')
            return principal
        return _bind_runtime(self,FormalRuntimeMemory,database,scope,identity,current_principal,message_context,provision=provision)


def load_formal_runtime_configuration(path):
    return FormalRuntimeConfiguration.from_bytes(read_private_policy(path))
