"""MEMORY-HISTORY-ERASURE-FENCE@1 for trusted original runtime coordinates."""
from cj_strict_json import compact
from dataclasses import dataclass
from hashlib import sha256
import json

from .domain import InvalidInput
from .runtime import RuntimeDenied,RuntimeRun

VERSION='MEMORY-HISTORY-ERASURE-FENCE@1'
_COVERAGE_TAG=b'MEMORY-ERASURE-CAPTURE-COMPLETE@1\0'


def coverage_reference(operation):
    # This is an internal completed control action, not a client action ID.
    # Its NUL-separated namespace cannot alias a legal original client ID.
    return sha256(_COVERAGE_TAG+operation.encode('utf-8')).hexdigest()


def record_coverage(memory,operation,selection,association):
    memory.cur.execute('''INSERT INTO cj_memory_erasure_fence
        (scope_digest,kind,reference_sha256,original_input_sha256,operation_id,item_version,scope_epoch)
        VALUES(%s,'action',%s,%s,%s,%s,%s)''',
        (sha256(memory.scope.encode()).hexdigest(),coverage_reference(operation),sha256(association).hexdigest(),
         operation,selection['item_version'],selection['scope_epoch']))


def require_coverage(cursor,scope,operation,item_version,scope_epoch,association=None):
    cursor.execute('''SELECT original_input_sha256,operation_id,item_version,scope_epoch FROM cj_memory_erasure_fence
        WHERE scope_digest=%s AND kind='action' AND reference_sha256=%s''',
        (sha256(scope.encode()).hexdigest(),coverage_reference(operation)))
    row=cursor.fetchone()
    if (row is None or row[1:]!=(operation,item_version,scope_epoch)
            or association is not None and row[0]!=sha256(association).hexdigest()):
        raise RuntimeDenied('original erasure history capture is incomplete')
    if association is not None:
        original=json.loads(association)
        references={sha256(compact(ref, sort_keys=True, ensure_ascii=True, allow_nan=True)).hexdigest()
                    for ref in original['message_refs']}
        cursor.execute("SELECT count(*) FROM cj_memory_erasure_fence WHERE scope_digest=%s AND kind='message' AND reference_sha256=ANY(%s)",
            (sha256(scope.encode()).hexdigest(),list(references)))
        if cursor.fetchone()!=(len(references),):raise RuntimeDenied('original history fence inventory is incomplete')


def require_complete_erasure_actions(tx):
    tx.cur.execute('''SELECT 1 FROM cj_memory_erasure_fence a WHERE a.scope_digest=%s AND a.kind='action'
        AND a.reference_sha256<>encode(sha256(%s::bytea || convert_to(a.operation_id,'UTF8')),'hex')
        AND NOT EXISTS(SELECT 1 FROM cj_memory_erasure_fence c
            WHERE (c.scope_digest,c.kind,c.operation_id,c.item_version,c.scope_epoch)=
                  (a.scope_digest,'action',a.operation_id,a.item_version,a.scope_epoch)
              AND c.reference_sha256=encode(sha256(%s::bytea || convert_to(a.operation_id,'UTF8')),'hex')) LIMIT 1''',
        (sha256(tx.scope.encode()).hexdigest(),_COVERAGE_TAG,_COVERAGE_TAG))
    if tx.cur.fetchone() is not None:raise RuntimeDenied('original erasure history capture is incomplete')


@dataclass(frozen=True)
class References:
    messages:frozenset[str]
    decisions:frozenset[str]

    def union(self,other):
        messages=self.messages|other.messages;decisions=self.decisions|other.decisions
        if len(messages)>10000 or len(decisions)>1000:raise InvalidInput('combined original history references exceed bound')
        return References(messages,decisions)

    @classmethod
    def capture(cls,message_refs,decision_source_sha256s):
        # The host supplies ALL original context coordinates, never model text
        # or caller-provided permission flags. Copy to immutable digest sets.
        def digest(value):
            if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise InvalidInput('invalid original runtime digest')
        if type(message_refs) is not list or len(message_refs)>10000:raise InvalidInput('bounded original message references required')
        for ref in message_refs:
            if type(ref) is not dict or set(ref)!={'conversation_id','generation','sequence','message_id','input_sha256'}:
                raise InvalidInput('exact original message coordinates required')
            for key in ('conversation_id','generation','message_id'):
                value=ref[key]
                if type(value) is not str or not value.strip() or '\0' in value:
                    raise InvalidInput('invalid original runtime identifier')
                try:value.encode('utf-8')
                except UnicodeError as error:raise InvalidInput('invalid original runtime identifier') from error
            if type(ref['sequence']) is not int or not 1<=ref['sequence']<=2**63-1:
                raise InvalidInput('invalid original message sequence')
            digest(ref['input_sha256'])
        if type(decision_source_sha256s) is not list or len(decision_source_sha256s)>1000:
            raise InvalidInput('bounded original decision references required')
        for value in decision_source_sha256s:digest(value)
        hashes=frozenset(sha256(compact(ref, sort_keys=True, ensure_ascii=True, allow_nan=True)).hexdigest()
                         for ref in message_refs)
        return cls(hashes,frozenset(decision_source_sha256s))

    def require_current(self,tx):
        require_complete_erasure_actions(tx)
        tx.cur.execute('''SELECT 1 FROM cj_memory_erasure_fence WHERE scope_digest=%s
            AND ((kind='message' AND reference_sha256=ANY(%s)) OR (kind='decision' AND reference_sha256=ANY(%s))) LIMIT 1''',
            (sha256(tx.scope.encode()).hexdigest(),list(self.messages),list(self.decisions)))
        if tx.cur.fetchone() is not None:raise RuntimeDenied('original model history contains erased Memory evidence')


class HistoryRuntimeRun(RuntimeRun):
    """Same canonical Memory/MESSAGE lease plus original history erasure check."""
    erasure_protocol=VERSION
    def __init__(self,original,references):
        super().__init__(original.owner,original.binding,original.principal,original.snapshot,original.payload,context=original.context)
        self.references=references

    def _check_additional(self,tx):
        self.references.require_current(tx)

    def _merge_history(self,references):
        return self.references.union(references)
