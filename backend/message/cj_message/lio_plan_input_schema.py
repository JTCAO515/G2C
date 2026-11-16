"""Additive plan-trigger understanding data, never a source/write capability.

The host validates every value against real originals and their original clocks
before creating NEEDS. Missing fields stay missing; accepted profile defaults
are separate code provenance and must not be emitted as traveler statements.
"""
from typing import Annotated,Literal
from pydantic import Field

from .lio_pipeline_schema import Data

PLAN_UNDERSTANDING='LIO-exploration-plan-understanding.1'
Participant=Annotated[str,Field(pattern=r'^(?:self|party|companion:[A-Za-z0-9][A-Za-z0-9_.:-]{0,95})$')]


class PlanQuote(Data):
    source_index:int=Field(ge=0)
    quote:str=Field(min_length=1,max_length=4096)


class PlanObservation(Data):
    field:Literal['start_date','party_size','pace','departure.mode','first_day_full','budget_currency','budget_total',
        'budget_per_person','budget_paid','budget_basis','budget_includes','overseas_timezone',
        'arrival.date','arrival.time','arrival.timezone','arrival.place',
        'departure.date','departure.time','departure.timezone','departure.place',
        'overseas_departure.date','overseas_departure.time','overseas_departure.timezone','overseas_departure.place']
    state:Literal['known','unknown','uncertain']
    value:str|int|bool|list[str]|None
    note:str|None=Field(max_length=4096)
    sources:list[PlanQuote]=Field(min_length=1,max_length=8)


class PlanCompanion(Data):
    companion_id:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$')
    name:str=Field(min_length=1,max_length=200)
    sources:list[PlanQuote]=Field(min_length=1,max_length=8)


class PlanBooking(PlanQuote):
    status:Literal['booked','intended','cancelled']


class PlanFixed(Data):
    label:str=Field(min_length=1,max_length=4096)
    source_index:int=Field(ge=0)
    quote:str=Field(min_length=1,max_length=4096)
    detail_refs:list[PlanQuote]=Field(max_length=8)
    kind:Literal['hotel','transport','appointment','intent']
    applies_to:list[Participant]=Field(min_length=1,max_length=32)
    locked:bool|None
    booking_evidence:PlanBooking|None
    start_date:str|None
    start_time:str|None
    start_timezone:str|None
    start_place:str|None
    end_date:str|None
    end_time:str|None
    end_timezone:str|None
    end_place:str|None
    unknown_fields:list[Literal['start_date','start_time','start_timezone','start_place',
        'end_date','end_time','end_timezone','end_place','locked','booking_status']]
    uncertain_fields:dict[str,str]


class PlanCondition(Data):
    condition_id:str=Field(min_length=1,max_length=96)
    applies_to:list[Participant]=Field(min_length=1,max_length=32)
    description:str=Field(min_length=1,max_length=4096)
    sources:list[PlanQuote]=Field(min_length=1,max_length=8)


class PlanUnderstanding(Data):
    version:Literal['LIO-exploration-plan-understanding.1']
    current_source_index:int=Field(ge=0)
    observations:list[PlanObservation]=Field(max_length=64)
    companions:list[PlanCompanion]=Field(max_length=32)
    fixed_items:list[PlanFixed]=Field(max_length=100)
    temporary_conditions:list[PlanCondition]=Field(max_length=32)
