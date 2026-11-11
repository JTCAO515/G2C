"""Sourced facts: bounded source entries and explicit original booking evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from typing import Literal
from pydantic import Field
from .lio_intake_flat_schema import Source,Fixed,FlatIntake,_inline,SYSTEM as FLAT_SYSTEM

PROFILE='LIO-planning-intake.7'
VERSION='LIO-planning-intake.6'


class FieldSource(Source):
    field:Literal['start_date','duration_days','party_size','pace','budget_currency',
        'budget_total','budget_per_person','budget_paid','budget_basis','budget_includes',
        'overseas_timezone','arrival.date','arrival.time','arrival.timezone','arrival.place',
        'departure.date','departure.time','departure.timezone','departure.place',
        'overseas_departure.date','overseas_departure.time','overseas_departure.timezone',
        'overseas_departure.place','companions','temporary_conditions']


class Booking(Source):
    status:Literal['booked','intended','cancelled']


class SourcedFixed(Fixed):
    booking_status:Booking|None=Field(alias='booking_evidence',description='Only an explicit original reservation/ticket or booking intention/cancellation quote. Fixed arrangements and hotel meetups are not reservation evidence: null.')


class SourcedIntake(FlatIntake):
    version:Literal['LIO-planning-intake.6']
    field_sources:list[FieldSource]=Field(max_length=512)
    fixed_items:list[SourcedFixed]=Field(max_length=100)


_generated=SourcedIntake.model_json_schema()
SCHEMA=_inline(_generated,_generated['$defs'])


def response_format(source_index):
    schema=deepcopy(SCHEMA);schema['properties']['current_source_index']['const']=source_index
    return dict(type='json_schema',json_schema=dict(name='lio_sourced_facts_v6',strict=True,schema=schema))


def response_format_sha256(source_index):
    return sha256(json.dumps(response_format(source_index),sort_keys=True,separators=(',',':')).encode()).hexdigest()


SYSTEM=FLAT_SYSTEM.replace('LIO-planning-intake.5','LIO-planning-intake.6').replace(
    'simple nullable dates/times/zone/lock/booking fields','simple nullable dates/times/zone/lock fields plus original booking evidence')+(
    ' For this version field_sources is a LIST of {field,source_index,quote}, never a map. '
    'Emit entries only for stated known facts, using the allowed field enum; no entries for missing facts. '
    'The host gets fixed-item sources from their primary/detail refs, not field_sources. '
    'Each fixed item replaces booking_status with booking_evidence: null without explicit reservation evidence, '
    'otherwise {status,source_index,quote}. Fixed/confirmed arrangements and a hotel meetup do not mean a reservation. '
    'Its evidence must be an exact original span in that item primary/detail source and explicitly state the reservation status. '
    'This evidence does not grant permission to book, save or change anything.'
)
