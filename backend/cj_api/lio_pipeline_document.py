"""Pure code projection from checked skeleton to the existing structured4 solver.

Provider places, protected items, date checks and subjects are host-supplied
validated data. This function neither captures their sources nor authorizes save.
The downstream genuine source validator/holds and sole publisher remain required.
"""
from copy import deepcopy
from datetime import date,timedelta

from cj_feasibility.rich_assembly import Activity
from cj_feasibility.rich_solver import DAY,Window
from cj_trip.structured_v4 import adjacent_pairs,validate_document


_PROPOSED_WINDOWS={'sight':(9*3600,18*3600,90*60),'lunch':(11*3600,14*3600,60*60),
                   'dinner':(17*3600,22*3600,60*60)}


def unconfirmed_place(names):
    zh,en=names
    return dict(state='unconfirmed',amap_id=None,name_zh=zh,name_en=en,name_en_source=None,
                coordinate=None,coordinate_role=None,address=None,source=None)


def _clock(seconds):
    return f'{seconds//3600:02d}:{seconds%3600//60:02d}'


def compile_document(skeleton,basis,*,locale,subjects,timezone,code_checks,places,hotel_places,
                     protected_items,protected_activities,legacy_sources):
    """Return (document, activities); input data is never a source grant.

    Proposed durations/windows are code suggestions, marked pending/unknown
    origin. Original protected items/constraints are copied without alteration.
    Explicit checks are retained verbatim, including conflicts and UNKNOWN.
    """
    first=None if basis.start_date is None else date.fromisoformat(basis.start_date)
    days=[]
    for index,area in enumerate(skeleton.areas,1):
        day=dict(day_index=index,theme=area,area=area)
        if first is not None:day['date']=(first+timedelta(days=index-1)).isoformat()
        days.append(day)
    items=deepcopy(list(protected_items));activities=list(protected_activities)
    for stop in skeleton.stops:
        lower,upper,duration=_PROPOSED_WINDOWS[stop.period or stop.kind]
        def event(clock):
            value=dict(day_index=stop.day_index,time=dict(state='known',value=_clock(clock)),
                       timezone=dict(state='known',value=timezone),utc_offset=dict(state='unknown'))
            return value
        proposed=unconfirmed_place((stop.name_zh,stop.name_en))
        place=deepcopy(places[stop.item_id])if places[stop.item_id]is not None else proposed
        text=place['name_zh']if locale=='zh'else place['name_en']+'（'+place['name_zh']+'）'
        items.append(dict(id=stop.item_id,text=text,verification='pending',evidence=[],
            schedule=dict(start=event(lower),end=event(lower+duration)),fixed=dict(state='known',value=False),
            source_category='unknown',source_refs=[],kind=stop.kind,place=place,note=None,tip=None,reason_refs=[]))
        offset=(stop.day_index-1)*DAY
        # Proximity is not inferred from an area name or an unconfirmed hotel.
        # The actual coordinate/proximity compiler may narrow these activities.
        activities.append(Activity(stop.item_id,(Window(offset+lower,offset+upper),),None,stop.period))
    hotels=[]
    for index,names in enumerate(skeleton.hotels):
        observed=hotel_places[index]
        hotels.append(dict(place=deepcopy(observed)if observed is not None else unconfirmed_place(names),
                           note=None,reason_refs=[]))
    document=dict(content_version='structured.4',title=skeleton.title,
        calendar=dict(state='undated')if first is None else dict(state='dated',start_date=basis.start_date),
        days=days,items=items,sources=deepcopy(list(legacy_sources)),date_checks=deepcopy(list(code_checks)),
        legs=[],lodging=dict(area=skeleton.lodging_area,recommendations=hotels))
    document['legs']=[dict(day_index=day,from_item_id=a,to_item_id=b,state='unconfirmed',mode=None,
        duration_seconds=None,distance_m=None,source=None,time_semantics='provider_estimate_at_query_time',future_guaranteed=False)
        for day,a,b in adjacent_pairs(document)]
    validate_document(document)
    # Participants belong to NEEDS/proposal projection, not invented Trip fields.
    proposed_subjects={stop.item_id:list(subjects)for stop in skeleton.stops}
    return document,tuple(activities),proposed_subjects
