"""One validated cumulative fact flow; no defaults and no model write capability."""
from dataclasses import dataclass,replace
import json
import re
from typing import Literal
from pydantic import ConfigDict,Field,ValidationError
from cj_agent.lio_intake_flow_schema import FlowIntake
from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_agent.lio_intake_flat_schema import DTO,City
from cj_needs.domain import InvalidInput,decode
from .lio_sourced_intake import parse_sourced,BookingSourceUnclear

CORE=('start_date','duration_days','party_size')
# Presence check only, never a date extractor or a default. The original
# compiler independently checks exact ISO/relative dates against their day.
DATE_EVIDENCE=re.compile(r'\d{4}[-/年]\d{1,2}|[0-9一二三四五六七八九十]+月|[0-9]+[日号]|'
    r'今天|明天|后天|周|星期|[0-9一二三四五六七八九十]+天[后之]|'
    r"\b(?:today|tomorrow|tonight|yesterday|next|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b|\b[0-9]+[/-][0-9]+\b|\bin [a-z0-9 -]+ days?\b",re.I)


@dataclass(frozen=True)
class ReadOnlyPlanningQuestion:
    reply:str


class _MissingDurationQuestion(DTO):
    # A control-only view. Source/unknown metadata is not accepted as facts;
    # the executable DTO and compiler below retain their original checks.
    model_config=ConfigDict(strict=True,extra='ignore',frozen=True)
    version:Literal['LIO-planning-intake.8']
    intent:Literal['plan','save','consult','discuss']
    reply:str=Field(min_length=1,max_length=12000)
    question_fields:list[Literal['duration_days']]=Field(min_length=1,max_length=1)
    current_source_index:int=Field(ge=0,le=0)
    planning_request_index:int=Field(ge=0,le=0)
    city:City
    duration_days:None
    start_date:None
    party_size:None
    publication_hold:None
    needs_tools:bool
    fixed_items:list=Field(max_length=0)
    extra_fields:dict=Field(max_length=0)
    extra_unknown_fields:list=Field(max_length=0)
    extra_uncertain_fields:dict=Field(max_length=0)
    unresolved:list=Field(max_length=0)
    long_term_requests:list=Field(max_length=0)


def _missing_duration_question(value,turns,refs,message_id,previous,schema):
    if (schema is not OptionalIntake or previous is not None or refs or len(turns)!=1
            or type(value)is not dict or value.keys()!=OptionalIntake.model_fields.keys()):
        return None
    try:control=_MissingDurationQuestion.model_validate(value)
    except ValidationError:return None
    text=turns[0].text;city=control.city
    if (city.source_index!=0 or not city.query.strip()or not city.quote.strip()
            or city.quote not in text or city.query not in city.quote):return None
    query=re.escape(city.query)
    direct=(re.fullmatch(r'\s*(?:(?:请|麻烦)\s*)?(?:(?:帮|给|为)(?:我|我们)\s*)?'
        r'(?:规划|安排|设计)\s*'+query+r'\s*的?(?:行程|旅行|旅游)\s*[。.!！?？]*',text,re.I)
        or re.fullmatch(r'\s*(?:please\s+)?(?:plan|organize|create)\s+'
        r'(?:(?:(?:a|my|our|the)\s+)?(?:trip|itinerary)\s+(?:to|in|for)\s+)?'+query+
        r'(?:\s+(?:trip|itinerary))?\s*[.?!]*',text,re.I))
    if direct is None or not control.reply.strip():return None
    try:reply_bytes=control.reply.encode('utf-8')
    except UnicodeError:return None
    if len(reply_bytes)>12000:return None
    # Only the literal query is retained, never proposed province/name or any
    # ignored execution metadata. Actual city resolution remains a later tool.
    fact=dict(value=dict(query=city.query,normalized_name=None,province=None,source_index=0,quote=city.quote),
              sources=[dict(message_id=message_id,quote=city.quote)])
    return ReadOnlyPlanningQuestion(control.reply),['duration_days'],{'city':fact}

def parse_flow(raw,turns,refs,message_id,previous,*,schema=FlowIntake):
    value=decode(raw.encode() if type(raw)is str else raw)
    question=_missing_duration_question(value,turns,refs,message_id,previous,schema)
    if question is not None:return question
    try:dto=schema.model_validate(value)
    except ValidationError:raise InvalidInput('exact unified planning facts required')from None
    data=dto.model_dump(by_alias=True,exclude_unset=True)
    intent=data['intent'];questions=data.pop('question_fields');hold=data.pop('publication_hold');request_index=data.pop('planning_request_index')
    if request_index is not None and request_index>=len(turns):raise InvalidInput('intake must bind the complete latest request')
    if hold is not None and (hold['source_index']>=len(turns)or hold['quote']not in turns[hold['source_index']].text):
        raise InvalidInput('field quote is not in the original message')
    source_ids=[ref['message_id']for ref in refs]+[message_id]
    # The stored context is scoped to the same conversation/generation. Reuse
    # only facts whose original MESSAGE is still present and checked by context.
    # The normal source/compiler boundary checks restored values and quotes too.
    saved={}if previous is None else previous.get('facts',{})
    city=data['city'];old_city=saved.get('city')
    same_city=(city is None or old_city is None or
        city['query'].casefold()==old_city['value']['query'].casefold()and
        (city['province']is None or old_city['value']['province']is None or city['province']==old_city['value']['province']))
    for field in ('city',*CORE):
        if field=='start_date'and not same_city:continue
        old=saved.get(field)
        if data[field]is not None or old is None or field in data['unknown_fields'] or field in data['uncertain_fields']:continue
        if any(ref['message_id']not in source_ids for ref in old['sources']):continue
        sources=[dict(source_index=source_ids.index(ref['message_id']),quote=ref['quote'])for ref in old['sources']]
        if field=='city':
            data[field]=dict(old['value'],source_index=sources[0]['source_index'],quote=sources[0]['quote'])
        else:
            data[field]=old['value']
            data['field_sources']=[ref for ref in data['field_sources']if ref['field']!=field]
            data['field_sources'].extend(dict(field=field,**ref)for ref in sources)
    # Data7 always validates supplied planning facts, even for consult/discuss.
    # The original compiler is reused unchanged; its temporary plan discriminator
    # grants nothing. The host determines authority only from traveler context.
    data.update(version='LIO-planning-intake.6',intent='plan'if intent!='cancel'else'cancel')
    try:intake=parse_sourced(json.dumps(data,ensure_ascii=False),turns,current_dates=dto.version=='LIO-planning-intake.8')
    except BookingSourceUnclear as error:
        error.control=replace(error.control,intent=intent,publication_hold=hold is not None,planning_request_index=request_index)
        raise
    intake=replace(intake,intent=intent,publication_hold=hold is not None,planning_request_index=request_index)
    if intent=='cancel':return intake,questions,{}
    # A previously classified ordinary consultation cannot later supply
    # execution facts merely because a model quotes it again on "continue".
    # Validate the received sources first, then withhold these known nonplanning
    # facts. This is a semantic hold, not repair of an invalid source/DTO.
    excluded=set()if previous is None else set(previous.get('nonplanning_message_ids',[]))
    blocked={field for field,sources in intake.sources.items()if any(source_ids[ref['source_index']]in excluded for ref in sources)}
    if intake.city is not None and source_ids[intake.city['source_index']]in excluded:
        intake=replace(intake,city=None);data['city']=None
    if blocked:
        fields=dict(intake.extraction['fields']);changes={}
        for field in blocked:
            if field=='start_date':changes['start_date']=dict(state='missing');data[field]=None
            elif field=='duration_days':changes['duration_days']=None;data[field]=None
            elif field=='party_size':fields[field]=dict(state='missing');data[field]=None
            elif field.startswith('fixed_items'):fields['fixed_items']=[]
            elif '.'in field:
                root,part=field.split('.',1)
                if root in fields:fields[root]=dict(fields[root],**{part:dict(state='missing')})
            elif field in fields:
                fields[field]=({}if field=='companions'else[]if field in ('temporary_conditions','fixed_items')else dict(state='missing'))
        if any(field.startswith('fixed_items')for field in blocked):blocked.update(field for field in intake.sources if field.startswith('fixed_items'))
        intake=replace(intake,**changes,extraction=dict(intake.extraction,fields=fields),
            sources={field:sources for field,sources in intake.sources.items()if field not in blocked})
    if dto.version!='LIO-planning-intake.8'and data['start_date']is not None and not any(ref['field']=='start_date'and DATE_EVIDENCE.search(ref['quote'])
            for ref in data['field_sources']):
        raise InvalidInput('original trip start source required')
    snapshot={}
    for field in ('city',*CORE):
        item=data[field]
        if item is None:continue
        sources=([dict(source_index=item['source_index'],quote=item['quote'])]if field=='city'else
                 [ref for ref in data['field_sources']if ref['field']==field])
        snapshot[field]=dict(value=item,sources=[dict(message_id=source_ids[ref['source_index']],quote=ref['quote'])for ref in sources])
    return intake,questions,snapshot if request_index is not None else saved
