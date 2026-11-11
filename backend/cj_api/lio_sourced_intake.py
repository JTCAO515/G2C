"""Validate sourced data6 once, then use the unchanged original domain compiler."""
import re
from pydantic import ValidationError
from cj_agent.lio_intake_facts_schema import SourcedIntake
from cj_needs.domain import InvalidInput,decode
from .lio_flat_intake import compile_flat

BOOKING={
    'booked':r'已(?:经)?(?:预订|订|预约|买票)|\b(?:booked|have tickets|has tickets|reservation confirmed)\b',
    'intended':r'打算(?:预订|预约)|准备(?:预订|预约)|\b(?:intend to book|plan to book)\b',
    'cancelled':r'(?:已|已经)取消(?:预订|预约)|\b(?:cancelled|canceled) (?:booking|reservation|tickets)\b',
}
CLAUSE=re.compile(r'([，,。.!?！？；;\n]|\b(?:and|but)\b|并且|但是)',re.I)
LINK=r'\s*(?:(?:is|was|has been|have been|already|the|our|my|a|an|for)\s+|(?:已|已经|现已|为|的|已经被|已被))*'
SUBJECT=r'(?:(?:我|我们|本人|全体|大家)\s*|(?:the|my|our|I|we|have|already)\s+)*'


def _booking_source(item,booking,items,turns):
    ref={key:booking[key]for key in ('source_index','quote')}
    primary={key:item[key]for key in ('source_index','quote')}
    if not any(ref['source_index']==source['source_index']and ref['quote']in source['quote']for source in (primary,*item['detail_refs'])):
        raise InvalidInput('explicit original booking evidence required')
    # Primary/detail index and bytes were checked by the original compiler.
    # Inspect the entire original clause, so clipping a negative prefix or a
    # different named target out of the supplied quote cannot create evidence.
    parts=CLAUSE.split(turns[ref['source_index']].text)
    clauses=[(parts[n],parts[n+1]if n+1<len(parts)else'')for n in range(0,len(parts),2)if ref['quote']in parts[n]]
    if len(clauses)!=1:raise InvalidInput('unique affirmative same-item booking source required')
    clause,separator=clauses[0];label=re.escape(item['label']);status=BOOKING[booking['status']]
    from .lio_planning_grounding import RANGE,ISO
    # Accept a whole direct declaration, not a keyword found inside a question,
    # quotation, denial, or a longer target name. Temporal/lock values are still
    # checked against their complete originals by the unchanged final guard.
    assertion=RANGE.sub(' ',re.sub(ISO,' ',clause))
    assertion=re.sub(r'不可更改|不能改|不可修改|不能修改','',assertion).strip()
    tied=re.fullmatch(SUBJECT+'(?:'+label+LINK+'(?:'+status+')|(?:'+status+')'+LINK+label+')',assertion,re.I)
    timed=[part for part in CLAUSE.split(primary['quote'])[::2]if RANGE.search(re.sub(ISO,' ',part))]
    following=r'(?=$|\s*(?:[，,。.!?！？；;:]|[0-9]|已|已经|预约|预订|集合|的|(?:is|was|has|have|from|at|on|for|meetup|meeting|appointment|booked)\b))'
    if (separator in ('?','？')or tied is None
            or any(re.search(label+following,part,re.I)is None for part in timed)
            or any(other is not item and other['label']in clause for other in items)):
        raise InvalidInput('unique affirmative same-item booking source required')


def parse_sourced(raw,turns):
    value=decode(raw.encode() if type(raw)is str else raw)
    try:dto=SourcedIntake.model_validate(value)
    except ValidationError:raise InvalidInput('exact sourced facts intake required')from None
    data=dto.model_dump(exclude_unset=True)
    sources={}
    for ref in data['field_sources']:
        sources.setdefault(ref['field'],[]).append({key:ref[key]for key in ('source_index','quote')})
    data['field_sources']=sources
    bookings=[]
    for item in data['fixed_items']:
        booking=item['booking_status']
        if booking is None:continue
        bookings.append((item,booking))
        item['booking_status']=booking['status']
    result=compile_flat(data,turns)
    if data['intent']in ('plan','save'):
        for item,booking in bookings:_booking_source(item,booking,data['fixed_items'],turns)
    return result
