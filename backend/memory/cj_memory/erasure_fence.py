"""MEMORY-HISTORY-ERASURE-FENCE@1 for trusted original runtime coordinates."""
from dataclasses import dataclass
from hashlib import sha256
import json

from .domain import InvalidInput
from .runtime import RuntimeDenied,RuntimeRun

VERSION='MEMORY-HISTORY-ERASURE-FENCE@1'


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
                if type(value) is not str or not value.strip() or len(value)>4096 or '\0' in value:
                    raise InvalidInput('invalid original runtime identifier')
                try:value.encode('utf-8')
                except UnicodeError as error:raise InvalidInput('invalid original runtime identifier') from error
            if type(ref['sequence']) is not int or not 1<=ref['sequence']<=2**63-1:
                raise InvalidInput('invalid original message sequence')
            digest(ref['input_sha256'])
        if type(decision_source_sha256s) is not list or len(decision_source_sha256s)>1000:
            raise InvalidInput('bounded original decision references required')
        for value in decision_source_sha256s:digest(value)
        hashes=frozenset(sha256(json.dumps(ref,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
                         for ref in message_refs)
        return cls(hashes,frozenset(decision_source_sha256s))

    def require_current(self,tx):
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
