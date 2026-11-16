"""Complete code-owned POI query sets; no source or publication authority.

Build the requests before admission/dispatch. A caller must preflight the full
skeleton and original budget, then use PipelineCalls and the genuine provider
capture. These are candidate pools, not claims that a venue matches a meal or
hotel requirement. Selection and source-held publication remain separate.
"""
from dataclasses import asdict
from hashlib import sha256
import json

from cj_place.gaode import _binding_json
from cj_place.gaode_v2 import TextSearch,Nearby

from .lio_poi2_tool import POI2Input
from .local_lio_provider_sources import POI2_REGISTRATION
from .local_lio_pipeline_calls import Call


PAGE_SIZE=3
MEAL_RADIUS_M=1500


def _call(query,target,origin,sources):
    raw=json.dumps(dict(run_id=origin.binding.run_id,target=target,query_type=type(query).__name__,
        query=asdict(query)),sort_keys=True,separators=(',',':'),default=_binding_json).encode()
    reference='poi-'+sha256(raw).hexdigest()[:24]
    return Call('gaode',POI2_REGISTRATION,POI2Input(query,reference,origin,sources,(target,)))


def sight_and_hotel_calls(stops,hotels,*,city,origin,sources):
    """One real bounded query per proposed sight or hotel, with exact targets."""
    result=[_call(TextSearch(stop.name_zh,city,PAGE_SIZE),stop.item_id,origin,sources)
            for stop in stops if stop.kind=='sight']
    result.extend(_call(TextSearch(names[0],city,PAGE_SIZE),'lodging-candidate-'+str(index),origin,sources)
                  for index,names in enumerate(hotels))
    return tuple(result)


def meal_calls(stops,*,city,centers,origin,sources):
    """Use unchanged observed anchors; absence/unsupported precision uses text.

    centers maps meal item IDs to code-selected provider Coordinates. It never
    implies a selected itinerary endpoint or a confirmed opening period. The
    query adapter refuses coordinates that would require rounding for around;
    that case selects one text request before dispatch, never a second attempt.
    """
    result=[]
    for stop in stops:
        if stop.kind!='meal':continue
        query=TextSearch(stop.name_zh,city,PAGE_SIZE)
        center=centers.get(stop.item_id)
        if center is not None:
            try:query=Nearby(stop.name_zh,city,center,MEAL_RADIUS_M,PAGE_SIZE)
            except ValueError as error:
                if str(error)!='around_requires_original_coordinate_precision':raise
        result.append(_call(query,stop.item_id,origin,sources))
    return tuple(result)
