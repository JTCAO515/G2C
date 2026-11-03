"""Explicit immutable comparison artifact; decoded decisions grant no lease."""
from hashlib import sha256
import json

from cj_memory.domain import strict_object,InvalidInput as MemoryInvalid
from cj_trip.decision_source import AcceptedDecision
from cj_trip.domain import identifier,packed
from cj_trip.structured import validate_document as validate_v1
from cj_trip.structured_v2 import validate_document as validate_v2
from .codec import SourceV2,InvalidInput,encode_v2,decode_v2
from .postgres import encode as canonical
from .decision_input import source_digest

VERSION='CJ020-decision.1'
FIELDS={'trip_id','version','content_sha256','action_id','proposal_id','candidate_hash','content_utf8'}


def _decision(value):
    if type(value) is not dict or set(value)!=FIELDS:raise InvalidInput('exact accepted decision comparison fields required')
    for field in ('trip_id','action_id','proposal_id'):identifier(value[field])
    if type(value['version']) is not int or not 1<=value['version']<=2**63-1:raise InvalidInput('positive accepted version required')
    for field in ('content_sha256','candidate_hash'):
        digest=value[field]
        if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise InvalidInput('exact accepted decision digest required')
    if type(value['content_utf8']) is not str:raise InvalidInput('original accepted UTF8 required')
    content=value['content_utf8'].encode('utf-8')
    if not content or sha256(content).hexdigest()!=value['content_sha256']:raise InvalidInput('accepted document digest differs')
    document=json.loads(content)
    if type(document) is not dict:raise InvalidInput('structured accepted document required')
    if document.get('content_version')=='structured.1':validate_v1(document)
    elif document.get('content_version')=='structured.2':validate_v2(document)
    else:raise InvalidInput('explicit structured accepted decision required')
    if packed(document)!=content:raise InvalidInput('noncanonical accepted document')
    return AcceptedDecision(value['trip_id'],value['version'],value['content_sha256'],value['action_id'],
        value['proposal_id'],value['candidate_hash'],content)


def encoded(source:SourceV2,messages,mode,decision:AcceptedDecision):
    base=json.loads(encode_v2(source,messages,mode))
    value=dict(trip_id=decision.trip_id,version=decision.version,content_sha256=decision.content_sha256,
        action_id=decision.action_id,proposal_id=decision.proposal_id,candidate_hash=decision.candidate_hash,
        content_utf8=decision.content.decode('utf-8'))
    base.update(version=VERSION,decision=value,decision_source_sha256=source_digest(source.cursor.scope,decision))
    raw=canonical(base)
    if len(raw)>262144:raise InvalidInput('accepted decision batch exceeds queue bound')
    return raw


def decoded(raw):
    if type(raw) is not bytes or not 0<len(raw)<=262144:raise InvalidInput('bounded decision batch required')
    try:
        value=strict_object(raw)
        if (type(value) is not dict or set(value)!={'version','source','mode','messages','source_kind','decision','decision_source_sha256'}
                or value['version']!=VERSION):raise InvalidInput('explicit decision batch version required')
        decision=_decision(value.pop('decision'))
        digest=value.pop('decision_source_sha256')
        value['version']='CJ020-internal.2'
        source,messages,mode=decode_v2(canonical(value))
        if digest!=source_digest(source.cursor.scope,decision):raise InvalidInput('original decision source digest differs')
        if encoded(source,messages,mode,decision)!=raw:raise InvalidInput('noncanonical original decision batch')
        return source,messages,mode,decision
    except (MemoryInvalid,ValueError,TypeError,KeyError,UnicodeError,RecursionError) as error:
        raise InvalidInput('stored accepted decision batch unavailable') from error
