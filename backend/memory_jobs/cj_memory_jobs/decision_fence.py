"""MEMORY-DECISION-FENCE@1: original accepted source comparison, no grant."""
from cj_agent.draft import trip_scope_for
from cj_trip.domain import Denied
from .decision_input import source_digest

VERSION='MEMORY-DECISION-FENCE@1'


def digest_under_lease(memory_scope,lease):
    lease.check()
    if lease.scope!=trip_scope_for(memory_scope):raise Denied('accepted decision owner differs')
    return source_digest(memory_scope,lease.decision)


def read_original_digest(boundary,token,expected_principal,memory_scope,query):
    """Return the materialized 64-byte ASCII digest under the real C boundary.

    Call before an existing Trip/Memory holder, never nest another Trip lock.
    A later effect still requires the original source version/hash holder and
    current canonical Memory history fence; this read grants neither.
    """
    def read(context):
        metadata=context.metadata
        if metadata.principal!=expected_principal or metadata.scope!=trip_scope_for(memory_scope):
            raise Denied('accepted decision owner differs')
        return context.read_decision_source(query,lambda value:source_digest(memory_scope,value).encode('ascii'),
            max_source_bytes=4_000_000,max_result_bytes=64)
    return boundary.with_operation(token,read)
