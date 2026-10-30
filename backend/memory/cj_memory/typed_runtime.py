"""Typed consumer of B's original MESSAGE references and final real leases."""
from dataclasses import dataclass
from datetime import datetime,timezone

from cj_message.travel_reference import MessageContextAuthority
from .domain import Service,InvalidInput
from .postgres import Repository
from .runtime import RuntimeMemory,RuntimeDenied
from .typed import ContextRef,decode,packed
from .typed_local import TypedConfiguration
from .local_runtime import RuntimeConfiguration
from .local import read_private_policy


class TypedRuntimeMemory(RuntimeMemory):
    typed_context=True
    payload_version='MEMORY-RUN-CONSUME@2'

    def __init__(self,service,guard,selection,authority):
        super().__init__(service,guard,selection)
        self.authority=authority

    def reference_lease(self,binding):
        return self.authority.hold_for_effect(binding)

    def context_for(self,binding,lease):
        reference=lease.reference
        # B checked original owner/message/run/hash/generation/selection epoch;
        # the descriptor only selects data and grants no additional permission.
        if reference.context_kind=='none':return None
        return ContextRef(reference.context_kind,reference.context_id)


@dataclass(frozen=True)
class TypedRuntimeConfiguration:
    collection: TypedConfiguration
    selections: object

    @classmethod
    def from_bytes(cls,raw):
        value=decode(raw,maximum=262144)
        if set(value)!={'version','collection','selections'} or value['version']!='local-memory-run.2':
            raise InvalidInput('explicit typed runtime policy required')
        collection=TypedConfiguration.from_bytes(packed(value['collection']))
        legacy=RuntimeConfiguration.from_bytes(packed(dict(version='local-memory-run.1',
            collection=value['collection']['collection'],selections=value['selections'])))
        return cls(collection,legacy.selections)

    def bind(self,database,scope,identity,admit,*,message_context):
        if type(message_context) is not MessageContextAuthority or message_context.repository.scope!=scope:
            raise RuntimeDenied('canonical original context authority required')
        selection=self.selections.get(identity)
        if selection is None:raise RuntimeDenied('typed runtime identity not configured')
        profile=self.collection.collection.profiles[identity]
        def guard(stage):
            principal=admit()
            if principal.subject!=identity or profile.expires_at<=datetime.now(timezone.utc):
                raise RuntimeDenied('typed runtime policy or identity changed')
            return principal,scope
        guard('typed_runtime_bind')
        with database.connect(scope) as conn:
            conn.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(scope,))
        repository=Repository(lambda:database.connect(scope),scope,
            transaction_binder=lambda conn,cur:conn.bind_scope(cur),typed_context=True)
        return TypedRuntimeMemory(Service(repository),guard,selection,message_context)


def load_typed_runtime_configuration(path):
    return TypedRuntimeConfiguration.from_bytes(read_private_policy(path))
