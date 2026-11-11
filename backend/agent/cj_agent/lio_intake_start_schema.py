"""Canonical planning start, independent from arrival or fixed-event dates."""
from copy import deepcopy
from hashlib import sha256
import json
from .lio_intake_modes_schema import SCHEMA as PREVIOUS_SCHEMA,GUIDANCE as PREVIOUS_GUIDANCE

PROFILE='LIO-planning-intake.5'
VERSION='LIO-planning-intake.4'
EXTRACTION_VERSION='LIO-execution-extraction.1'
SCHEMA=deepcopy(PREVIOUS_SCHEMA)
SCHEMA['properties']['version']={'const':VERSION}
execution=SCHEMA['properties']['extraction']['anyOf'][0]
execution['properties']['version']={'const':EXTRACTION_VERSION}
SCHEMA['allOf'][0]['else']['properties']['extraction']=execution
SCHEMA['$defs']['fields']['required'].extend(['party_size','fixed_items'])
SCHEMA['$defs']['fixed_item']['properties'].update(
    source_ref={'$ref':'#/$defs/source'},
    detail_refs={'type':'array','items':{'$ref':'#/$defs/source'},'maxItems':8})
SCHEMA['$defs']['fixed_item']['required'].extend(['source_ref','detail_refs'])
SCHEMA['$defs']['fixed_item']['properties']['label']=SCHEMA['$defs']['fixed_item']['properties'].pop('description')
SCHEMA['$defs']['fixed_item']['required'].remove('description')
SCHEMA['$defs']['fixed_item']['required'].append('label')
FIXED_FIELDS=tuple(SCHEMA['$defs']['fixed_item']['required'])
START={'$ref':'#/$defs/date_observation'}
SCHEMA['properties']['start_date']={'anyOf':[START,{'type':'null'}]}
SCHEMA['required'].append('start_date')
SCHEMA['allOf'][0]['then']['properties']['start_date']={'type':'null'}
SCHEMA['allOf'][0]['else']['properties']['start_date']=START
SCHEMA['allOf'].append({'if':{'properties':{'start_date':{'type':'object','properties':{'state':{'const':'known'}},'required':['state']}}},
    'then':{'properties':{'field_sources':{'required':['start_date']}}}})


def response_format(source_index):
    schema=deepcopy(SCHEMA)
    schema['properties']['current_source_index']={'type':'integer','const':source_index}
    return dict(type='json_schema',json_schema=dict(name='lio_planning_intake_v4',strict=True,schema=schema))


def response_format_sha256(source_index):
    return sha256(json.dumps(response_format(source_index),sort_keys=True,separators=(',',':')).encode()).hexdigest()


GUIDANCE=(
    ' Response version is LIO-planning-intake.4; plan/save extraction version is LIO-execution-extraction.1. '
    'Return current_source_index exactly as the schema constant for the latest original traveler turn. '
    'Stored Memory/Trip data is not indexed traveler evidence or permission. '
    'Return the COMPLETE cumulative snapshot from all indexed traveler turns, not just the latest delta. '
    'Retain unchanged dates, people and every fixed commitment when another field is corrected. '
    'Execution fields include party_size and fixed_items; unstated other optional fields are omitted. '
    'I/我 or one fixed-item participant does not establish total party size. Require an explicit total '
    'count or clear solo statement; otherwise party_size stays missing, never inferred from Memory. '
    'companions is a dictionary; fixed_items/temporary_conditions are arrays, never missing-observation objects. '
    'unresolved is [] except a supported schema clarification; never dates/party strings. '
    'start_date is a required observation for the itinerary beginning, separate from arrival/fixed-event dates. '
    'If start tomorrow is stated, use known ISO date from THAT original message local day plus one '
    'and field_sources.start_date quoting that start statement and source_index. Do not omit it because '
    'a fixed event has the same date. Missing/unknown/uncertain only if no definite trip start was stated; '
    'a later person reply never reanchors the earlier relative date. '
    'For consult/discuss/cancel, start_date/extraction/duration_days are null and field_sources is {}. '
    'A continuation after discussion/refusal stays discussion until a new explicit plan/save request. '
    'City query is a nonempty exact city-name span within its original quote; no inferred province/adcode. '
    'Each fixed item has label, source_ref and detail_refs (or []). Its primary quote is the complete '
    'ONE original commitment, not a whole turn, a summary, combined events or repeated clock ranges. '
    'label is a short exact span in that quote; the host preserves the quote as canonical description. '
    'Each detail must name a label unique across all primaries and belong to that one item. '
    'Never guess a primary from global citations or attach an ambiguous nameless detail. '
    'Keep separately grounded date/clock/participant/lock/booking observations. Never invent a booking. '
    'Omit destination_timezone; the host uses the confirmed city policy. Missing fixed timezone may '
    'use that policy, but explicit unknown/uncertain/conflicting zones stay questions; never infer UTC offsets.'
)
