"""Native4 generation orchestration over original registered operations.

Preparation includes complete pre-city graph admission and genuine source
composition. Provider retrieval, final scheduling/checks and sole publication
are subsequent steps; the old preview factory is not replaced by preparation.
"""
from dataclasses import dataclass,replace
import json

from cj_message.lio_pipeline_schema import SKELETON,WORDING
from cj_message.lio_wire import ExplorationOrigin
from cj_place.models import Coordinate
from cj_feasibility.rich_assembly import assemble,assemble_unconfirmed
from cj_feasibility.rich_solver import Limits
from cj_agent.draft import DraftRejected
from cj_trip.rich_reasons import ProfileFact
from cj_trip.domain import packed

from .lio_city import CityReference
from .lio_pipeline_document import representation_size
from .lio_pipeline_model import SKELETON_SYSTEM,WORDING_SYSTEM,skeleton_data,wording_batches
from .lio_pipeline_wording import wording_items,apply_wording
from .lio_pipeline_preflight import admit_city_lookup,recipes_for_edges
from .lio_pipeline_skeleton import parse_skeleton
from .local_lio_pipeline_calls import PipelineCalls,PipelineCapacity,model_call
from .local_lio_pipeline_inputs import understand_constraints,planning_edges
from .local_lio_pipeline_search import sight_and_hotel_calls,meal_calls
from .local_lio_pipeline_sources import capture_pipeline_sources
from .local_lio_rich_checks import RichUncollectedChecks
from .local_lio_pipeline_routes import retrieve_routes


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
    calls=PipelineCalls(worker,binding,prior_model_calls=prior_model_calls,locale=locale)
    constraints=understand_constraints(host,worker,binding,view,locale=locale)
    projected=constraints.project()
    day_count=effective['duration_days']
    edges=planning_edges(projected,day_count)
    expected=recipes_for_edges(day_count,effective['pace'],edges)
    packet=model_call(host,worker,binding,view,SKELETON,SKELETON_SYSTEM,
        skeleton_data(effective,expected,locale=locale))
    raw,=calls.parallel((packet,))
    prefix='p4-'+binding.run_id[:12]
    skeleton=parse_skeleton(raw.encode(),expected,id_prefix=prefix)
    current=host.legacy.calendar.current(binding)
    retained=None if current is None else json.loads(current.trip.content)
    size,resolution=admit_city_lookup(skeleton,projected,edges,calls,id_prefix=prefix,locale=locale,retained=retained,
        query=dict(query=effective['city'],normalized_name=None,province=None))
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


def order_retrieved_plan(prepared,compiled,capture,*,locale,stop):
    """Source-held validation followed by C's pure bounded ordering.

    This does not publish a Trip. After order changes, route collection and
    final checks must run again; the old check capture cannot be reused.
    """
    return _assemble_retrieved(prepared,compiled,capture,compiled.document,phase='order',locale=locale,stop=stop)


def route_ordered_plan(prepared,document):
    """Query frozen adjacency, then seal all original provider operations anew."""
    bundle=prepared.sources;worker,binding=bundle.worker,bundle.binding
    origin=ExplorationOrigin(bundle.profiles.database,binding,worker.messages.query(binding.message_id))
    city=prepared.city.parent_city if prepared.city.parent_city is not None else prepared.city.name
    routed,_=retrieve_routes(document,calls=prepared.calls,city=city,origin=origin,providers=bundle.providers)
    representation_size(routed)
    return routed,bundle.seal()


def schedule_retrieved_plan(prepared,compiled,capture,document,*,locale,stop):
    """Freeze C's chosen order and schedule with the original observed legs."""
    return _assemble_retrieved(prepared,compiled,capture,document,phase='schedule',locale=locale,stop=stop)


def _assemble_retrieved(prepared,compiled,capture,document,*,phase,locale,stop):
    bundle=prepared.sources;worker,binding=bundle.worker,bundle.binding
    checks=RichUncollectedChecks(bundle.source)
    publisher=bundle.publisher(checks)
    def read():
        with bundle.source.hold_for_publication(binding):
            issued=checks.capture(binding,capture,document)
            rich=publisher.conditional_source(binding,capture,issued,document)
            facts=tuple(ProfileFact(row['factor_key'],row['state'],row['value']if type(row['value'])is str
                else json.dumps(row['value'],ensure_ascii=False))for row in capture.profile.profile['factors'])
            unconfirmed=frozenset(item['id']for item in document['items']
                if item['id']in compiled.proposed_subjects and item['kind']in ('sight','meal')
                and item['place']['state']=='unconfirmed')
            if not unconfirmed<=bundle.source.unavailable_targets(binding,capture):
                raise ValueError('unconfirmed stops require actual terminal source outcomes')
            return rich,facts,unconfirmed
    _,(rich,facts,unconfirmed)=worker._step(binding,read)
    arguments=dict(source=rich,facts=facts,activities=compiled.order_activities if phase=='order'else compiled.schedule_activities,
        edges=prepared.edges,phase=phase,locale=locale,limits=Limits(),stop=stop)
    if unconfirmed:return assemble_unconfirmed(document,**arguments,unconfirmed_items=unconfirmed)
    return assemble(document,**arguments)


def publish_retrieved_plan(prepared,compiled,capture,assembly):
    """Fresh final checks and the original sole selected writer, never a retry.

    The complete final body is captured after scheduling/wording. Uncollected
    weather/opening evidence stays UNKNOWN, and the issued source/Memory/Trip
    holders still decide commit. No previously issued check is carried across
    moved clocks. A refused/uncertain outcome propagates to the host unchanged.
    """
    if assembly.content is None:
        raise DraftRejected('complete scheduled candidate required')
    document=json.loads(assembly.content)
    representation_size(document)
    bundle=prepared.sources;worker,binding=bundle.worker,bundle.binding
    checks=RichUncollectedChecks(bundle.source)
    publisher=bundle.publisher(checks)
    original=worker.messages.query(binding.message_id)
    def publish():
        issued=checks.capture(binding,capture,document)
        document['date_checks']=issued.checks
        with bundle.source.message_context.hold_for_effect(binding)as message, \
                checks.hold(binding,issued,message)as check:
            check(document)
        final=replace(assembly,content=packed(document),date_checks_must_be_recomputed=False)
        return publisher.publish_assembly_for_message(binding,original,
            worker.message_context.active_original(binding),final,capture,checks=issued,
            proposed_subjects=compiled.proposed_subjects,before_publish=worker._publication_check)
    previous=worker.drafts
    worker.drafts=publisher
    try:
        return worker._step(binding,publish,lambda receipt:'trip_proposal:'+receipt.proposal_id,draft=True)
    finally:
        worker.drafts=previous


def word_retrieved_plan(host,prepared,compiled,capture,assembly,view,*,locale):
    """Spend only remaining model slots and retain every final item unchanged.

    Protected items, hotel disclaimers and route facts are not model targets.
    Wording has no source/write authority; the final checks/publisher must run
    after this returns, including when no date-specific evidence was collected.
    """
    if assembly.content is None:
        raise DraftRejected('complete scheduled candidate required before wording')
    document=json.loads(assembly.content)
    facts=tuple(ProfileFact(row['factor_key'],row['state'],row['value']if type(row['value'])is str
        else json.dumps(row['value'],ensure_ascii=False))for row in capture.profile.profile['factors'])
    items=wording_items(document,compiled.proposed_subjects)
    batches=wording_batches(items,available_models=prepared.calls.model_slots_left)
    bundle=prepared.sources
    calls=tuple(model_call(host,bundle.worker,bundle.binding,view,WORDING,WORDING_SYSTEM,
        dict(locale=locale,items=batch,factors=[dict(key=fact.key,state=fact.state,value=fact.display_value)
            for fact in facts if fact.state in ('known','memory')]))for batch in batches)
    results=prepared.calls.parallel(calls)
    value=apply_wording(document,tuple((batch,result.encode())for batch,result in zip(batches,results,strict=True)),facts=facts)
    representation_size(value)
    return replace(assembly,content=packed(value),
        date_checks_must_be_recomputed=assembly.date_checks_must_be_recomputed or value['calendar']['state']=='dated')
