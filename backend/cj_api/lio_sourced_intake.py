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


def parse_sourced(raw,turns):
    value=decode(raw.encode() if type(raw)is str else raw)
    try:dto=SourcedIntake.model_validate(value)
    except ValidationError:raise InvalidInput('exact sourced facts intake required')from None
    data=dto.model_dump(exclude_unset=True)
    sources={}
    for ref in data['field_sources']:
        sources.setdefault(ref['field'],[]).append({key:ref[key]for key in ('source_index','quote')})
    data['field_sources']=sources
    for item in data['fixed_items']:
        booking=item['booking_status']
        if booking is None:continue
        ref={key:booking[key]for key in ('source_index','quote')}
        primary={key:item[key]for key in ('source_index','quote')}
        if data['intent']in ('plan','save')and (not any(ref['source_index']==source['source_index']and ref['quote']in source['quote']for source in (primary,*item['detail_refs']))
                or re.search(BOOKING[booking['status']],ref['quote'],re.I)is None):
            raise InvalidInput('explicit original booking evidence required')
        item['booking_status']=booking['status']
    return compile_flat(data,turns)
