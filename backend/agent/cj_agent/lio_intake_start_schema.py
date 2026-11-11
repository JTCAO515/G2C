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


GUIDANCE=(PREVIOUS_GUIDANCE.replace('Response version is LIO-planning-intake.3.','Response version is LIO-planning-intake.4.').replace(
    'NEEDS-extraction.1',EXTRACTION_VERSION)+
    ' start_date is a separate REQUIRED observation for plan/save: the date the itinerary should begin, '
    'not merely an arrival event or a hotel/appointment date. If a traveler says start tomorrow, '
    'set start_date to known with the ISO date computed from THAT original message local day plus one; '
    'field_sources.start_date must quote that original start statement and its source_index. '
    'Do not omit the trip start because the same date also belongs to a fixed item. '
    'The execution fields MUST include party_size and fixed_items, even if missing or []. '
    'First-person I/我 or one person attending a fixed item does not establish the total travel party. '
    'Keep party_size missing until an explicit total count or clear solo statement; saved Memory is not a count source. '
    'Return the complete cumulative snapshot from ALL indexed traveler turns, never only latest changes. '
    'Retain the start, party and every fixed commitment when a later message changes only another field. '
    'Use missing/unknown/uncertain only when no definite trip start was stated. '
    'Preserve previously stated start dates unless the traveler corrects them; do not re-anchor to a later message day. '
    'For consult/discuss/cancel start_date MUST be null. The server maps a verified canonical start '
    'into its planning range, never by inferring it from a fixed-item date. '
    'Every fixed item has source_ref for its ONE complete original commitment, and detail_refs for '
    'explicit later clarifications of THAT item (or []). Each detail quote must explicitly name its '
    'short label; do not attach another item or a nameless ambiguous clarification. The short label is a nonempty '
    'literal label/span within source_ref.quote. The host preserves the complete primary quote '
    'as the canonical fixed description; do not return a separate description field. Do not choose another item or infer a primary source '
    'from a global fixed_items list. Keep dates, clocks, participants, locks and booking status '
    'as separate source-grounded observations; missing timezone may be derived by the host from '
    'the confirmed destination, but explicit unknown/uncertain or conflicting zones remain questions.')
