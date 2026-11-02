"""MESSAGE-SOURCE-STATUS@1: owned head/end metadata, never a collection grant."""
from dataclasses import dataclass
from .domain import Cursor,Unavailable
from .source import ConversationEnd,EndQuery,_end,_identity

VERSION='MESSAGE-SOURCE-STATUS@1'


@dataclass(frozen=True,repr=False)
class SourceStatus:
    cursor:Cursor
    conversation_type:str
    end:ConversationEnd|None


def read_status(service,conversation_id):
    _identity(conversation_id)
    with service.repository.transaction() as tx:
        tx.lock_scope()
        head=tx.chat(conversation_id)
        tx.cur.execute('SELECT conversation_type::text,end_id,end_generation,end_epoch,end_sequence '
            'FROM cj_message_chat WHERE scope=%s AND conversation_id=%s',(tx.scope,conversation_id))
        row=tx.cur.fetchone()
        if row is None or len(row)!=5 or row[0]!='travel':raise Unavailable('source status unavailable')
        end=None if all(value is None for value in row[1:]) else _end(tx,
            EndQuery(conversation_id,head.generation,head.epoch,head.last_sequence))
        result=SourceStatus(Cursor(tx.scope,conversation_id,head.generation,head.epoch,head.last_sequence,0),row[0],end)
    return result
