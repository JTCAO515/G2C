"""Install C's explicit compatible factory without changing MSG3/ref1/payload2."""
from cj_message.domain import Unavailable
from cj_message.travel_reference import MessageContextAuthority,require_producer
from cj_message.trip_reference import profile
from cj_message.trip_context import current_source
from .composition import CompositionUnavailable


def configuration(value):
    from cj_memory.formal_runtime import FormalRuntimeConfiguration
    if type(value) is not FormalRuntimeConfiguration or value.abi!='CJ-MESSAGE-FORMAL-MEMORY@1':
        raise CompositionUnavailable('provided canonical formal Memory configuration required')
    return value


class Producer:
    def __init__(self,database,config,principal,scope,guard):
        self.database,self.config,self.principal,self.scope,self.guard=database,config,principal,scope,guard

    def require(self,tx,command):
        if tx.scope!=self.scope or not tx.trip_mode or not tx.trip_metadata or not profile(tx.cur,tx.scope):
            raise Unavailable('existing formal Trip profile and explicit consumer required')
        require_producer(tx,command)
        def admit():
            self.guard('formal_memory_producer')
            return self.principal
        authority=MessageContextAuthority(self.database.message_repository(self.scope),admit)
        # Genuine C configuration checks current policy/owner and provisions its
        # canonical Memory scope. No snapshot or caller permission is invented.
        self.config.bind(self.database,self.scope,self.principal.subject,admit,message_context=authority)
        return None if command.trip_context is None else current_source(tx.cur,tx.scope,command.trip_context)


def producer_factory(database,value):
    config=configuration(value)
    if not database.travel_context or not database.trip_context or database.edit_configuration is not None:
        raise CompositionUnavailable('explicit formal/travel host required, separate from scoped edit')
    def resolve(principal,scope,guard):return Producer(database,config,principal,scope,guard)
    return resolve
