"""Explicit initialization of current legacy title/items; never an automatic migration."""
from dataclasses import dataclass
from hashlib import sha256
import json
from .domain import Conflict, Trip, identifier, packed, validate_legacy_document
from .manual import ManualSave
from .structured import validate_document, event, observation, _fixed

VERSION='TRIP-initialize.1'
BASIS='manual-initialization.1'


@dataclass(frozen=True)
class Initialization:
    raw: bytes
    request_id: str
    trip_id: str
    expected_version: int
    original_hash: str
    observations: tuple

    @classmethod
    def parse(cls,raw):
        if type(raw) is not bytes or not 0 < len(raw) <= 1_000_000:
            raise ValueError('bounded original initialization required')
        doc=json.loads(raw)
        if (type(doc) is not dict or set(doc)!={'version','request_id','trip_id','expected_version','original_hash','items'}
                or doc['version']!=VERSION or packed(doc)!=raw):
            raise ValueError('exact canonical initialization input required')
        identifier(doc['request_id']);identifier(doc['trip_id'])
        if type(doc['expected_version']) is not int or doc['expected_version']<1:
            raise ValueError('original Trip version required')
        digest=doc['original_hash']
        if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('original content hash required')
        if type(doc['items']) is not list or not 1<=len(doc['items'])<=60:
            raise ValueError('explicit observations for all original items required')
        observations=[];seen=set()
        for item in doc['items']:
            if type(item) is not dict or set(item)!={'id','schedule','fixed'}:raise ValueError('initialization cannot edit text or source')
            identifier(item['id'])
            if item['id'] in seen:raise ValueError('duplicate item')
            seen.add(item['id'])
            if type(item['schedule']) is not dict or set(item['schedule'])!={'start','end'}:raise ValueError('explicit start/end required')
            event(item['schedule']['start']);event(item['schedule']['end']);observation(item['fixed'],_fixed)
            observations.append((item['id'],packed(item['schedule']),packed(item['fixed'])))
        return cls(raw,doc['request_id'],doc['trip_id'],doc['expected_version'],digest,tuple(observations))


class InitializationSave(ManualSave):
    @classmethod
    def parse(cls,raw):return cls._parse(raw,'TRIP-initialize-save.1')


@dataclass(frozen=True)
class InitializationCandidate:
    original: Trip
    content: bytes
    edit: Initialization
    diff: bytes


def initialize(original,request):
    if (original.trip_id!=request.trip_id or original.version!=request.expected_version
            or sha256(original.content).hexdigest()!=request.original_hash):
        raise Conflict('original Trip changed; retain explicit initialization input')
    before=json.loads(original.content)
    # Explicitly bounded compatibility: provenance.1 has distinct source/decision
    # semantics and is retained on its old path until its binding is implemented.
    validate_legacy_document(before)
    if packed(before)!=original.content:raise ValueError('canonical original Trip required')
    observations={key:(schedule,fixed) for key,schedule,fixed in request.observations}
    if set(observations)!={item['id'] for item in before['items']}:raise ValueError('exact original item ID set required')
    items=[]
    for item in before['items']:
        schedule,fixed=observations[item['id']]
        items.append(dict(item,schedule=json.loads(schedule),fixed=json.loads(fixed),
                          source_category='unknown',source_refs=[]))
    after=dict(content_version='structured.1',title=before['title'],items=items,sources=[])
    validate_document(after)
    diff=packed(dict(before=before,after=after,request_id=request.request_id,
                     trip_id=original.trip_id,expected_version=original.version))
    return InitializationCandidate(original,packed(after),request,diff)
