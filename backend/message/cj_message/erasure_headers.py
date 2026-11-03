"""MESSAGE-ERASURE-HEADERS@1: complete owned metadata under MESSAGE scope lock."""
from dataclasses import dataclass,asdict
from threading import get_ident
import inspect

from .domain import InvalidInput,Unavailable

VERSION='MESSAGE-ERASURE-HEADERS@1'
MAX_REFS=10000
MAX_RESULT_BYTES=8_388_608


@dataclass(frozen=True)
class MessageReference:
    conversation_id:str
    generation:str
    sequence:int
    message_id:str
    input_sha256:str

    def to_dict(self):return asdict(self)


class HeaderSnapshot:
    """Callback-lifetime observation, never consent or future execution authority."""
    version=VERSION

    def __init__(self,principal,scope,references,check_context):
        self._principal,self._scope,self._references=principal,scope,references
        self._check_context=check_context
        self._thread=get_ident();self._active=True

    def check(self):
        if not self._active or get_ident()!=self._thread:raise Unavailable('erasure metadata lifetime unavailable')
        self._check_context()

    @property
    def principal(self):self.check();return self._principal

    @property
    def scope(self):self.check();return self._scope

    @property
    def references(self):self.check();return self._references

    @property
    def complete(self):self.check();return True


def _identity(value):
    if type(value) is not str or not value.strip() or '\0' in value:
        raise Unavailable('original message metadata unavailable')
    return value


def _current(cursor,scope):
    cursor.execute('SELECT current_user,public.cj_account_scope_current(%s)',(scope,))
    if cursor.fetchone()!=('cj_m1_runtime',True):raise Unavailable('current runtime account required')


def with_headers(service,principal,project,*,max_refs,max_result_bytes,check_context,admit):
    if (type(max_refs) is not int or not 1<=max_refs<=MAX_REFS
            or type(max_result_bytes) is not int or not 1<=max_result_bytes<=MAX_RESULT_BYTES):
        raise InvalidInput('explicit bounded erasure metadata limits required')
    snapshot=None
    with service.repository.transaction() as tx:
        _current(tx.cur,tx.scope)
        # Declare only the already-implemented shared-table read compatibility.
        # Restore before any caller/C callback; scope/account RLS stays active.
        tx.cur.execute("SELECT current_setting('cj.message_edit_result_abi',true)")
        previous=tx.cur.fetchone()[0]
        from .edit_result_protocol import CONFIGURATION_ABI
        tx.cur.execute("SELECT set_config('cj.message_edit_result_abi',%s,true)",(CONFIGURATION_ABI,))
        tx.lock_scope()
        references=_references(tx,max_refs)
        tx.cur.execute("SELECT set_config('cj.message_edit_result_abi',%s,true)",(previous,))
        admit('erasure_headers_before_callback')
        _current(tx.cur,tx.scope)
        snapshot=HeaderSnapshot(principal,tx.scope,tuple(references),check_context)
        try:
            result=project(snapshot)
            if type(result) is not bytes:
                if inspect.iscoroutine(result):result.close()
                raise Unavailable('materialized synchronous metadata callback required')
            if len(result)>max_result_bytes:raise Unavailable('erasure metadata result exceeds byte bound')
            snapshot.check()
            _current(tx.cur,tx.scope)
            admit('erasure_headers_after_callback')
        finally:snapshot._active=False
    return result


def _references(tx,max_refs):
    # Include nonempty heads and every unsupported kind, including inactive
    # chats. Empty travel chats have no original message references to freeze.
    tx.cur.execute("SELECT conversation_id,generation,last_sequence,conversation_type::text FROM cj_message_chat "
        "WHERE scope=%s AND (last_sequence>0 OR conversation_type::text<>'travel') "
        'ORDER BY conversation_id COLLATE "C",generation COLLATE "C" LIMIT %s',(tx.scope,max_refs+1))
    heads={};total=0
    for cid,generation,through,kind in tx.cur.fetchall():
        _identity(cid);_identity(generation)
        if kind!='travel' or type(through) is not int or not 1<=through<=2**63-1:
            raise Unavailable('original message head unavailable')
        total+=through
        if total>max_refs:raise Unavailable('complete erasure metadata exceeds reference bound')
        heads[cid,generation]=through
    tx.cur.execute('SELECT conversation_id,generation,sequence,message_id,input_sha256,encode(sha256(raw_input),\'hex\') '
        'FROM cj_message_receipt WHERE scope=%s ORDER BY conversation_id COLLATE "C",generation COLLATE "C",sequence LIMIT %s',
        (tx.scope,max_refs+1))
    references=[];seen={}
    for cid,generation,sequence,mid,stored_sha,actual_sha in tx.cur.fetchall():
        _identity(cid);_identity(generation);_identity(mid)
        key=(cid,generation)
        if (key not in heads or type(sequence) is not int or sequence!=seen.get(key,0)+1
                or sequence>heads[key] or type(stored_sha) is not str or stored_sha!=actual_sha):
            raise Unavailable('original message coordinates or digest unavailable')
        seen[key]=sequence
        references.append(MessageReference(cid,generation,sequence,mid,stored_sha))
        if len(references)>max_refs:raise Unavailable('complete erasure metadata exceeds reference bound')
    if len(references)!=total or seen!=heads:raise Unavailable('complete original message metadata unavailable')
    return tuple(references)
