"""Code selection of exact observed names and immutable adjacent route queries.

These projections grant no source eligibility. The host retains the genuine
registered provider capture/holds and final Source4 validation. A model English
name never becomes an official translation; unsourced display uses pinyin.
"""
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256
import json

from pypinyin import lazy_pinyin
from cj_needs.revision_lease import LeaseUnavailable
from cj_place.gaode import _binding_json
from cj_place.models import Coordinate,Endpoint
from cj_place.rich_routes import CityRoute,initial_mode
from cj_trip.structured_v4 import adjacent_pairs

from .lio_route_tool import RouteInput
from .local_lio_pipeline_calls import Call
from .local_lio_provider_sources import ROUTE_REGISTRATION


class PlaceSelectionBlocked(ValueError):pass


def _display_place(payload,source):
    english=' '.join(lazy_pinyin(payload['name_zh']))
    if len(english)>500 or payload['address']is not None and len(payload['address'])>500:return None
    return dict(deepcopy(payload),state='matched',name_en=english,name_en_source=None,source=deepcopy(source))


def matched_place(name,reply):
    """Only one exact observed identity; no fuzzy name or first-result guess.

    Missing/ambiguous data remains unconfirmed. That alone is not proof of a
    terminal unavailable tool outcome and cannot authorize a fallback save.
    """
    if reply is None or reply['status']!='ok':return None
    candidates=[row for row in reply['items']if row['place']is not None and row['place']['name_zh']==name]
    if len(candidates)!=1:return None
    row,=candidates
    return _display_place(row['place'],row['source'])


def lookup_places(skeleton,replies):
    """replies are decoded original registered results keyed by code target."""
    places={stop.item_id:matched_place(stop.name_zh,replies.get(stop.item_id))for stop in skeleton.stops}
    hotels=tuple(matched_place(names[0],replies.get('lodging-candidate-'+str(index)))
                 for index,names in enumerate(skeleton.hotels))
    return places,hotels


def lookup_selected_places(skeleton,source,binding,capture):
    """Format C's issued selection under its actual current publication holder.

    Do not repeat name matching or reinterpret a nonempty page as unavailable.
    Data returned here is not a capability; after new route calls the host must
    reseal providers and keep the final C holder through sole publication.
    """
    # C checks the actual issued capture once for this held batch. Formatting
    # below is pure; the enclosing source holder checks again on exit. Avoid
    # re-reading/rechecking every provider and profile for each individual stop.
    results={row['target']:row for row in source.selection_results(binding,capture)}
    def selected(target,keyword):
        result=results.get(target)
        if result is None:raise LeaseUnavailable('target has no original code-owned POI selection')
        if result['query_keyword']!=keyword:
            raise LeaseUnavailable('selection keyword differs from its original target query')
        if result['status']=='unavailable':return None
        if result['status']=='ambiguous':raise PlaceSelectionBlocked('place selection is ambiguous; preserve the current trip')
        record=result['selected_record']
        ref={key:record[key]for key in ('provider','kind','reference','sha256')}
        value=_display_place(record['payload'],ref)
        if value is None:raise PlaceSelectionBlocked('selected place cannot be represented without changing its original fields')
        return value
    places={stop.item_id:selected(stop.item_id,stop.name_zh)for stop in skeleton.stops}
    hotels=tuple(selected('lodging-candidate-'+str(index),names[0])for index,names in enumerate(skeleton.hotels))
    return places,hotels


def _query_key(origin,query):
    return json.dumps(dict(run_id=origin.binding.run_id,query=asdict(query)),sort_keys=True,
        separators=(',',':'),default=_binding_json).encode()


def route_calls(document,*,city,origin,sources):
    """Build after ordering/preflight, before dispatch; no endpoint inference.

    Identical exact queries in this one original RUN share an attempt. The host
    must retain and recheck that actual capture before reusing its result for
    each pair. Missing endpoints produce no query or guessed distance/duration.
    """
    items={item['id']:item for item in document['items']};calls=[];references={};seen={}
    for pair in adjacent_pairs(document):
        _,a,b=pair;places=tuple(items[key]['place']for key in (a,b))
        if any(place['state']!='matched'for place in places):references[pair]=None;continue
        try:endpoints=tuple(Endpoint(place['amap_id'],Coordinate(place['coordinate']['raw']),place['coordinate_role'])for place in places)
        except ValueError as error:
            if str(error)!='route_coordinate_precision':raise
            references[pair]=None;continue # keep the actual point; never round to make a request
        query=CityRoute(*endpoints,initial_mode(*endpoints),city)
        key=_query_key(origin,query)
        if key not in seen:
            reference='route-'+sha256(key).hexdigest()[:24]
            target='leg-'+sha256(json.dumps(pair,separators=(',',':')).encode()).hexdigest()[:24]
            calls.append(Call('gaode',ROUTE_REGISTRATION,RouteInput(query,reference,origin,sources,target)))
            seen[key]=reference
        references[pair]=seen[key]
    return tuple(calls),references


def taxi_fallback_calls(initial_calls,references,replies):
    """One taxi alternative after a definite unavailable transit observation.

    Inputs are the original registered calls and decoded observations retained
    by the host. Missing/UNKNOWN/transport failures never authorize another
    request. The caller dispatches these through the same PipelineCalls budget;
    the failed transit attempt is still charged, and the genuine provider
    capture/holds remain mandatory for final source eligibility.
    """
    calls=[];replacement={}
    for original in initial_calls:
        argument=original.argument
        if argument.query.mode!='transit':continue
        result=replies[argument.request_ref]
        if result['status']!='unavailable':continue
        query=replace(argument.query,mode='taxi')
        reference='route-'+sha256(_query_key(argument.origin,query)).hexdigest()[:24]
        calls.append(Call('gaode',ROUTE_REGISTRATION,replace(argument,query=query,request_ref=reference)))
        replacement[argument.request_ref]=reference
    return tuple(calls),{pair:replacement.get(reference,reference)for pair,reference in references.items()}


def apply_routes(document,references,replies):
    """Project completed original estimates onto the same frozen adjacency.

    The final Source4 validator still checks every referenced observation and
    exact endpoints. Unknown/unqueried legs stay unconfirmed, never zero-filled.
    No ordering, item, clock, booking or source eligibility is changed here.
    """
    value=deepcopy(document)
    for leg in value['legs']:
        reference=references[(leg['day_index'],leg['from_item_id'],leg['to_item_id'])]
        reply=None if reference is None else replies[reference]
        if reply is None or reply['status']!='ok'or not reply['items']:continue
        observed,=reply['items'];route=observed['route']
        leg.update(state='estimated',mode=route['mode'],duration_seconds=route['duration_seconds'],
                   distance_m=route['distance_m'],source=deepcopy(observed['source']))
    return value
