"""Canonical Memory command preparation; no approval, write or execution permit."""
from cj_memory.typed import STORED_VERSION, TypedCommand, packed
from cj_message.domain import HistoryMessage
from cj_message.travel import Selection
from .extraction import CollectionUnavailable, Entry, publication_identity


def build_command(scope: str, entry: Entry, messages: tuple[HistoryMessage, ...],
                  context: Selection | None) -> TypedCommand:
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
    identities=publication_identity(scope,entry,messages,key)
    value=dict(version=STORED_VERSION,operation_id=identities.operation_id,item_id=identities.item_id,
        subject=entry.subject,slot=entry.slot,kind=entry.kind,text=entry.text,extent=entry.extent,
        context_id=identifier,context_kind=kind,context_version=version,
        source_id=identities.source_id,source_version=1,occurred_at=entry.occurred_at)
    return TypedCommand.parse(packed(value))
