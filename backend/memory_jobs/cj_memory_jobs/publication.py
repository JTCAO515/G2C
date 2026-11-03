"""Canonical Memory command preparation; no approval, write or execution permit."""
from cj_memory.domain import Conflict, Unavailable
from cj_memory.typed import STORED_VERSION, TypedCommand, packed
from cj_message.domain import HistoryMessage
from cj_message.travel import Selection
from .extraction import CollectionUnavailable, Entry, publication_identity


def build_command(scope: str, entry: Entry, messages: tuple[HistoryMessage, ...],
                  context: Selection | None,*,identities=None) -> TypedCommand:
    """Use a server-resolved context, never context/owner fields from model JSON.

    The caller still needs the accepted current B lease and canonical MEMORY
    transaction. Prepared commands/source IDs alone cannot authorize publication.
    Current values without a resolved travel scope are not made long-term.
    """
    if entry.extent=='long_term':
        if context is not None:
            raise CollectionUnavailable('long-term collection cannot use a current context')
        kind,identifier,version,key='legacy',None,None,None
    else:
        if context is None:
            raise CollectionUnavailable('current collection requires a resolved travel scope')
        kind,identifier,version='travel',context.id,context.expected_version
        key=('travel',identifier)
    if identities is None:identities=publication_identity(scope,entry,messages,key)
    value=dict(version=STORED_VERSION,operation_id=identities.operation_id,item_id=identities.item_id,
        subject=entry.subject,slot=entry.slot,kind=entry.kind,text=entry.text,extent=entry.extent,
        context_id=identifier,context_kind=kind,context_version=version,
        source_id=identities.source_id,source_version=1,occurred_at=entry.occurred_at)
    return TypedCommand.parse(packed(value))


def publish_command(memory_transaction, command: TypedCommand, collection_policy,
                    *, direct_statement: bool, context_lease=None):
    """Write on the caller's live canonical source/MEMORY transaction only.

    The trusted producer has freshly parsed/classified the original result under
    MESSAGE-SOURCE. This function does not open/commit a transaction or dispatch.
    The exact generated command is the original MEMORY operation input; history
    task/provider bytes remain in the original task ledger, never substituted.
    """
    tx=memory_transaction
    old=tx.operation(command.operation_id)
    if old is not None:
        if old[0]!=command.raw:
            raise Conflict('original history Memory operation differs')
        return old[1]  # Historical data, not renewed approval or source activation.
    if not tx.typed_context:
        raise Unavailable('typed canonical Memory storage required')
    if command.extent=='current':
        if context_lease is None:
            raise Unavailable('current history publication requires the real travel lease')
        context_lease.check()
        if context_lease.context!=Selection(command.context_id,command.context_version):
            raise Unavailable('history publication travel selection differs')
    resolved=collection_policy.evaluate(command,command.raw)
    confirmed=direct_statement is True and command.kind!='inference'
    tx.cur.execute('''INSERT INTO cj_memory_source
        (scope,source_id,version,approved_input,authorized,confirmed,semantic_resolved,active,expires_at)
        VALUES(%s,%s,1,%s,true,%s,%s,true,%s) ON CONFLICT(scope,source_id) DO NOTHING''',
        (tx.scope,command.source_id,command.raw,confirmed,resolved,collection_policy.expires_at))
    if tx.cur.rowcount!=1:
        raise Conflict('history source exists without its original operation')
    current=tx.source(command)
    result=tx.insert(command,'active' if current and command.kind!='inference' else 'candidate')
    if command.extent=='current':context_lease.check()
    return result
