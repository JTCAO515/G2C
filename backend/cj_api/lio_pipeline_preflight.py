"""Complete pre-city graph data; no NEEDS/source capture or save permission.

The actual host must call this before any Gaode request. It later binds the
original city, repeats full field/source checks and rebuilds from held sources;
neither this graph nor a successful size result may be used as a source grant.
"""
from copy import deepcopy
from dataclasses import dataclass,replace
from datetime import date

from cj_needs.domain import InvalidInput

from .lio_calendar_ordinals import fixed_ordinals
from .lio_pipeline_document import compile_document,lodging_anchors,transfer_items,unconfirmed_place,representation_size,_PROPOSED_WINDOWS
from .lio_pipeline_skeleton import recipes


@dataclass(frozen=True)
class _CalendarData:
    start_date:str|None


def recipes_for_edges(day_count,pace,edges):
    """Use real first/last-day bounds before asking the model for stops.

    Only infeasible suggested meal periods are excluded. This does not alter
    protected commitments, lower the requested sights, or trim a large plan.
    """
    original=recipes(day_count,pace,light_first=edges.first_unknown_recipe,
        light_last=edges.last_unknown_morning)
    result=[]
    for row in original:
        if row.day_index not in (1,day_count):result.append(row);continue
        offset=(row.day_index-1)*86400
        def fits(period):
            lower,upper,duration=_PROPOSED_WINDOWS[period]
            return any(max(window.start,offset+lower)+duration<=min(window.end,offset+upper)
                for window in edges.windows[row.day_index-1])
        result.append(replace(row,meals=tuple(period for period in row.meals if fits(period))))
    return tuple(result)


def admit_city_lookup(skeleton,projection,edges,calls,*,query,id_prefix,locale,retained):
    """The full candidate is checked before even the first city request.

    Returning from this gate grants no NEEDS/Trip/source authority. The host
    still compiles and checks the final observed candidate at publication.
    """
    document=preflight_document(skeleton,projection,edges,id_prefix=id_prefix,
        locale=locale,retained=retained)
    size=representation_size(document)
    return size,calls.resolve_city(query)


def fixed_day_map(fields,day_count,start_date):
    """Same explicit ordinal/literal-date policy as the genuine calendar reader.

    Unknown mappings stop before city dispatch. No day-one or plan-now-date
    fallback is introduced. The final source reader independently rereads the
    actual historical messages and verifies the complete mapping.
    """
    first=None if start_date is None else date.fromisoformat(start_date)
    result={}
    for item in fields.get('fixed_items',()):
        try:pair=fixed_ordinals(item['description'],day_count)
        except InvalidInput:
            if first is None:raise InvalidInput('fixed arrangement needs an explicit day before lookup')from None
            indices=[]
            for edge in ('start','end'):
                observed=item[edge]['date']
                if observed['state']!='known'or observed['value']not in item['description']:
                    raise InvalidInput('fixed date needs its original literal before lookup')from None
                indices.append((date.fromisoformat(observed['value'])-first).days+1)
            if not 1<=indices[0]<=indices[1]<=day_count:
                raise InvalidInput('fixed date is outside the requested calendar')
            pair=tuple(indices)
        result[item['item_id']]=pair
    return result


def preflight_document(skeleton,projection,edges,*,id_prefix,locale,retained=None):
    """Measure all protected/proposed/hotel/transfer items and adjacent legs.

    Provider-dependent fields remain explicitly unconfirmed. Their final size
    must be checked again after the original observations arrive; this result
    makes no claim about a future provider payload or publication eligibility.
    """
    from cj_draft.calendar_plan import protected_base_data
    day_count=len(skeleton.areas)
    start=projection.start_date
    if start['state']!='known':start=projection.fields.get('arrival',{}).get('date',{})
    start_date=start['value']if start.get('state')=='known'else None
    mapping=fixed_day_map(projection.fields,day_count,start_date)
    base=protected_base_data(projection.fields,mapping,day_count,start_date=start_date,retained=retained)
    protected=deepcopy(base['items'])
    fixed={item['item_id']:item for item in projection.fields.get('fixed_items',())}
    for item in protected:
        if 'kind'in item:continue # preserve the complete original rich metadata
        original=fixed.get(item['id'])
        kind=original['kind']if original is not None and original['kind']in ('hotel','transport')else'free_time'
        item.update(kind=kind,place=unconfirmed_place(('待确认地点','Unconfirmed place')),
                    note=None,tip=None,reason_refs=[])
    if retained is not None:skeleton=replace(skeleton,title=retained['title'])
    # Explicitly a suggested stay estimate, not a chosen/booked user hotel.
    lodging=unconfirmed_place(skeleton.hotels[0])
    hotels,hotel_order,_=lodging_anchors(lodging,edges,id_prefix=id_prefix,timezone=None,locale=locale)
    transfers=transfer_items(projection.fields,day_count,id_prefix=id_prefix,locale=locale)
    dated=base['calendar']['state']=='dated'
    checks=[dict(kind=kind,state='unknown'if dated else'not_checked',day_indices=list(range(1,day_count+1)),
        item_ids=[],reason='date_evidence_not_collected'if dated else'date_not_set',evidence_refs=[])
        for kind in ('weather','day_opening')]
    document,_,_=compile_document(skeleton,_CalendarData(base['calendar'].get('start_date')),
        locale=locale,subjects=(),timezone=None,code_checks=checks,
        places={stop.item_id:None for stop in skeleton.stops},hotel_places=(None,)*len(skeleton.hotels),
        protected_items=protected,protected_activities=(),legacy_sources=base['sources'],
        additional_items=(*hotels,*transfers),additional_activities=hotel_order)
    return document
