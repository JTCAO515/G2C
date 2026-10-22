"""Exact public NEEDS values; no private repository or recomputed historical hash."""
import base64
from dataclasses import asdict
import json
from .generated import NeedsReceipt,NeedsSnapshot,NeedsRevision,NeedsFields

def fields(raw,domain):
    try:
        value=domain.decode(raw)
        domain.validate_fields(value,complete=True)
    except domain.InvalidInput:
        raise ValueError('Invalid stored NEEDS content') from None
    return NeedsFields.model_validate_json(raw,strict=True)

def raw64(raw):
    if type(raw) is not bytes or not 0<len(raw)<=131072:raise ValueError('Bounded original UTF8 required')
    raw.decode('utf-8')
    return base64.b64encode(raw).decode('ascii')

def receipt(value,domain):
    if type(value) is not domain.Receipt:raise ValueError('Invalid original NEEDS receipt')
    return NeedsReceipt.model_validate_json(json.dumps(asdict(value)),strict=True)

def snapshot(value,domain):
    if type(value) is not domain.Snapshot:raise ValueError('Invalid NEEDS snapshot')
    projected=fields(value.content,domain)
    return NeedsSnapshot.model_validate_json(json.dumps({'needs_id':value.needs_id,'version':value.version,
        'source_kind':value.source_kind,'content_utf8_base64':raw64(value.content),
        'fields':projected.model_dump(mode='json',exclude_unset=True)}),strict=True)

def revision(value,domain):
    if type(value) is not domain.Revision:raise ValueError('Invalid NEEDS revision')
    try:command=domain.Command(value.original_input).data
    except domain.InvalidInput:raise ValueError('Invalid stored original NEEDS action') from None
    if (command['action_id']!=value.action_id or command['needs_id']!=value.needs_id
            or command['expected_version']+1!=value.version):
        raise ValueError('Revision differs from original action binding')
    projected=fields(value.content,domain)
    return NeedsRevision.model_validate_json(json.dumps({'needs_id':value.needs_id,'version':value.version,
        'action_id':value.action_id,'source_kind':value.source_kind,
        'original_input_utf8_base64':raw64(value.original_input),'content_utf8_base64':raw64(value.content),
        'fields':projected.model_dump(mode='json',exclude_unset=True)}),strict=True)
