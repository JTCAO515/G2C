"""Offline recorded-shape PLACE transport for L1; all returned facts are synthetic."""
import asyncio
from datetime import datetime, timezone

from cj_place import (ORIGIN, Config, Coordinate, Departure, Endpoint, Response, RouteQuery, Search)
from cj_place.synthetic import run_synthetic
from cj_trip.domain import packed
from cj_draft.provenance import SourceObservationBatch


def source_observations(binding):
    config = Config(ORIGIN, 4096, 65536, 3, 60)
    search = Search('合成公园', '合成城市', 1, 20)
    route = RouteQuery(Endpoint('SYNTH_A', Coordinate('116.1,39.1'), 'entrance'),
                       Endpoint('SYNTH_B', Coordinate('116.2,39.2'), 'poi_center'),
                       'walking', Departure('at_query_time', None))
    async def transport(request):
        if isinstance(request.query, Search):
            body = {'status': '1', 'info': 'OK', 'infocode': '10000', 'count': '1',
                    'pois': [{'id': 'SYNTH_A', 'name': '合成公园', 'address': '合成路', 'location': '116.1,39.1'}]}
        else:
            body = {'status': '1', 'info': 'OK', 'infocode': '10000', 'count': '1',
                    'route': {'origin': '116.1,39.1', 'destination': '116.2,39.2',
                              'paths': [{'distance': '123.50', 'duration': '60'}]}}
        return Response(request.binding_digest, request.origin, request.path, 200, packed(body), datetime.now(timezone.utc))
    async def read():
        return tuple([await run_synthetic(config, query, request_ref=binding.run_id + suffix, transport=transport)
                      for query, suffix in ((search, '-search'), (route, '-route'))])
    return SourceObservationBatch(binding, asyncio.run(read()))
