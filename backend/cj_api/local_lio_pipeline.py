"""Native4 generation orchestration over original registered operations.

Preparation includes complete pre-city graph admission and genuine source
composition. Provider retrieval, final scheduling/checks and sole publication
are subsequent steps; the old preview factory is not replaced by preparation.
"""
from dataclasses import dataclass,replace
import json

from cj_message.lio_pipeline_schema import SKELETON
from cj_message.lio_wire import ExplorationOrigin
from cj_place.models import Coordinate

from .lio_city import CityReference
from .lio_pipeline_document import representation_size
from .lio_pipeline_model import SKELETON_SYSTEM,skeleton_data
from .lio_pipeline_preflight import preflight_document
from .lio_pipeline_skeleton import recipes,parse_skeleton
from .local_lio_pipeline_calls import PipelineCalls,PipelineCapacity,model_call
from .local_lio_pipeline_inputs import understand_constraints,planning_edges
from .local_lio_pipeline_search import sight_and_hotel_calls,meal_calls
from .local_lio_pipeline_sources import capture_pipeline_sources


class DestinationUnresolved(ValueError):
    def __init__(self,resolution):
        super().__init__('original destination requires clarification')
        self.resolution=resolution


@dataclass(frozen=True)
class PreparedPlan:
    skeleton:object
    projected:object
    projection:object
    edges:object
    calls:PipelineCalls
    sources:object
    city:CityReference
    preflight_size:tuple[int,int,int]
    id_prefix:str


def prepare_generation(host,worker,binding,view,*,locale,effective,prior_model_calls=0):
    """One understanding, one skeleton, whole graph, then city/source binding.

    effective is the code-accepted profile/default projection, not model input
    with write permission. The model only proposes bounded names. Every old
    Trip/fixed item, hotel anchor and explicit transfer endpoint is included
    before even the city lookup; nothing is cut, lightened or split to fit.
    """
    calls=PipelineCalls(worker,binding,prior_model_calls=prior_model_calls)
    constraints=understand_constraints(host,worker,binding,view,locale=locale)
    projected=constraints.project()
    day_count=effective['duration_days']
    edges=planning_edges(projected,day_count)
    expected=recipes(day_count,effective['pace'],light_first=edges.first_unknown_recipe,
        light_last=edges.last_unknown_morning)
    packet=model_call(host,worker,binding,view,SKELETON,SKELETON_SYSTEM,
        skeleton_data(effective,expected,locale=locale))
    raw,=calls.parallel((packet,))
    prefix='p4-'+binding.run_id[:12]
    skeleton=parse_skeleton(raw.encode(),expected,id_prefix=prefix)
    current=host.legacy.calendar.current(binding)
    retained=None if current is None else json.loads(current.trip.content)
    graph=preflight_document(skeleton,projected,edges,id_prefix=prefix,locale=locale,retained=retained)
    size=representation_size(graph)
    # This original one-send tool consumes the same45 allocation as POI/routes.
    resolution=calls.resolve_city(dict(query=effective['city'],normalized_name=None,province=None))
    if resolution['status']!='resolved':raise DestinationUnresolved(resolution)
    city=CityReference(**resolution['candidates'][0])
    projection=constraints.compile(day_count=day_count,city_reference=city,
        message_id=binding.message_id,run_id=binding.run_id)
    fields=projection.fields
    start=fields['arrival']['date']
    source=capture_pipeline_sources(host,worker,binding,view,fields,city,day_count=day_count,
        start_date=start['value']if start['state']=='known'else None)
    return PreparedPlan(skeleton,projected,projection,planning_edges(projection,day_count),
        calls,source,city,size,prefix)


def retrieve_skeleton(prepared):
    """Original POI2/nearby attempts and issued exact selections for all stops.

    This is retrieval, not the final assembler or a publication grant. Unknown
    receipts propagate without retry. Only the genuine selection reader can
    declare a lookup unavailable; ambiguity never becomes an empty-page flag.
    After routes or other provider operations, the caller must reseal and hold
    the complete source again through final assembly and sole publication.
    """
    skeleton=prepared.skeleton;bundle=prepared.sources
    sights=tuple(stop for stop in skeleton.stops if stop.kind=='sight')
    meals=tuple(stop for stop in skeleton.stops if stop.kind=='meal')
    if len(sights)+len(meals)+len(skeleton.hotels)>45-prepared.calls.gaode:
        raise PipelineCapacity('complete original place lookup set exceeds the remaining allowance')
    worker,binding=bundle.worker,bundle.binding
    origin=ExplorationOrigin(bundle.profiles.database,binding,worker.messages.query(binding.message_id))
    prepared.calls.parallel(sight_and_hotel_calls(sights,skeleton.hotels,city=prepared.city.adcode,
        origin=origin,sources=bundle.providers))
    first=bundle.seal()
    observed,_=bundle.places(replace(skeleton,stops=sights),first)
    anchors={}
    for stop in sights:
        place=observed[stop.item_id]
        if place is not None and stop.day_index not in anchors:
            anchors[stop.day_index]=Coordinate(place['coordinate']['raw'])
    centers={stop.item_id:anchors[stop.day_index]for stop in meals if stop.day_index in anchors}
    prepared.calls.parallel(meal_calls(meals,city=prepared.city.adcode,centers=centers,
        origin=origin,sources=bundle.providers))
    complete=bundle.seal()
    places,hotels=bundle.places(skeleton,complete)
    return places,hotels,complete


def compile_retrieved_plan(prepared,places,hotel_places,capture,*,checks,subjects,locale):
    """Read the current protected Trip under the same genuine provider frame.

    The returned document is data for C's assembler, not an issued check or
    publication grant. Routes, final checks, final resealing and the sole
    Source4 publisher remain required after this frame closes.
    """
    from .lio_pipeline_compilation import compile_retrieved
    bundle=prepared.sources;worker,binding=bundle.worker,bundle.binding
    def compile():
        with bundle.source.hold_for_publication(binding):
            bundle.source.check(binding,capture)
            current=bundle.source.contexts[binding]
            retained=None if current is None else json.loads(current.trip.content)
            return compile_retrieved(prepared,places,hotel_places,checks=checks,subjects=subjects,
                locale=locale,retained=retained)
    _,result=worker._step(binding,compile)
    return result
