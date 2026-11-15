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
from .lio_positive_trip import destination_query

CORE=('start_date','duration_days','party_size')
_META_REQUEST=re.compile(r'^\s*(?:(?:请帮我|请|帮我)?(?:(?:把|将)[^。！？!?\n]{0,40})?(?:翻译|复述|改写|引用)|'
    r'(?:(?:can|could|would) you\s+)?(?:please\s+)?(?:help(?: (?:me|us))?(?: to)?\s+)?'
    r'(?:translate|rephrase|paraphrase|repeat|quote)\b|how (?:do|would) (?:you|I) say\b|'
    r'(?:例如|示例|举例|假设|假如|如果|他说|她说|有人说)|'
    r'\b(?:for example|suppose|assuming|if|(?:he|she|they|someone) (?:said|says))\b)',re.I)
_META_SUFFIX=re.compile(r'^\s*(?:这(?:句|段)(?:话|内容)?|该句)?\s*(?:怎么|如何|怎样)(?:翻译|复述|改写|引用)',re.I)
_SOURCE_BREAK=re.compile(r'[。！？!?；;\n]|\.(?=\s+[A-Z]|$)|\b(?:but|however)\b|但是|不过|而是',re.I)


def _quoted_data_spans(text):
    pairs={'“':'”','「':'」','『':'』','‘':'’'};stack=[];spans=[];start=0
    for index,char in enumerate(text):
        if char in ("'",'’')and index>0 and index+1<len(text)and text[index-1].isalnum()and text[index+1].isalnum():continue
        if index>0 and text[index-1]=='\\'and char in ('"',"'",*pairs,*pairs.values()):continue
        if stack and char==stack[-1]:
            stack.pop()
            if not stack:spans.append((start,index+1))
        elif char in pairs or char in ('"',"'"):
            if not stack:start=index
            stack.append(pairs.get(char,char))
    if stack:spans.append((start,len(text)))
    return tuple(spans)


def _nonplanning_fact_source(text,quote):
    """Classify the cited span's task scope, not the whole message's first task.

    Translation data remains dialogue; later affirmative traveler facts remain
    data even in the same original. The schema/literal source validators run
    first, and no value or locator is repaired here.
    """
    spans=_quoted_data_spans(text)
    stripped=text.strip().rstrip('。.!！').strip()
    if any(text[start:end]==stripped for start,end in spans):return True
    breaks=tuple(part for part in _SOURCE_BREAK.finditer(text)
        if not any(start<=part.start()<end for start,end in spans))
    for found in re.finditer(re.escape(quote),text):
        before=[part.end()for part in breaks if part.end()<=found.start()]
        after=[part.start()for part in breaks if part.start()>=found.end()]
        start=before[-1]if before else 0;end=after[0]if after else len(text)
        if _META_REQUEST.search(text[start:found.end()]):return True
        for left,right in spans:
            if not left<=found.start()or not found.end()<=right:continue
            prefixes=re.split(r'[,，]',text[start:left])
            suffix=text[right:end]
            if (any(_META_REQUEST.search(prefix)for prefix in prefixes)or
                    _META_REQUEST.search(suffix)or _META_SUFFIX.search(suffix)):return True
    return False


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
    literal=destination_query(text,city.query)
    if (direct is None and literal is None)or not control.reply.strip():return None
    try:reply_bytes=control.reply.encode('utf-8')
    except UnicodeError:return None
    if len(reply_bytes)>12000:return None
    # Only the literal query is retained, never proposed province/name or any
    # ignored execution metadata. Actual city resolution remains a later tool.
    fact=dict(value=dict(query=literal if literal is not None else city.query,normalized_name=None,province=None,source_index=0,quote=city.quote),
              sources=[dict(message_id=message_id,quote=city.quote)])
    return ReadOnlyPlanningQuestion(control.reply),['duration_days'],{'city':fact}

def _rebind(ref,turns,offset):
    """Undo a Memory-slot count in one {source_index,quote} locator (#994).

    The quote stays the evidence: after the shift it must still be an exact
    span of that original traveler message, so Memory/system text never becomes
    a source. Any other wrong locator is not repaired and is rejected as before.
    """
    index,quote=ref.get('source_index'),ref.get('quote')
    if type(index)is not int or type(quote)is not str or not quote:return 0
    if 0<=index<len(turns)and quote in turns[index].text:return 0
    shifted=index-offset
    if 0<=shifted<len(turns)and quote in turns[shifted].text:
        ref['source_index']=shifted;return 1
    return 0


def rebind_sources(value,turns,*,memory_offset=0):
    """Correct Memory-shifted source locators before validation.

    memory_offset is the number of code-owned Memory user slots sent before the
    original traveler messages; the model may count them as traveler messages.
    Returns how many locators changed. Without Memory nothing is changed.
    """
    if type(value)is not dict or memory_offset<=0:return 0
    changed=0
    def walk(node):
        nonlocal changed
        if type(node)is dict:
            if 'source_index'in node and 'quote'in node:changed+=_rebind(node,turns,memory_offset)
            for child in node.values():walk(child)
        elif type(node)is list:
            for child in node:walk(child)
    walk(value)
    if memory_offset:
        for key in ('current_source_index','planning_request_index'):
            index=value.get(key)
            if type(index)is int and index>=len(turns)and 0<=index-memory_offset<len(turns):
                value[key]=index-memory_offset;changed+=1
    return changed


def schema_detail(error,schema):
    """Code-owned field/type names of a schema failure; never model values."""
    names=set(schema.model_fields)
    return ','.join(sorted({str(item['loc'][0])+':'+str(item['type'])for item in error.errors()
                            if item.get('loc')and item['loc'][0]in names})[:8])


def parse_flow(raw,turns,refs,message_id,previous,*,schema=FlowIntake,memory_offset=0):
    value=decode(raw.encode() if type(raw)is str else raw)
    rebound=rebind_sources(value,turns,memory_offset=memory_offset)
    if rebound:
        import logging
        logging.getLogger('cj_usage.audit').info('LIO_INTAKE_SOURCE_REBOUND message_id=%s count=%s',message_id,rebound)
    question=_missing_duration_question(value,turns,refs,message_id,previous,schema)
    if question is not None:return question
    try:dto=schema.model_validate(value)
    except ValidationError as failure:
        error=InvalidInput('exact unified planning facts required')
        error.detail=schema_detail(failure,schema)
        raise error from None
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
    meta_blocked=set();meta_city=False
    if dto.version=='LIO-planning-intake.8':
        # Meta-text remains ordinary dialogue, regardless of its RUN outcome.
        # Its otherwise valid quotes cannot become affirmative planning facts.
        meta_blocked={field for field,sources in intake.sources.items()if any(
            _nonplanning_fact_source(turns[ref['source_index']].text,ref['quote'])for ref in sources)}
        meta_city=intake.city is not None and _nonplanning_fact_source(
            turns[intake.city['source_index']].text,intake.city['quote'])
        if request_index is not None and _nonplanning_fact_source(turns[request_index].text,turns[request_index].text):
            intake=replace(intake,planning_request_index=None)
    blocked=meta_blocked|{field for field,sources in intake.sources.items()if any(source_ids[ref['source_index']]in excluded for ref in sources)}
    if intake.city is not None and (meta_city or source_ids[intake.city['source_index']]in excluded):
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
