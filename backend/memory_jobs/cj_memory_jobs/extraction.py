"""Untrusted model-output boundary. Parsed data is never a collection/save permit."""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Callable

from cj_memory.domain import InvalidInput as MemoryInvalidInput, strict_object
from cj_message.domain import HistoryMessage


class InvalidExtraction(ValueError): pass
class CollectionUnavailable(Exception): pass


@dataclass(frozen=True)
class Evidence:
    message_id: str
    quote: str


@dataclass(frozen=True)
class Entry:
    subject: str
    slot: str
    kind: str
    text: str
    extent: str
    occurred_at: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class ParsedEntry:
    entry: Entry
    direct_statement: bool
    # Classification data only: publisher must reacquire current source/Memory
    # fences and commit a real MEMORY receipt before reporting saved/active.


@dataclass(frozen=True)
class PublicationIdentity:
    operation_id: str
    item_id: str
    source_id: str


def publication_identity(scope: str, entry: Entry,
                         messages: tuple[HistoryMessage, ...],
                         context_key: tuple[str,str] | None) -> PublicationIdentity:
    """Stable data keys, independent of task, mode, output wording and language.

    The accepted original message revisions and canonical subject/slot/context
    determine identity. A changed model value/kind must conflict on original bytes,
    not mint another item to evade the same-source rule. No key grants authority.
    """
    source={row.receipt.message_id:row.receipt for row in messages}
    references=[]
    for evidence in entry.evidence:
        row=source[evidence.message_id]
        references.append((row.conversation_id,row.generation,row.sequence,row.message_id,row.input_sha256))
    value=dict(version='MEMORY-PUBLICATION-IDENTITY@1',scope_digest=sha256(scope.encode('utf-8')).hexdigest(),
               references=sorted(references),subject=entry.subject,slot=entry.slot,
               extent=entry.extent,context=context_key)
    digest=sha256(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('ascii')).hexdigest()
    return PublicationIdentity('history-op-v1:'+digest,'history-item-v1:'+digest,'history-v1:'+digest)


@dataclass(frozen=True)
class CollectionPolicy:
    """Trusted synchronous bounded policy checks; no provider/network work here."""
    subjects: frozenset[str]
    slots: frozenset[str]
    max_entries: int
    max_text_bytes: int
    content_allowed: Callable[[Entry], bool]
    direct_statement: Callable[[Entry, tuple[HistoryMessage, ...]], bool]

    def __post_init__(self):
        for values in (self.subjects,self.slots):
            if (type(values) is not frozenset or not values
                    or any(type(v) is not str or not v.strip() for v in values)):
                raise ValueError('explicit canonical collection references required')
        if (type(self.max_entries) is not int or not 1<=self.max_entries<=100
                or type(self.max_text_bytes) is not int or not 1<=self.max_text_bytes<=4096
                or self.content_allowed is None or self.direct_statement is None):
            raise ValueError('explicit collection limits and policy required')


def _text(value, limit):
    if type(value) is not str or not value.strip() or '\0' in value:
        raise InvalidExtraction('bounded exact model text required')
    try:
        if len(value.encode('utf-8'))>limit:
            raise InvalidExtraction('model text exceeds bound')
    except UnicodeError:
        raise InvalidExtraction('invalid model text Unicode') from None
    return value


def _model_value(raw):
    if type(raw) is not bytes or not 0<len(raw)<=16384:
        raise InvalidExtraction('bounded original model bytes required')
    try:
        value=strict_object(raw)
    except (MemoryInvalidInput,RecursionError):
        raise InvalidExtraction('invalid extraction JSON') from None
    return value


def _value_entries(value,messages,max_entries,max_text_bytes,selector,*,quote_texts=None):
    if (type(value) is not dict or set(value)!={'version','entries'}
            or value['version']!='MEMORY-EXTRACT@1' or type(value['entries']) is not list
            or len(value['entries'])>max_entries):
        raise InvalidExtraction('explicit extraction envelope required')
    source={row.receipt.message_id:row for row in messages}
    seen=set()
    for item in value['entries']:
        fields={'subject','slot','kind','text','extent','occurred_at','evidence'}
        if type(item) is not dict or set(item)!=fields:
            raise InvalidExtraction('explicit extraction entry required')
        subject=_text(item['subject'],4096);slot=_text(item['slot'],4096)
        kind=_text(item['kind'],32);extent=_text(item['extent'],32)
        if kind not in ('fact','experience','preference','inference') or extent not in ('long_term','current'):
            raise InvalidExtraction('unsupported extraction kind or extent')
        if selector is not None:selector(subject,slot)
        key=subject,slot,extent
        if key in seen:
            raise InvalidExtraction('duplicate canonical extraction slot')
        seen.add(key)
        refs=item['evidence']
        if type(refs) is not list or not 1<=len(refs)<=len(messages):
            raise InvalidExtraction('explicit source evidence required')
        evidence=[];used=set()
        for ref in refs:
            if type(ref) is not dict or set(ref)!={'message_id','quote'}:
                raise InvalidExtraction('exact evidence reference required')
            mid=_text(ref['message_id'],32768)
            quote=_text(ref['quote'],max_text_bytes)
            if mid in used or mid not in source:
                raise InvalidExtraction('evidence does not match original source')
            text=source[mid].text if quote_texts is None else quote_texts[mid,quote]
            if quote not in text:
                raise InvalidExtraction('evidence does not match original source')
            used.add(mid);evidence.append(Evidence(mid,quote))
        entry=Entry(subject,slot,kind,_text(item['text'],max_text_bytes),extent,
                    _text(item['occurred_at'],4096),tuple(evidence))
        yield entry


def decode_output(raw: bytes, messages: tuple[HistoryMessage, ...]) -> tuple[Entry,...]:
    """Intrinsic stored-data decoding only; never approval or directness.

    Historical receipt reads compare these data to actual canonical operations;
    every new publication still uses parse_output with its explicit live policy.
    """
    return _decode_value(_model_value(raw),messages)


def _decode_value(value,messages,*,quote_texts=None):
    return tuple(_value_entries(value,messages,100,4096,None,quote_texts=quote_texts))


def parse_output(raw: bytes, messages: tuple[HistoryMessage, ...],
                 policy: CollectionPolicy) -> tuple[ParsedEntry, ...]:
    """Classify under explicit policy, without creating a collection/save permit."""
    return _parse_value(_model_value(raw),messages,policy)


def _parse_value(value,messages,policy,*,quote_texts=None,direct_statement=None):
    source={row.receipt.message_id:row for row in messages}
    def selector(subject,slot):
        if subject not in policy.subjects or slot not in policy.slots:
            raise CollectionUnavailable('canonical collection scope unavailable')
    result=[]
    classify=policy.direct_statement if direct_statement is None else direct_statement
    for entry in _value_entries(value,messages,policy.max_entries,policy.max_text_bytes,selector,quote_texts=quote_texts):
        if policy.content_allowed(entry) is not True:
            raise CollectionUnavailable('content collection unavailable')
        # Model kind/quote cannot certify explicit consent. A trusted policy must
        # independently classify source statements, and inference never promotes.
        direct=(entry.kind!='inference' and classify(entry,
                tuple(source[e.message_id] for e in entry.evidence)) is True)
        result.append(ParsedEntry(entry,direct))
    return tuple(result)
