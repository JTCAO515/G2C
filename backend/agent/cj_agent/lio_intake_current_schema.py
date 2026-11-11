"""Current-source coordinates; keep the deployed profile/data versions intact."""
from copy import deepcopy
from hashlib import sha256
import json

from .lio_intake_schema import SCHEMA as PREVIOUS_SCHEMA,GUIDANCE as PREVIOUS_GUIDANCE

PROFILE='LIO-planning-intake.3'
VERSION='LIO-planning-intake.2'
SCHEMA=deepcopy(PREVIOUS_SCHEMA)
SCHEMA['properties']['version']={'const':VERSION}
SCHEMA['properties'].pop('current_request')
SCHEMA['properties']['current_source_index']={'type':'integer','minimum':0}
SCHEMA['required'].remove('current_request')
SCHEMA['required'].append('current_source_index')


def response_format(source_index):
    schema=deepcopy(SCHEMA)
    schema['properties']['current_source_index']={'type':'integer','const':source_index}
    return dict(type='json_schema',json_schema=dict(name='lio_planning_intake_v2',strict=True,schema=schema))


def response_format_sha256(source_index):
    return sha256(json.dumps(response_format(source_index),sort_keys=True,separators=(',',':')).encode()).hexdigest()


GUIDANCE=(PREVIOUS_GUIDANCE+' Response version is LIO-planning-intake.2. '
    'current_request is not a response field. Return current_source_index matching the schema constant, '
    'the latest indexed traveler message, even for a short continuation. '
    'Use older indexed traveler messages only as evidence for their own quoted facts; '
    'the server obtains the current request from its immutable original, not from model-written text.')
