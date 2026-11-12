"""One validated cumulative fact flow; no defaults and no model write capability."""
from dataclasses import replace
import json
import re
from pydantic import ValidationError
from cj_agent.lio_intake_flow_schema import FlowIntake
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

def parse_flow(raw,turns,refs,message_id,previous):
    value=decode(raw.encode() if type(raw)is str else raw)
    try:dto=FlowIntake.model_validate(value)
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
    same_city=(city is None or old_city is None or city['query'].casefold()==old_city['value']['query'].casefold())
    if same_city:
        for field in ('city',*CORE):
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
    try:intake=parse_sourced(json.dumps(data,ensure_ascii=False),turns)
    except BookingSourceUnclear as error:
        error.control=replace(error.control,intent=intent,publication_hold=hold is not None,planning_request_index=request_index)
        raise
    intake=replace(intake,intent=intent,publication_hold=hold is not None,planning_request_index=request_index)
    if intent=='cancel':return intake,questions,{}
    if data['start_date']is not None and not any(ref['field']=='start_date'and DATE_EVIDENCE.search(ref['quote'])for ref in data['field_sources']):
        raise InvalidInput('original trip start source required')
    snapshot={}
    for field in ('city',*CORE):
        item=data[field]
        if item is None:continue
        sources=([dict(source_index=item['source_index'],quote=item['quote'])]if field=='city'else
                 [ref for ref in data['field_sources']if ref['field']==field])
        snapshot[field]=dict(value=item,sources=[dict(message_id=source_ids[ref['source_index']],quote=ref['quote'])for ref in sources])
    return intake,questions,snapshot
