"""Additive native4 city route data; no transport or source/write authority.

Official endpoint/field reference:
https://lbs.amap.com/api/webservice/guide/api/direction
Old RouteQuery and its parser retain their original walking/driving grammar.
"""
from dataclasses import asdict,dataclass
from decimal import Decimal
from hashlib import sha256
import json
from urllib.parse import urlencode

from .gaode import (PreparedRequest,prepare as prepare_legacy,
                    _binding_json,_decode,_quantity,_path_points,_separation_m,ROUTE_POINT_TOLERANCE_M)
from .gaode_v2 import ReceiptMismatch,_region
from .models import Endpoint,RouteQuery,Departure,Coordinate,aware,identifier

VERSION='CJ-PLACE-RICH-ROUTE.1'


@dataclass(frozen=True)
class CityRoute:
    origin:Endpoint
    destination:Endpoint
    mode:str
    city:str

    def __post_init__(self):
        if type(self.origin)is not Endpoint or type(self.destination)is not Endpoint:
            raise ValueError('observed_route_endpoints_required')
        if self.mode not in ('walking','transit','taxi'):raise ValueError('explicit_city_route_mode_required')
        _region(self.city)
        if self.mode=='transit'and self.city.isdecimal():raise ValueError('transit_requires_explicit_chinese_city')


@dataclass(frozen=True)
class Estimate:
    distance_m:Decimal
    duration_seconds:Decimal


def initial_mode(origin,destination):
    """Code policy over unchanged raw provider points, not a route estimate."""
    return 'walking'if _separation_m(origin.coordinate,destination.coordinate)<=1500 else'transit'


def _legacy(query):
    return RouteQuery(query.origin,query.destination,'driving'if query.mode=='taxi'else'walking',Departure('at_query_time',None))


def prepare(config,query,request_ref,started_at):
    aware(started_at);identifier(request_ref)
    if type(query)is not CityRoute:raise ValueError('explicit_rich_route_required')
    if query.mode!='transit':
        old=prepare_legacy(config,_legacy(query),request_ref,started_at,basic=True,coordinate_only=True)
        path,params=old.path,old.params
    else:
        path='/v3/direction/transit/integrated'
        params=tuple(sorted(dict(output='JSON',origin=query.origin.coordinate.raw,destination=query.destination.coordinate.raw,
            city=query.city,extensions='base',strategy='0',nightflag='0').items()))
    if len((config.origin+path+'?'+urlencode(params)).encode())>config.max_request_bytes:raise ValueError('request_too_large')
    raw=json.dumps(dict(version=VERSION,query=asdict(query),origin=config.origin,path=path,params=params,
        request_ref=request_ref,started_at=started_at,limits=asdict(config)),sort_keys=True,separators=(',',':'),default=_binding_json).encode()
    return PreparedRequest(query,config.origin,path,params,request_ref,started_at,sha256(raw).hexdigest())


def _transit_estimate(query,row):
    """Sum explicit segment distances; route.distance is not transit distance.

    Use only a single unambiguous bus/metro line per segment. Railway and
    alternative-line/missing geometry data are unavailable, never zero-filled.
    """
    duration=_quantity(row['duration'],'s').value
    segments=row.get('segments')
    if not isinstance(segments,list)or not 1<=len(segments)<=64:raise ValueError('bounded_transit_segments_required')
    distance=Decimal(0);points=[];rides=0
    for segment in segments:
        if not isinstance(segment,dict)or segment.get('railway')not in (None,{},[]):raise ValueError('city_transit_only')
        walk=segment.get('walking')
        if walk not in (None,{},[]):
            distance+=_quantity(walk['distance'],'m').value
            steps=walk['steps']
            if not isinstance(steps,list)or not 1<=len(steps)<=128:raise ValueError('bounded_walking_steps_required')
            for step in steps:
                points.extend(Coordinate(point)for point in step['polyline'].split(';'))
        bus=segment.get('bus')
        if bus not in (None,{},[]):
            lines=bus.get('buslines')
            if not isinstance(lines,list)or len(lines)!=1:raise ValueError('unambiguous_transit_line_required')
            line=lines[0]
            distance+=_quantity(line['distance'],'m').value
            points.extend(Coordinate(point)for point in line['polyline'].split(';'))
            rides+=1
    if not rides or not points:raise ValueError('observed_city_transit_geometry_required')
    if (_separation_m(query.origin.coordinate,points[0])>ROUTE_POINT_TOLERANCE_M or
            _separation_m(query.destination.coordinate,points[-1])>ROUTE_POINT_TOLERANCE_M):
        raise ReceiptMismatch('transit_endpoint_geometry_differs')
    minimum=max(0.,.99*_separation_m(query.origin.coordinate,query.destination.coordinate)-2*ROUTE_POINT_TOLERANCE_M)
    if float(distance)<minimum:raise ReceiptMismatch('transit_distance_below_point_span')
    return Estimate(distance,duration)


def _road_estimate(query,value):
    route=value.get('route')
    if not isinstance(route,dict):raise ValueError('route_object_required')
    if (not Coordinate(route.get('origin')).same_position(query.origin.coordinate)or
            not Coordinate(route.get('destination')).same_position(query.destination.coordinate)):
        raise ReceiptMismatch('route_original_endpoints_differ')
    paths=route.get('paths')
    if not isinstance(paths,list)or len(paths)>32 or value.get('count')!=str(len(paths)):
        raise ValueError('bounded_route_options_required')
    for path in paths:
        try:
            points=_path_points(path)
            if points is None:continue
            if (_separation_m(query.origin.coordinate,points[0])>ROUTE_POINT_TOLERANCE_M or
                    _separation_m(query.destination.coordinate,points[1])>ROUTE_POINT_TOLERANCE_M):
                raise ReceiptMismatch('route_endpoint_geometry_differs')
            distance=_quantity(path['distance'],'m').value
            minimum=max(0.,.99*_separation_m(query.origin.coordinate,query.destination.coordinate)-2*ROUTE_POINT_TOLERANCE_M)
            if float(distance)<minimum:raise ReceiptMismatch('route_distance_below_point_span')
            return Estimate(distance,_quantity(path['duration'],'s').value)
        except ReceiptMismatch:raise
        except(KeyError,TypeError,ValueError):continue
    return None


def parse(config,request,response,now):
    aware(now);aware(response.received_at)
    if (response.binding_digest!=request.binding_digest or response.origin!=request.origin or response.path!=request.path
            or response.received_at<request.started_at or response.received_at>now
            or(now-response.received_at).total_seconds()>config.max_age_seconds
            or len(response.body)>config.max_response_bytes):
        raise ReceiptMismatch('bounded_same_request_route_receipt_required')
    query=request.query
    if response.http_status!=200:return None
    value=_decode(response.body)
    if value.get('status')!='1'or value.get('infocode')!='10000':return None
    # Keep the new original digest intact. The legacy parser recomputes its
    # own v3 digest; relabeling a new receipt to satisfy it would erase provenance.
    if query.mode!='transit':return _road_estimate(query,value)
    route=value.get('route')
    if not isinstance(route,dict):raise ValueError('route_object_required')
    if (not Coordinate(route['origin']).same_position(query.origin.coordinate)or
            not Coordinate(route['destination']).same_position(query.destination.coordinate)):
        raise ReceiptMismatch('route_original_endpoints_differ')
    options=route.get('transits')
    if not isinstance(options,list)or len(options)>32 or value.get('count')!=str(len(options)):
        raise ValueError('bounded_transit_options_required')
    for option in options:
        try:return _transit_estimate(query,option)
        except ReceiptMismatch:raise
        except (KeyError,TypeError,ValueError):continue
    return None
