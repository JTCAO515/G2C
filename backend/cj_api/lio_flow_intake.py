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
from .lio_positive_trip import destination_query,known_city_term
from .lio_planning_grounding import NUMBER,OPEN_PLAN
from .lio_national_intake import ZONE_LITERAL,_clock_zone_marker

CORE=('start_date','duration_days','party_size')
_CHONGQING_CITY_ANSWER=re.compile(r'^\s*(?:去)?(?P<city>重庆|Chongqing)(?:,\s*China)?[。.!！]',re.I)
_UNKNOWN_HOTEL_SITE=re.compile(r'酒店名称和位置尚未确定[。！]?|(?:the )?hotel name and location are (?:not known yet|unknown)\.?',re.I)
_SAME_MEETUP_LOCK=re.compile(r';\s*keep it unchanged(?:[.!](?=\s|$)|\s*\Z)',re.I)
_EXPLICIT_START_TOMORROW=re.compile(r'(?:从明天开始|明天起|\b(?:starting|start|from) tomorrow)\Z',re.I)
_CITY_DURATION_PHRASE=re.compile(
    rf'\s*(?:(?:我|我们)?(?:想|要)?去(?P<zh>[\u4e00-\u9fff]+?)(?:玩|逛)(?:{NUMBER})[天日]'
    rf"|(?:I|we) (?:want|would like) to spend (?:{NUMBER}) days? in (?P<en>[\w'-]+))[。.!！]?\s*",re.I)
_SHORT_PLAN=re.compile(
    rf'(?:(?:请|麻烦)?(?:帮|给|为)(?:我们|我))?\s*(?:规划|安排)\s*(?:{NUMBER})\s*天'
    rf'|(?:(?:could|can|would) you\s+|please\s+)?(?:help (?:me|us) (?:to )?)?plan\s+(?:{NUMBER})\s+days?',re.I)
_DATE_REVISION=re.compile(
    r'日期|改期|改天|改[成为到]|出发|启程|起程|到达|抵达|返程|提前|推迟|延期|另选|换一天|取消|之前那天|原来那天'
    r'|\b(?:actually|instead|dates?|start(?:ing)?|depart\w*|arriv\w*|reschedul\w*|'
    r'postpon\w*|delay\w*|earlier|later|(?:previous|old) (?:day|time))\b',re.I)
_TRAVEL_ENDPOINT=re.compile(r'到达|抵达|起飞|落地|返程|\b(?:arriv\w*|depart\w*|flight|train|land(?:s|ing|ed)?)\b',re.I)
_META_REQUEST=re.compile(r'^\s*(?:(?:请帮我|请|帮我)?(?:(?:把|将)[^。！？!?\n]{0,40})?(?:翻译|复述|改写|引用)|'
    r'(?:(?:can|could|would) you\s+)?(?:please\s+)?(?:help(?: (?:me|us))?(?: to)?\s+)?'
    r'(?:translate|rephrase|paraphrase|repeat|quote)\b|how (?:do|would) (?:you|I) say\b|'
    r'(?:例如|示例|举例|假设|假如|如果|他说|她说|有人说)|'
    r'\b(?:for example|suppose|assuming|if|(?:he|she|they|someone) (?:said|says))\b)',re.I)
_META_SUFFIX=re.compile(r'^\s*(?:这(?:句|段)(?:话|内容)?|该句)?\s*(?:怎么|如何|怎样)(?:翻译|复述|改写|引用)',re.I)
_SOURCE_BREAK=re.compile(r'[。！？!?；;\n]|\.(?=\s+[A-Z]|$)|\b(?:but|however)\b|但是|不过|而是',re.I)
_SELF_FACT=re.compile(r'^\s*(?:(?:and|but)\s+)?(?:(?:I|we)\s+(?:actually\s+)?(?:start|depart|leave|arrive|are|will|plan|have)\b|'
    r'(?:我(?:们)?|本次行程)(?:实际|确定|将|会|要|计划|从|是|有|共|一共))',re.I)
_META_TASK_WORD=re.compile(r'翻译|复述|改写|引用|\b(?:translat\w*|rephras\w*|paraphras\w*|repeat\w*|quot\w*)\b',re.I)


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
        if _META_REQUEST.search(text[start:found.end()]):
            # A quoted task object has ended. A separate explicit first-person
            # assertion after its separator is not part of that quoted task.
            ended=[right for left,right in spans if start<=left and right<=found.start()
                and _META_REQUEST.fullmatch(text[start:left].strip().rstrip(':：').strip())]
            declaration=''if not ended else text[ended[-1]:found.end()].lstrip(' ,，')
            if not (_SELF_FACT.search(declaration)and not _META_TASK_WORD.search(declaration)):
                return True
        for left,right in spans:
            if not left<=found.start()or not found.end()<=right:continue
            prefixes=re.split(r'[,，]',text[start:left])
            suffix=text[right:end].lstrip(' ,，:：')
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


@dataclass
class ReadOnlyPlanningData:
    """Validated dialogue DATA, separate from the execution projection.

    No NEEDS fields, planning root, grant or publisher belongs to this view.
    Known-nonplanning and failed originals may inform a read-only answer;
    meta/quoted task data is still withheld after the original source checks.
    """
    city:dict|None=None
    duration_days:int|None=None
    start_date:dict|None=None
    arrival_date:dict|None=None
    departure_date:dict|None=None
    sources:dict|None=None
    facts:dict|None=None


class _MissingDurationQuestion(DTO):
    # A control-only view. Source/unknown metadata is not accepted as facts;
    # the executable DTO and compiler below retain their original checks.
    model_config=ConfigDict(strict=True,extra='ignore',frozen=True)
    version:Literal['LIO-planning-intake.8']
    intent:Literal['plan','save','consult','discuss']
    reply:str=Field(min_length=1,max_length=12000)
    question_fields:list[Literal['duration_days']]=Field(min_length=1,max_length=1)
    current_source_index:int=Field(ge=0,le=0)
    planning_request_index:int|None=Field(ge=0,le=0)
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


def _missing_duration_question(value,turns,refs,message_id,previous,schema,*,validated_plan=False):
    if (schema is not OptionalIntake or previous is not None or refs or len(turns)!=1
            or type(value)is not dict or value.keys()!=OptionalIntake.model_fields.keys()):
        return None
    try:control=_MissingDurationQuestion.model_validate(value)
    except ValidationError:return None
    # A plan-labelled city question can leave its future planning root unset.
    # This still retains only literal city DATA and grants no execution; the
    # later complete intake must supply its own validated planning root.
    if control.planning_request_index is None and (not validated_plan or control.intent!='plan'):return None
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


def _fact_snapshot(data,source_ids,blocked=()):
    snapshot={}
    for field in ('city',*CORE):
        item=data[field]
        if item is None or field in blocked:continue
        sources=([dict(source_index=item['source_index'],quote=item['quote'])]if field=='city'else
                 [ref for ref in data['field_sources']if ref['field']==field])
        snapshot[field]=dict(value=item,sources=[dict(message_id=source_ids[ref['source_index']],quote=ref['quote'])for ref in sources])
    return snapshot


def _date_reopened(text):
    return DATE_EVIDENCE.search(text) is not None or _DATE_REVISION.search(text) is not None


def _require_current_city_continuation_dates(intake, previous, turns):
    if (previous is None or intake.city is None or intake.intent not in ('plan','save')
            or previous.get('status') not in ('needs_city','needs_details')
            or previous.get('authority') not in ('plan','save') or 'city' in previous.get('facts',{})):
        return
    latest=max((index for index,turn in enumerate(turns)if _date_reopened(turn.text)),default=0)
    for field in ('start_date','arrival.date','departure.date'):
        sources=intake.sources.get(field,())
        if sources and all(ref['source_index']<latest for ref in sources):
            raise InvalidInput('trip date source precedes the latest original date instruction')


def _explicit_trip_start_quote(text, city=None):
    # Restore only a start phrase attached to the original planning request.
    # A date elsewhere in the message cannot source this trip's start.
    boundary=_SOURCE_BREAK.search(text)
    first_clause=text.strip()
    if boundary is not None:
        rest=text[boundary.end():].strip()
        if boundary[0].isalpha()or (city is None and rest)or _date_reopened(rest):return None
        first_clause=text[:boundary.start()].strip()
    start=_EXPLICIT_START_TOMORROW.search(first_clause)
    if start is None or text.count(start[0])!=1:return None
    request=first_clause[:start.start()].rstrip(' ,，')
    if city is not None and known_city_term(city):
        request=re.sub(r'\b'+re.escape(city)+r'\s+(?=(?:trip|itinerary|visit)\Z)', '',request,flags=re.I)
    if OPEN_PLAN.fullmatch(request)or _SHORT_PLAN.fullmatch(request):return start[0]
    return None


def _continue_trip_start_quote(text):
    boundary=_SOURCE_BREAK.search(text)
    first=text if boundary is None else text[:boundary.start()]
    rest='' if boundary is None else text[boundary.end():]
    start=_EXPLICIT_START_TOMORROW.fullmatch(first.strip())
    if start is not None and not _date_reopened(rest):return start[0]
    return None


def _normalize_city_phrase(city,turns):
    if city is None or city['source_index']>=len(turns):return
    text=turns[city['source_index']].text
    if city['query']!=city['quote'] or city['quote'].strip()!=text.strip():return
    match=_CITY_DURATION_PHRASE.fullmatch(text)
    if match is None:return
    name=match['zh'] or match['en']
    if known_city_term(name):city.update(query=name,quote=name)


def _normalize_optional_fixed_items(items,turns):
    paths=('start_place','end_place')
    endpoints=tuple(edge+'_'+part for edge in ('start','end') for part in ('date','time','timezone','place'))
    meetup_sources={item['source_index']for item in items if item['locked'] is True
        and item['start_time'] is not None and item['end_time'] is not None
        and re.fullmatch(r'hotel meetup|酒店集合',item['label'],re.I)}
    items[:]=[item for item in items if not (
        item['kind']=='hotel' and item['source_index']in meetup_sources and item['source_index']<len(turns)
        and item['locked'] is False and item['booking_evidence']is None and not item['detail_refs']
        and all(item[path]is None for path in endpoints)
        and sorted(item['unknown_fields'])==sorted(paths)
        and item['uncertain_fields']=={'name_and_location':item['quote']}
        and _UNKNOWN_HOTEL_SITE.fullmatch(item['quote']) and _UNKNOWN_HOTEL_SITE.fullmatch(item['label'])
        and item['quote'] in turns[item['source_index']].text)]
    original_zone=any(ZONE_LITERAL.search(turn.text)or _clock_zone_marker(turn.text)for turn in turns)
    for item in items:
        for edge in ('start','end'):
            path=edge+'_time'
            value=item[path]
            if value is not None and re.fullmatch(r'[0-9]{2}:[0-9]{2}:00',value):
                item[path]=value[:5]
        unknown=item['unknown_fields']
        uncertain=item['uncertain_fields']
        if item['source_index']>=len(turns):continue
        text=turns[item['source_index']].text
        hotel=item['kind']=='hotel' or re.fullmatch(r'hotel meetup|酒店集合',item['label'],re.I)
        if hotel and not original_zone:
            for path in ('start_timezone','end_timezone'):
                if item[path] is None and unknown.count(path)<=1 and uncertain.get(path)in (
                        None,'timezone not stated in original message'):
                    if path in unknown:unknown.remove(path)
                    uncertain.pop(path,None)
        aliases=uncertain.keys()&{'place','hotel_location'}
        alias=next(iter(aliases))if len(aliases)==1 else None
        note=uncertain.get(alias)
        if (hotel and note and _UNKNOWN_HOTEL_SITE.fullmatch(note)
                and note.casefold()in text.casefold()
                and all((item[path] is None or item[path].casefold()in ('hotel','the hotel','酒店'))
                        and path not in unknown and path not in uncertain for path in paths)):
            del uncertain[alias]
            unknown.extend(paths)
            for path in paths:item[path]=None
        if hotel and all(item[path] is None for path in paths):
            # A standalone missing hotel name carries no values to bind to
            # the fixed clock or reservation.
            item['detail_refs']=[ref for ref in item['detail_refs']if not (
                ref['source_index']==item['source_index'] and ref['quote'] in text
                and _UNKNOWN_HOTEL_SITE.fullmatch(ref['quote']))]
        quote=item['quote']
        if (hotel and item['locked'] is False and 'locked' not in unknown and 'locked' not in uncertain
                and text.count(quote)==1):
            inside=_SAME_MEETUP_LOCK.search(quote)
            ending=_SAME_MEETUP_LOCK.match(text,text.index(quote)+len(quote))
            if ending or inside and inside.end()==len(quote):
                if ending:item['quote']+=ending[0]
                item['locked']=True


def _drop_unsourced_hotel_endpoint_aliases(data,turns):
    if not data['fixed_items'] or any(_TRAVEL_ENDPOINT.search(turn.text) for turn in turns):return
    for edge in ('arrival','departure'):
        key=edge+'.location'
        note=data['extra_uncertain_fields'].get(key)
        if (edge in data['extra_fields'] and data['extra_unknown_fields'].count(key)==1
                and note and _UNKNOWN_HOTEL_SITE.fullmatch(note)
                and any(note.casefold()in turn.text.casefold()for turn in turns)
                and not any(ref['field'].startswith(edge+'.')for ref in data['field_sources'])
                and not any(path.startswith(edge+'.') and path!=key
                            for path in (*data['extra_uncertain_fields'],*data['extra_unknown_fields']))):
            del data['extra_fields'][edge],data['extra_uncertain_fields'][key]
            data['extra_unknown_fields'].remove(key)


def parse_flow(raw,turns,refs,message_id,previous,*,schema=FlowIntake,memory_offset=0,read_only=None):
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
    if dto.version=='LIO-planning-intake.8':
        # Both markers encode absence for an unsourced optional party size.
        # Retain UNKNOWN without copying the model's redundant note into NEEDS.
        # A value, source, previous known count or any other duplicate still
        # goes through the original observation validation.
        unknown=data['unknown_fields']
        party_note=data['uncertain_fields'].get('party_size')
        if (data['party_size'] is None and 'party_size'in unknown and 'party_size' not in saved
                and not any(ref['field']=='party_size' for ref in data['field_sources'])):
            if data['duration_days'] is None and questions==['duration_days']:
                while unknown.count('party_size')>1:unknown.remove('party_size')
            if unknown.count('party_size')==1 and party_note and party_note.strip()and len(party_note.encode())<=4096:
                del data['uncertain_fields']['party_size']
        # A duration clarification may repeat the absence marker for a
        # separately sourced date. Keep the original date validator.
        if (data['duration_days'] is None and questions==['duration_days'] and data['start_date'] is not None
                and 'start_date' not in data['uncertain_fields']
                and any(ref['field']=='start_date'for ref in data['field_sources'])):
            unknown[:]=[field for field in unknown if field!='start_date']
        _normalize_optional_fixed_items(data['fixed_items'],turns)
        _drop_unsourced_hotel_endpoint_aliases(data,turns)
        _normalize_city_phrase(data['city'],turns)
        if (previous is not None and previous.get('status')=='plan_preview'
                and previous.get('authority') in ('plan','save') and 'city' in saved
                and request_index is not None and request_index<len(turns)-1 and intent=='plan'
                and data['city'] is None and data['start_date'] is not None
                and not any(ref['field']=='start_date'for ref in data['field_sources'])):
            quote=_continue_trip_start_quote(turns[-1].text)
            if quote is not None:
                data['field_sources'].append(dict(field='start_date',source_index=len(turns)-1,quote=quote))
        if (previous is None and request_index==0 and intent=='plan' and data['start_date'] is not None
                and not any(ref['field']=='start_date'for ref in data['field_sources'])):
            city=data['city']
            quote=_explicit_trip_start_quote(turns[0].text,city['query']if city is not None else None)
            if quote is not None:
                data['field_sources'].append(dict(field='start_date',source_index=0,quote=quote))
        # Historical snapshots may predate the task-scope filter. Reuse only
        # affirmative source spans; returning an unchanged cache must not keep
        # translated facts alive after the execution projection withheld them.
        saved={field:fact for field,fact in saved.items()if not any(
            ref['message_id']in source_ids and _nonplanning_fact_source(
                turns[source_ids.index(ref['message_id'])].text,ref['quote'])for ref in fact['sources'])}
        duration=saved.get('duration_days')
        city_answer=_CHONGQING_CITY_ANSWER.match(turns[-1].text)
        if (city_answer and previous is not None and previous.get('status') in ('needs_city','needs_details')
                and previous.get('authority') in ('plan','save') and intent=='plan' and 'city' not in saved
                and duration is not None and duration['value']==data['duration_days']):
            name=city_answer['city']
            if data['city'] is None:
                data['city']=dict(query=name,normalized_name=None,province=None,source_index=len(turns)-1,quote=name)
            if data['start_date'] is not None and not any(ref['field']=='start_date'for ref in data['field_sources']):
                source_indexes={source_ids.index(ref['message_id'])for ref in duration['sources']
                                if ref['message_id']in source_ids[:-1]}
                if len(source_indexes)==1:
                    source_index=source_indexes.pop()
                    quote=_explicit_trip_start_quote(turns[source_index].text)
                    if quote is not None:
                        data['field_sources'].append(dict(field='start_date',source_index=source_index,quote=quote))
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
    _require_current_city_continuation_dates(intake,previous,turns)
    if schema is OptionalIntake and intent=='plan'and request_index is None:
        # This null-root variant only reaches the DATA-only question after the
        # complete DTO and original source/compiler checks above have passed.
        question=_missing_duration_question(value,turns,refs,message_id,previous,schema,validated_plan=True)
        if question is not None:return question
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
    if read_only is not None:
        # Only a complete source/compiler-validated result reaches this point.
        # The execution-only exclusions below must not erase human dialogue.
        read_only.city=None if meta_city else intake.city
        read_only.duration_days=None if 'duration_days'in meta_blocked else intake.duration_days
        read_only.start_date=None if 'start_date'in meta_blocked else intake.start_date
        fields=intake.extraction['fields']
        read_only.arrival_date=None if 'arrival.date'in meta_blocked else fields.get('arrival',{}).get('date')
        read_only.departure_date=None if 'departure.date'in meta_blocked else fields.get('departure',{}).get('date')
        read_only.sources={key:refs for key,refs in intake.sources.items()if key not in meta_blocked}
        read_only.facts=_fact_snapshot(data,source_ids,meta_blocked|({'city'}if meta_city else set()))
    # Only a host-produced read-only trip context can retain human DATA from
    # a denied root. The authority checker still sees the full exclusion set;
    # ordinary nonplanning sources and meta/quoted task data stay withheld.
    data_excluded=excluded-(set()if previous is None else set(previous.get('read_only_data_message_ids',[])))
    blocked=meta_blocked|{field for field,sources in intake.sources.items()if any(source_ids[ref['source_index']]in data_excluded for ref in sources)}
    if intake.city is not None and (meta_city or source_ids[intake.city['source_index']]in data_excluded):
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
    snapshot=_fact_snapshot(data,source_ids)
    return intake,questions,snapshot if request_index is not None else saved
