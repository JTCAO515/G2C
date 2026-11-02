"""Unpublished Trip-evidence decoder; shares the canonical finite entry grammar."""
import json
from cj_message.domain import Command
from .decision_input import reference
from . import model_v2
from .extraction import _model_value,_parse_value,_decode_value,InvalidExtraction
from .postgres import encode

VERSION='MEMORY-EXTRACT-DRAFT@3'


def _translated(raw,messages,decision,scope):
    value=_model_value(raw)
    if type(value) is not dict or set(value)!={'version','entries'} or value['version']!=VERSION or type(value['entries']) is not list:
        raise InvalidExtraction('explicit decision extraction envelope required')
    lookup={model_v2.reference(scope,m):(m.receipt.message_id,m.text,False) for m in messages}
    for message in messages:
        if json.loads(message.original_utf8)['version']!='MESSAGE-send.3':continue
        command=Command.parse_original(message.original_utf8);selection=command.trip_context
        if (selection is not None and (selection.id,selection.expected_version)==(decision.trip_id,decision.version)
                and selection.day is None and selection.item_id is None):
            lookup[reference(scope,message,decision)]=(message.receipt.message_id,decision.content.decode('utf-8'),True)
    entries=[];texts={};trip_entries=set()
    for entry in value['entries']:
        if type(entry) is not dict or type(entry.get('evidence')) is not list:
            raise InvalidExtraction('explicit decision evidence required')
        evidence=[];has_trip=False
        for ref in entry['evidence']:
            if (type(ref) is not dict or set(ref)!={'ref','quote'} or type(ref['ref']) is not str
                    or ref['ref'] not in lookup or type(ref['quote']) is not str):
                raise InvalidExtraction('decision evidence does not match permitted original')
            mid,text,trip=lookup[ref['ref']];quote=ref['quote']
            if quote not in text:raise InvalidExtraction('quote differs from its exact original reference')
            texts[mid,quote]=text
            has_trip|=trip
            evidence.append(dict(message_id=mid,quote=quote))
        if has_trip:trip_entries.add(encode([entry.get('subject'),entry.get('slot'),entry.get('extent')]))
        entries.append(dict(entry,evidence=evidence))
    return dict(version='MEMORY-EXTRACT@1',entries=entries),texts,trip_entries


def parse_output(raw,messages,decision,policy,scope):
    value,texts,trip_entries=_translated(raw,messages,decision,scope)
    def direct(entry,rows):
        if encode([entry.subject,entry.slot,entry.extent]) in trip_entries:return False
        return policy.direct_statement(entry,rows)
    return _parse_value(value,messages,policy,quote_texts=texts,direct_statement=direct)


def decode_output(raw,messages,decision,scope):
    value,texts,_=_translated(raw,messages,decision,scope)
    return _decode_value(value,messages,quote_texts=texts)
