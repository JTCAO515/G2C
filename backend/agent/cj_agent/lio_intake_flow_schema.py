"""Unified planning facts and model clarification; additive profile8/data7."""
from copy import deepcopy
from hashlib import sha256
import json
from typing import Literal
from pydantic import Field
from .lio_intake_facts_schema import SourcedIntake,SYSTEM as FACTS_SYSTEM
from .lio_intake_flat_schema import Source,_inline

PROFILE='LIO-planning-intake.8'
VERSION='LIO-planning-intake.7'

class FlowIntake(SourcedIntake):
    version:Literal['LIO-planning-intake.7']
    planning_request_index:int|None=Field(ge=0,description='Original traveler message actually requesting this itinerary; null for translation, quotations, meta questions, sufficiency/option consultation or discussion. Missing parameters do not turn a genuine travel request into consultation.')
    publication_hold:Source|None=Field(description='Exact original refusal, discussion-only, conditional or cancellation span; null only when none exists. A hold can deny publication, never grant it.')
    question_fields:list[Literal['city','duration_days','start_date','party_size','fixed_items']]=Field(max_length=5)

_generated=FlowIntake.model_json_schema()
SCHEMA=_inline(_generated,_generated['$defs'])

def response_format(source_index):
    schema=deepcopy(SCHEMA);schema['properties']['current_source_index']['const']=source_index
    return dict(type='json_schema',json_schema=dict(name='lio_planning_flow_v7',strict=True,schema=schema))

def response_format_sha256(source_index):
    return sha256(json.dumps(response_format(source_index),sort_keys=True,separators=(',',':')).encode()).hexdigest()

SYSTEM=FACTS_SYSTEM.replace('LIO-planning-intake.6','LIO-planning-intake.7')+(
    ' Unified planning rule: a destination and duration enter planning, including 去成都玩三天. '
    'planning_request_index identifies a genuine request to plan the travelers own itinerary, including bare destination+duration. '
    'It is null for translate this quoted trip, is three days enough, or other ordinary consultation, even when city/days/date/people are mentioned. '
    'Do not mark a parameter-only answer after a hold as a new request; a pending positive request can continue. '
    'Extract supplied facts for ALL intents, including consult/discuss; intent is advisory, never write authority. '
    'Retain every previously supplied fact unless the traveler changes that fact; a short answer changes only related facts. '
    'Never default a start date to tomorrow or a party to one. Missing start date and party size must be asked together in ONE reply. '
    'If a date is already supplied, including from tomorrow, ask only party size; never ask the date again. '
    'publication_hold concerns planning/saving authorization only. Keep a hotel meetup unchanged or do not claim a reservation are not publication holds. '
    'publication_hold records any original refusal or hold semantically, not just fixed phrases: e.g. 无需落盘, 先别自动保存, no need to persist. Never clear a hold on a bare parameter answer. '
    'question_fields lists exactly which facts your reply asks the traveler to supply or clarify; [] for a non-question. '
    'Use a concise natural clarification rather than an itinerary while a required fact is missing. '
    'Do not ask a fact already supplied. A refusal to save, discussion-only or cancellation still forbids publication. '
    'Keep source indices and exact quotes from originals for all facts, even when the latest answer only supplies party size.'
)
