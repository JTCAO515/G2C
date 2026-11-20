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
from cj_trip.domain import packed

from .lio_city import _normalize
from .lio_pipeline_skeleton import CapacityExceeded,SkeletonUnavailable


_PROPOSED_WINDOWS={'sight':(9*3600,18*3600,90*60),'lunch':(11*3600,14*3600,60*60),
                   'dinner':(17*3600,22*3600,60*60)}
_GENERIC_ENDPOINTS=frozenset(map(_normalize, (
    '酒店','宾馆','民宿','住处','机场','车站','火车站','高铁站','航站楼','市区','市中心',
    'hotel','the hotel','my hotel','our hotel','airport','the airport','station','train station','city center','downtown',
)))


def declared_endpoint_names(fields,*,id_prefix,retained,city_names):
    """Names eligible for exact lookup from checked traveler observations."""
    retained_ids=set() if retained is None else {item['id'] for item in retained['items']}
    excluded=_GENERIC_ENDPOINTS|{_normalize(name)for name in city_names}

    def specific(observation):
        if observation.get('state')!='known':return None
        name=observation['value'].strip()
        normalized=_normalize(name)
        return name if normalized and normalized not in excluded else None

    names=[]
    for item in fields.get('fixed_items',()):
        start=specific(item['start']['place'])
        if item['item_id'] not in retained_ids and start is not None and start==specific(item['end']['place']):
            names.append((item['item_id'],start))
    for edge in ('arrival','departure'):
        name=specific(fields.get(edge,{}).get('place',{}))
        if name is not None:names.append((f'{id_prefix}-{edge}-transfer',name))
    return tuple(names)


def unconfirmed_place(names):
    zh,en=names
    return dict(state='unconfirmed',amap_id=None,name_zh=zh,name_en=en,name_en_source=None,
                coordinate=None,coordinate_role=None,address=None,source=None)


def _clock(seconds):
    return f'{seconds//3600:02d}:{seconds%3600//60:02d}'


def _event(day,seconds,timezone):
    # None is used only by the pre-city data projection, never a guessed zone.
    zone=dict(state='unknown')if timezone is None else dict(state='known',value=timezone)
    return dict(day_index=day,time=dict(state='known',value=_clock(seconds)),
                timezone=zone,utc_offset=dict(state='unknown'))


def representation_size(document):
    """Whole current graph, in canonical UTF-8 bytes; never a source grant.

    Call before any provider dispatch and recheck the final candidate. A capacity
    refusal preserves the old Trip and is not a successful richness result.
    """
    size=(len(document['items']),len(document['legs']),len(packed(document)))
    if size[0]>60 or size[1]>60 or size[2]>1_000_000:
        raise CapacityExceeded('complete plan exceeds the current representation capacity')
    return size


def lodging_anchors(place,edges,*,id_prefix,timezone,locale):
    """Explicit estimate anchor supplied by the host, not an inferred stay.

    Order-only minute points bracket the new tourist activities. Scheduling then
    uses the original feasible windows and C's frozen order, so return is not
    pinned to the end of the day. Protected facts are never included or moved.
    No hotel is selected, booked or assigned a source by this function.
    """
    if edges.status!='CONDITIONAL_WINDOW'or edges.unknowns:
        raise SkeletonUnavailable('resolved edge windows required for hotel-route estimates')
    items=[];order=[];schedule=[]
    for day,windows in enumerate(edges.windows,1):
        if not windows:raise SkeletonUnavailable('no usable source window for hotel-route estimates')
        earliest=((windows[0].start+59)//60)*60;latest=(windows[-1].end//60)*60
        if earliest>=latest:raise SkeletonUnavailable('no representable source window for hotel-route estimates')
        for kind,point in (('out',earliest),('back',latest)):
            key=f'{id_prefix}-lodging-d{day}-{kind}'
            name=place['name_zh']if locale=='zh'else place['name_en']+'（'+place['name_zh']+'）'
            text=(('酒店出发估算：'if kind=='out'else'返回酒店估算：')+name+'（推荐住处，入住未确认）'if locale=='zh'else
                  ('Estimated departure from 'if kind=='out'else'Estimated return to ')+name+'; suggested stay, unconfirmed')
            items.append(dict(id=key,text=text,verification='pending',evidence=[],
                schedule=dict(start=_event(day,point%DAY,timezone),end=_event(day,point%DAY,timezone)),fixed=dict(state='known',value=False),
                source_category='unknown',source_refs=[],kind='hotel',place=deepcopy(place),
                note=('往返按这家推荐酒店估算，可改为你的住处；未确认入住或预订。'if locale=='zh'else
                      'Routes use this suggested hotel as an estimate. You can change it; no stay or booking is confirmed.'),
                tip=None,reason_refs=[]))
            order.append(Activity(key,(Window(point,point),)))
            schedule.append(Activity(key,windows))
    return tuple(items),tuple(order),tuple(schedule)


def transfer_items(fields,day_count,*,id_prefix,locale):
    """Complete unscheduled transfer data for explicitly supplied endpoints.

    fields is the city-free original projection, not fields_for's destination
    defaults. No airport/station, coordinate, pickup time or booking is inferred.
    These items count in pre-city capacity and adjacency; they must be rebuilt
    with actual source windows before scheduling or publication.
    """
    items=[]
    for edge,day in (('arrival',1),('departure',day_count)):
        location=fields.get(edge,{}).get('place',{})
        if location.get('state')!='known':continue
        name=location['value'];key=f'{id_prefix}-{edge}-transfer'
        text=(('接送安排待确认：'if edge=='arrival'else'出发接送待确认：')+name if locale=='zh'else
              ('Unconfirmed pickup: 'if edge=='arrival'else'Unconfirmed departure transfer: ')+name)
        def event():return dict(day_index=day,time=dict(state='unknown'),
            timezone=dict(state='unknown'),utc_offset=dict(state='unknown'))
        items.append(dict(id=key,text=text,verification='pending',evidence=[],
            schedule=dict(start=event(),end=event()),fixed=dict(state='known',value=False),
            source_category='unknown',source_refs=[],kind='transport',place=unconfirmed_place((name,name)),
            note=('接送时间、服务和预订尚未确认。'if locale=='zh'else
                  'Transfer timing, service and booking are unconfirmed.'),tip=None,reason_refs=[]))
    return tuple(items)


def unconfirmed_legs(document):
    return [dict(day_index=day,from_item_id=a,to_item_id=b,state='unconfirmed',mode=None,
        duration_seconds=None,distance_m=None,source=None,time_semantics='provider_estimate_at_query_time',future_guaranteed=False)
        for day,a,b in adjacent_pairs(document)]


def compile_document(skeleton,basis,*,locale,subjects,timezone,code_checks,places,hotel_places,
                     protected_items,protected_activities,legacy_sources,additional_items=(),additional_activities=()):
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
    items=deepcopy([*protected_items,*additional_items]);activities=[*protected_activities,*additional_activities]
    for stop in skeleton.stops:
        lower,upper,duration=_PROPOSED_WINDOWS[stop.period or stop.kind]
        proposed=unconfirmed_place((stop.name_zh,stop.name_en))
        place=deepcopy(places[stop.item_id])if places[stop.item_id]is not None else proposed
        text=place['name_zh']if locale=='zh'else place['name_en']+'（'+place['name_zh']+'）'
        items.append(dict(id=stop.item_id,text=text,verification='pending',evidence=[],
            schedule=dict(start=_event(stop.day_index,lower,timezone),end=_event(stop.day_index,lower+duration,timezone)),fixed=dict(state='known',value=False),
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
    document['legs']=unconfirmed_legs(document)
    representation_size(document)
    validate_document(document)
    # Participants belong to NEEDS/proposal projection, not invented Trip fields.
    proposed_subjects={stop.item_id:list(subjects)for stop in skeleton.stops}
    proposed_subjects.update({item['id']:list(subjects)for item in additional_items})
    return document,tuple(activities),proposed_subjects
