"""CJ-MESSAGE-EDIT-MEMORY@1; original typed eligibility and currentness only."""
from dataclasses import dataclass
from typing import ClassVar
from cj_message.edit_protocol import MEMORY_ABI
from cj_message.edit_reference import EditAuthority
from cj_api.local_app import scope_for
from .domain import InvalidInput
from .runtime import RuntimeDenied
from .typed import ContextRef,decode,packed
from .typed_runtime import TypedRuntimeConfiguration,TypedRuntimeMemory,_bind_runtime
from .local import read_private_policy


class EditRuntimeMemory(TypedRuntimeMemory):
    def reference_lease(self,binding):
        # Capture must release Trip SHARE before waiting for Memory. During
        # publication the authority reuses its actual active same-cursor lease.
        return self.authority.hold_for_effect(binding,source_lock=False)

    def context_for(self,binding,lease):
        namespace=lease.memory_namespace
        namespace.check(binding)
        if namespace.kind!='travel':raise RuntimeDenied('actual travel namespace required')
        return ContextRef('travel',namespace.id)


@dataclass(frozen=True)
class EditRuntimeConfiguration(TypedRuntimeConfiguration):
    abi:ClassVar[str]=MEMORY_ABI

    @classmethod
    def from_bytes(cls,raw):
        value=decode(raw,maximum=262144)
        if set(value)!={'version','collection','selections'} or value['version']!='local-memory-edit-run.1':
            raise InvalidInput('explicit edit runtime memory policy required')
        original=TypedRuntimeConfiguration.from_bytes(packed(dict(value,version='local-memory-run.2')))
        return cls(original.collection,original.selections)

    def bind(self,database,scope,identity,admit,*,message_context):
        return self._bind(database,scope,identity,admit,message_context,provision=True)

    def bind_readonly(self,database,scope,identity,admit,*,message_context):
        return self._bind(database,scope,identity,admit,message_context,provision=False)

    def _bind(self,database,scope,identity,admit,message_context,*,provision):
        if type(message_context) is not EditAuthority or message_context.repository.scope!=scope:
            raise RuntimeDenied('canonical original edit authority required')
        def current_principal():
            principal=admit()
            if scope_for(principal.issuer,principal.subject)!=scope:
                raise RuntimeDenied('edit memory principal/owner mismatch')
            return principal
        return _bind_runtime(self,EditRuntimeMemory,database,scope,identity,current_principal,message_context,provision=provision)


def load_edit_runtime_configuration(path):
    return EditRuntimeConfiguration.from_bytes(read_private_policy(path))
