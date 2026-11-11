"""Additive strict wire profile; frozen LIO-planning-intake.1 data stays intact."""
from hashlib import sha256
import json

PROFILE='LIO-planning-intake.2'
DEFS={}


def obj(properties,required=None,**extra):
    return dict(type='object',properties=properties,required=list(properties) if required is None else required,
                additionalProperties=False,**extra)


def define(name,schema):
    DEFS[name]=schema
    return {'$ref':'#/$defs/'+name}


TEXT=define('text',dict(type='string',minLength=1,maxLength=4096))
IDENTIFIER=define('identifier',dict(type='string',pattern='^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$'))
MISSING=define('missing',obj(dict(state=dict(const='missing'))))
UNKNOWN=define('unknown',obj(dict(state=dict(const='unknown'))))
UNCERTAIN=define('uncertain',obj(dict(state=dict(const='uncertain'),note=TEXT)))


def observation(value):
    return dict(anyOf=[MISSING,UNKNOWN,UNCERTAIN,obj(dict(state=dict(const='known'),value=value))])


TEXT_OBS=define('text_observation',observation(TEXT))
DATE_OBS=define('date_observation',observation(dict(type='string',format='date')))
TIME_OBS=define('time_observation',observation(dict(type='string',pattern=r'^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$')))
MONEY_OBS=define('money_observation',observation(dict(type='string',pattern=r'^(0|[1-9][0-9]{0,14})(\.[0-9]{1,6})?$')))
EVENT=define('event',obj(dict(date=DATE_OBS,time=TIME_OBS,timezone=TEXT_OBS,place=TEXT_OBS)))
SUBJECTS=define('subjects',dict(type='array',items=dict(type='string',pattern=r'^(self|party|companion:[A-Za-z0-9][A-Za-z0-9_.:-]{0,95})$'),minItems=1,maxItems=32))
FIXED=define('fixed_item',obj(dict(item_id=IDENTIFIER,kind=dict(enum=['hotel','transport','appointment','intent']),description=TEXT,
    applies_to=SUBJECTS,locked=observation(dict(type='boolean')),start=EVENT,end=EVENT,
    booking_status=observation(dict(enum=['booked','intended','cancelled'])))))
TEMPORARY=define('temporary_condition',obj(dict(condition_id=IDENTIFIER,applies_to=SUBJECTS,description=TEXT)))
FIELDS=define('fields',obj(dict(
    party_size=observation(dict(type='integer',minimum=1,maximum=100000)),
    destination_timezone=TEXT_OBS,overseas_timezone=TEXT_OBS,
    budget_currency=observation(dict(type='string',pattern='^[A-Z]{3}$')),
    **{name:MONEY_OBS for name in ('budget_total','budget_per_person','budget_paid')},
    budget_basis=observation(dict(enum=['total','per_person'])),
    budget_includes=observation(dict(type='array',items=TEXT,minItems=1,maxItems=32)),pace=TEXT_OBS,
    overseas_departure=EVENT,arrival=EVENT,departure=EVENT,
    companions=dict(type='object',additionalProperties=TEXT,maxProperties=16,**{'not':obj(dict(state=dict(enum=['missing','unknown'])))}),
    fixed_items=dict(type='array',items=FIXED,maxItems=100),
    temporary_conditions=dict(type='array',items=TEMPORARY,maxItems=100)),required=[]))
SOURCE=define('source',obj(dict(source_index=dict(type='integer',minimum=0),quote=TEXT)))
UNRESOLVED=define('unresolved',dict(anyOf=[obj(dict(field=dict(const=field),reason=dict(const=reason),original_text=TEXT))
    for field,reason in [('budget_basis','missing_basis'),('budget_paid','currency_mismatch'),
        ('temporary_conditions','unclear_lifetime'),('fixed_items','missing_subject')]]))
CITY=define('city',obj(dict(query=dict(type='string',minLength=1,maxLength=256),
    normalized_name=dict(type=['string','null'],maxLength=256),province=dict(type=['string','null'],maxLength=256),
    source_index=dict(type='integer',minimum=0),quote=dict(type='string',minLength=1,maxLength=256))))
SCHEMA=obj(dict(version=dict(const='LIO-planning-intake.1'),intent=dict(enum=['consult','discuss','plan','save','cancel']),
    reply=TEXT,needs_tools=dict(type='boolean'),city=dict(anyOf=[CITY,dict(type='null')]),
    duration_days=dict(anyOf=[dict(type='integer',minimum=1,maximum=366),dict(type='null')]),
    extraction=obj(dict(version=dict(const='NEEDS-extraction.1'),fields=FIELDS,
        unresolved=dict(type='array',items=UNRESOLVED,maxItems=8),long_term_requests=dict(type='array',items=TEXT,maxItems=8))),
    field_sources=dict(type='object',additionalProperties=dict(type='array',items=SOURCE,minItems=1,maxItems=16),maxProperties=256),
    current_request=dict(type='string',minLength=1,maxLength=12000)),**{'$defs':DEFS})
RESPONSE_FORMAT=dict(type='json_schema',json_schema=dict(name='lio_planning_intake_v1',strict=True,schema=SCHEMA))
SCHEMA_SHA256=sha256(json.dumps(RESPONSE_FORMAT,sort_keys=True,separators=(',',':')).encode()).hexdigest()
GUIDANCE=(
 ' Exact extraction keys are version,fields,unresolved,long_term_requests. '
 'extraction.version MUST be the literal NEEDS-extraction.1. '
 'Omit unstated optional fields. companions is a dictionary of companion-id to label (or {}), '
 'fixed_items and temporary_conditions are arrays (or []). These three collections NEVER use '
 '{state:missing}. Use observation objects only for the scalar/event observations. '
 'unresolved is [] unless a supported NEEDS clarification applies; its entries are objects with '
 'field,reason,original_text matching the supplied schema, NEVER strings such as dates or party size. '
 'The server already asks for missing start, duration and party size; do not add unsupported unresolved names. '
 'Every ordinary missing detail stays missing; do not fabricate a known value to satisfy the schema.'
)
