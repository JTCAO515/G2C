"""Appended send.4 boundary, preserving old wire parsers."""
from dataclasses import dataclass
import hashlib
import json
import re
from cj_trip.domain import identifier
from .domain import InvalidInput,Unavailable
from .trip_context import TripSelection,decode_source,on_day,trip_scope_for
from .travel_reference import ContextConflict


@dataclass(frozen=True)
class EditSelection:
    id: str
    expected_version: int
    content_sha256: str
    day: tuple[str,str] | None
    item_ids: tuple[str,...]

    @classmethod
    def parse(cls,value):
        try:
            if type(value) is not dict or set(value)!={'id','expected_version','content_sha256','day','item_ids'}:
                raise ValueError('explicit edit Trip fields required')
            base=TripSelection.parse(dict(id=value['id'],expected_version=value['expected_version'],day=value['day'],item_id=None))
            digest=value['content_sha256'];items=value['item_ids']
            if type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None:raise ValueError('explicit content hash required')
            if type(items) is not list or len(items)>60 or len(set(items))!=len(items):raise ValueError('unique bounded item IDs required')
            for item in items:identifier(item)
            return cls(base.id,base.expected_version,digest,base.day,tuple(items))
        except (ValueError,TypeError,KeyError) as exc:raise InvalidInput('invalid edit selection') from exc

    def public_value(self):
        return dict(id=self.id,expected_version=self.expected_version,content_sha256=self.content_sha256,
            day=None if self.day is None else dict(date=self.day[0],timezone=self.day[1]),item_ids=list(self.item_ids))


def parse(raw):
    from .domain import Command
    from .travel import Selection
    from cj_needs.domain import identifier as needs_id
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise InvalidInput('duplicate field')
            result[key]=value
        return result
    try:
        if type(raw) is not bytes:raise ValueError('original bytes required')
        value=json.loads(raw.decode('utf8'),object_pairs_hook=unique)
        fields={'version','conversation_id','message_id','text','trip_id','creation_intent','expected_generation','expected_sequence','trip_context','travel_context','needs_reference','modification_intent'}
        if type(value) is not dict or set(value)!=fields or value['version']!='MESSAGE-send.4':raise ValueError('send.4 exact fields required')
        for key in ('conversation_id','message_id','text','expected_generation'):
            if type(value[key]) is not str or not value[key].strip():raise ValueError('explicit nonblank identity/text required')
        if len(value['conversation_id'].encode('utf8'))>256 or '\0' in value['conversation_id']:raise ValueError('invalid conversation')
        if type(value['expected_sequence']) is not int or value['expected_sequence']<0:raise ValueError('invalid head')
        if value['trip_id'] is not None or value['creation_intent']!='none':raise ValueError('creation unavailable in send.4')
        intent=value['modification_intent']
        if intent not in ('none','propose_scoped_edit'):raise ValueError('explicit edit intent required')
        trip=EditSelection.parse(value['trip_context']);travel=Selection.parse(value['travel_context'])
        needs=None
        if intent=='propose_scoped_edit':
            if (trip.day is None)==(not trip.item_ids):raise ValueError('exactly day or item selection required')
            v=value['needs_reference']
            if type(v) is not dict or set(v)!={'id','expected_version'} or type(v['expected_version']) is not int or not 1<=v['expected_version']<=9223372036854775807:raise ValueError('current NEEDS required')
            needs=(needs_id(v['id']),v['expected_version'])
        elif value['needs_reference'] is not None:raise ValueError('discussion NEEDS must be null')
        return Command(value['conversation_id'],value['message_id'],raw,value['expected_generation'],value['expected_sequence'],travel,needs,trip,intent)
    except (ValueError,TypeError,KeyError,UnicodeError) as exc:raise InvalidInput('invalid send.4') from exc


def validate_source(raw,selection):
    base=TripSelection(selection.id,selection.expected_version,selection.day,None)
    document=decode_source(raw,base)
    if hashlib.sha256(raw).hexdigest()!=selection.content_sha256:raise ContextConflict('Trip content changed')
    available={item['id'] for item in document['items']}
    if not set(selection.item_ids)<=available:raise Unavailable('selected item unavailable')
    selected=(tuple(item['id'] for item in document['items'] if on_day(item,selection.day)) if selection.day is not None
              else selection.item_ids or tuple(item['id'] for item in document['items']))
    if not selected:raise Unavailable('empty declared day')
    return document,selected


def current_trip(cursor,scope,selection,*,write=False):
    cursor.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR '+('UPDATE' if write else 'SHARE'),(trip_scope_for(scope),))
    if cursor.fetchone() is None:raise Unavailable('Trip owner unavailable')
    cursor.execute('SELECT version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s',(trip_scope_for(scope),selection.id))
    row=cursor.fetchone()
    if row is None:raise Unavailable('Trip unavailable')
    if row[0]!=selection.expected_version:raise ContextConflict('Trip version changed')
    raw=bytes(row[1]);doc,ids=validate_source(raw,selection)
    return raw,doc['content_version'],ids
