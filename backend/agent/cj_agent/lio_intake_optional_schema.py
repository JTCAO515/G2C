"""Optional dates/party: additive profile9/data8; older profiles stay frozen."""
from copy import deepcopy
from hashlib import sha256
import json
from typing import Literal
from .lio_intake_flow_schema import FlowIntake
from .lio_intake_flat_schema import _inline
from .lio_intake_facts_schema import SYSTEM as FACTS_SYSTEM

PROFILE='LIO-planning-intake.9'
VERSION='LIO-planning-intake.8'


class OptionalIntake(FlowIntake):
    version:Literal['LIO-planning-intake.8']


_generated=OptionalIntake.model_json_schema()
SCHEMA=_inline(_generated,_generated['$defs'])


def response_format(source_index):
    schema=deepcopy(SCHEMA)
    schema['properties']['current_source_index']['const']=source_index
    return dict(type='json_schema',json_schema=dict(name='lio_optional_planning_v8',strict=True,schema=schema))


def response_format_sha256(source_index):
    return sha256(json.dumps(response_format(source_index),sort_keys=True,separators=(',',':')).encode()).hexdigest()


SYSTEM=FACTS_SYSTEM.replace('LIO-planning-intake.6','LIO-planning-intake.8')+(
    ' Planning needs only a destination and day count, including 去成都玩三天, '
    '规划北京三日游 and Plan 4 days in Xi\'an from tomorrow. '
    'planning_request_index identifies the original request to plan the travelers own itinerary. '
    'It is null for translation, quotations, meta questions, sufficiency or option consultation. '
    'A short reply to a pending request continues that original request; never replace its source index. '
    'Extract supplied facts for ALL intents; intent is advisory, never write authority. '
    'Preserve earlier facts unless the traveler changes or explicitly marks them unknown. '
    'Dates and party size are OPTIONAL, never required clarifications. '
    'Unknown, undecided, not sure, 随便, 不知道, 没定日期 and 没定人数 are data, not cancellation or a hold. '
    'Never default a date to tomorrow or a party size to one. '
    'If city or day count is missing, ask just one missing item in a natural question. '
    'When both are supplied, question_fields=[] and reply is a brief acknowledgement; '
    'the host produces the complete plan separately. Do not ask dates or party size. '
    'Retain luxury, pace and other preferences in the original dialogue. '
    'publication_hold is an exact original refusal to save, discussion-only, conditional or cancellation span. '
    'Keep a hotel meetup unchanged or do not claim a reservation is not a publication hold. '
    'Never clear an actual hold on a bare parameter answer. A new explicit planning/save request may resume it. '
    'question_fields lists exactly which facts the reply asks for. '
    'Do not introduce yourself or say you do not know the traveler in planning replies. '
    'Keep original source indices, quotes and question-day date bindings; no model write permission.'
)
