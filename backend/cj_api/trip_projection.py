"""Formal generated TRIP projections over fixed public domain value types only."""
import base64
from dataclasses import asdict
import json
from .generated import TripActionReceipt, TripDocument, TripRecord


def parse_action(raw, domain):
    if type(raw) is not bytes:
        raise ValueError('Original canonical action bytes required')
    value=json.loads(raw.decode('utf-8'))
    if type(value) is not list or len(value)!=5 or any(type(v) is not str for v in value):
        raise ValueError('Five canonical action strings required')
    action=domain.Action(*value)
    if action.raw()!=raw:
        raise ValueError('Noncanonical action')
    return action


def receipt_projection(value, domain):
    if type(value) is not domain.Receipt:
        raise ValueError('Invalid internal Trip action receipt')
    if ((value.kind=='accept' and value.committed_version is None)
            or (value.kind=='reject' and value.committed_version is not None)):
        raise ValueError('Invalid receipt action/version relationship')
    return TripActionReceipt.model_validate_json(json.dumps(asdict(value)),strict=True)


def content_projection(raw, domain):
    if type(raw) is not bytes or not 0<len(raw)<=1_000_000:
        raise ValueError('Immutable bounded Trip content required')
    decoded=raw.decode('utf-8')
    document=TripDocument.model_validate_json(decoded,strict=True)
    obj=json.loads(decoded)
    if domain.packed(obj)!=raw or not document.title.strip():
        raise ValueError('Canonical nonempty content required')
    seen=set()
    for item in document.items:
        if (item.id in seen or not item.text.strip()
                or item.verification.value=='verified' and not item.evidence):
            raise ValueError('Invalid item identity/fact state')
        seen.add(item.id)
    return document,base64.b64encode(raw).decode('ascii')


def trip_projection(value, domain):
    if type(value) is not domain.Trip:
        raise ValueError('Invalid internal Trip')
    document,encoded=content_projection(value.content,domain)
    return TripRecord.model_validate_json(json.dumps({'trip_id':value.trip_id,'version':value.version,
        'content_utf8_base64':encoded,'document':document.model_dump(mode='json')}),strict=True)
