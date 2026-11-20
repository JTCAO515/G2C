"""Complete retrieved data for C's order/schedule phases, never a save grant.

Places are C-issued selections and fields are the checked understanding. This
pure projection performs no lookup, obtains no holder and writes no Trip. The
host must capture/check/hold their actual sources again for final publication.
"""
from copy import deepcopy
from dataclasses import dataclass,replace

from cj_draft.calendar_plan import protected_base_data
from cj_feasibility.rich_assembly import Activity
from cj_feasibility.rich_solver import DAY,Window
from cj_place.models import Coordinate,Endpoint
from cj_place.rich_routes import initial_mode

from .lio_pipeline_document import compile_document,lodging_anchors,representation_size,transfer_items,unconfirmed_place,unconfirmed_legs
from .lio_pipeline_preflight import _CalendarData,fixed_day_map


@dataclass(frozen=True)
class CompiledPlanData:
    document:dict
    order_activities:tuple[Activity,...]
    schedule_activities:tuple[Activity,...]
    proposed_subjects:dict


def _protected_activity(item):
    points=[]
    for edge in ('start','end'):
        event=item['schedule'][edge]
        if event['time']['state']!='known'or event['timezone']!={'state':'known','value':'Asia/Shanghai'}:
            return Activity(item['id'],())
        hours,minutes=map(int,event['time']['value'].split(':'))
        points.append((event['day_index']-1)*DAY+hours*3600+minutes*60)
    # C's windows cover the whole occupied interval, not just allowed starts.
    # Its protected Visit also fixes the exact original start; neither bound
    # permits moving a fixed appointment to make the generated plan fit.
    return Activity(item['id'],(Window(*points),)if points[0]<=points[1]else())


def _nearby(place,hotel):
    if place is None or hotel is None:return None
    def endpoint(value):
        return Endpoint(value['amap_id'],Coordinate(value['coordinate']['raw']),value['coordinate_role'])
    # Reuse the existing observed-point walking policy; an area name is never
    # proximity evidence, and this is not a measured route or duration.
    return initial_mode(endpoint(place),endpoint(hotel))=='walking'


def compile_retrieved(prepared,places,hotel_places,*,checks,subjects,locale,retained):
    """Rebuild every preflight item with observed places, without defaults.

    retained is the actual current Trip data supplied by the held source (None
    means an explicit first plan). Known fixed clocks/locks and every retained
    item remain unchanged; unresolved protected/transfer clocks remain unknown
    for C to reject or clarify. Participants are supplied, never repaired here.
    """
    fields=prepared.projection.fields;skeleton=prepared.skeleton
    day_count=len(skeleton.areas)
    start=prepared.projection.start_date
    if start['state']!='known':start=fields.get('arrival',{}).get('date',{})
    start_date=start['value']if start.get('state')=='known'else None
    base=protected_base_data(fields,fixed_day_map(fields,day_count,start_date),day_count,
        start_date=start_date,retained=retained)
    protected=deepcopy(base['items'])
    fixed={item['item_id']:item for item in fields.get('fixed_items',())}
    for item in protected:
        if 'kind'in item:continue
        original=fixed.get(item['id'])
        kind=original['kind']if original is not None and original['kind']in ('hotel','transport')else'free_time'
        place=places.get(item['id'])
        item.update(kind=kind,place=deepcopy(place)if place is not None else unconfirmed_place(('待确认地点','Unconfirmed place')),
            note=None,tip=None,reason_refs=[])
    if retained is not None:skeleton=replace(skeleton,title=retained['title'])
    # These are already uniquely selected recommendation candidates, not raw
    # provider search rows or a traveler booking. Take the first available one
    # only as the disclosed hotel estimate used by the existing anchor builder.
    hotel=next((place for place in hotel_places if place is not None),None)
    suggested=hotel if hotel is not None else unconfirmed_place(skeleton.hotels[0])
    anchors,anchor_order,anchor_schedule=lodging_anchors(suggested,prepared.edges,
        id_prefix=prepared.id_prefix,timezone=prepared.city.timezone,locale=locale)
    # fields_for binds destination-city metadata to both NEEDS edges. That is
    # not a traveler-supplied airport/station or a request for pickup service.
    transfers=transfer_items(prepared.projected.fields,day_count,id_prefix=prepared.id_prefix,locale=locale)
    for item in transfers:
        place=places.get(item['id'])
        if place is not None:item['place']=deepcopy(place)
    transfer_bounds=tuple(Activity(item['id'],())for item in transfers)
    document,activities,proposed=compile_document(skeleton,_CalendarData(base['calendar'].get('start_date')),
        locale=locale,subjects=subjects,timezone=prepared.city.timezone,code_checks=checks,
        places=places,hotel_places=hotel_places,protected_items=protected,
        protected_activities=tuple(_protected_activity(item)for item in protected),legacy_sources=base['sources'],
        additional_items=(*anchors,*transfers),additional_activities=(*anchor_order,*transfer_bounds))
    stops={stop.item_id:stop for stop in skeleton.stops}
    order=tuple(replace(activity,nearby=_nearby(places[activity.item_id],hotel))
        if activity.item_id in stops else activity for activity in activities)
    schedule_hotels={activity.item_id:activity for activity in anchor_schedule}
    schedule=tuple(schedule_hotels.get(activity.item_id,activity)for activity in order)
    # Give the order solver tighter proposed meal windows first. This is a
    # search preference, not a new time constraint or travel estimate. Original
    # fixed/retained items keep their values and positions; C still chooses and
    # validates the actual order before any route can populate a leg.
    bounds={activity.item_id:activity for activity in order}
    for day in document['days']:
        positions=[index for index,item in enumerate(document['items'])
            if item['schedule']['start']['day_index']==day['day_index']
            and item['id']in proposed and item['kind']in ('sight','meal')]
        suggestions=sorted((document['items'][index]for index in positions),
            key=lambda item:min(window.end for window in bounds[item['id']].windows))
        for index,item in zip(positions,suggestions,strict=True):document['items'][index]=item
    document['legs']=unconfirmed_legs(document)
    representation_size(document) # Full observed UTF-8 bytes, including sources and all legs.
    return CompiledPlanData(document,order,schedule,proposed)
