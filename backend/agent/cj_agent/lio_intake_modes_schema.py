"""Intent-specific intake: non-executing dialogue has no NEEDS parameters."""
from copy import deepcopy
from hashlib import sha256
import json

from .lio_intake_current_schema import SCHEMA as PREVIOUS_SCHEMA,GUIDANCE as PREVIOUS_GUIDANCE

PROFILE='LIO-planning-intake.4'
VERSION='LIO-planning-intake.3'
SCHEMA=deepcopy(PREVIOUS_SCHEMA)
SCHEMA['properties']['version']={'const':VERSION}
SCHEMA['$defs']['fields']['properties'].pop('destination_timezone')
execution=SCHEMA['properties']['extraction']
SCHEMA['properties']['extraction']={'anyOf':[execution,{'type':'null'}]}
SCHEMA['allOf']=[dict(
    **{'if':{'properties':{'intent':{'enum':['consult','discuss','cancel']}}},
       'then':{'properties':{'extraction':{'type':'null'},'duration_days':{'type':'null'},
                           'field_sources':{'type':'object','maxProperties':0}}},
       'else':{'properties':{'extraction':execution}}})]


def response_format(source_index):
    schema=deepcopy(SCHEMA)
    schema['properties']['current_source_index']={'type':'integer','const':source_index}
    return dict(type='json_schema',json_schema=dict(name='lio_planning_intake_v3',strict=True,schema=schema))


def response_format_sha256(source_index):
    return sha256(json.dumps(response_format(source_index),sort_keys=True,separators=(',',':')).encode()).hexdigest()


GUIDANCE=('For plan/save execution parameters only: '+PREVIOUS_GUIDANCE.replace(
    'Response version is LIO-planning-intake.2.','Response version is LIO-planning-intake.3.')+
    ' For consult/discuss/cancel, extraction and duration_days MUST be null and field_sources MUST be {}. '
    'Do not generate NEEDS observations, missing-field questions or unresolved entries for non-executing dialogue. '
    'A short continuation after discussion/refusal remains discussion until an explicit new plan/save request. '
    'City query is the exact nonempty city-name span within its original quote; the quote may include context. '
    'Never infer destination_timezone in execution fields; the server derives it from the confirmed city. '
    'Keep explicitly stated event timezones and their original sources; do not infer them.')
