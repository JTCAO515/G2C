from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
import unittest

from cj_place.gaode import Config,Response
from cj_place.gaode_v2 import ReceiptMismatch
from cj_place.models import Coordinate,Endpoint,RouteQuery,Departure
from cj_place.rich_routes import CityRoute,prepare,parse,initial_mode

NOW=datetime(2026,11,14,tzinfo=timezone.utc)
CONFIG=Config('https://restapi.amap.com',8192,65536,20,60)
A=Endpoint('SYN_A',Coordinate('116.4,39.9'),'entrance')
B=Endpoint('SYN_B',Coordinate('116.42,39.9'),'poi_center')


def transit():
    return dict(status='1',infocode='10000',count='1',route=dict(origin=A.coordinate.raw,destination=B.coordinate.raw,
        distance='999999',transits=[dict(duration='900',segments=[dict(railway={},
            walking=dict(distance='600',steps=[dict(polyline='116.4,39.9;116.407,39.9')]),
            bus=dict(buslines=[dict(distance='1400',polyline='116.407,39.9;116.42,39.9')]))])]))


def reply(request,value):
    return Response(request.binding_digest,request.origin,request.path,200,json.dumps(value).encode(),NOW)


class RichRoutes(unittest.TestCase):
    def test_mode_policy_and_additive_transit_query_leave_old_route_grammar_closed(self):
        self.assertEqual(initial_mode(A,B),'transit')
        near=replace(B,coordinate=Coordinate('116.401,39.9'))
        self.assertEqual(initial_mode(A,near),'walking')
        with self.assertRaises(ValueError):RouteQuery(A,B,'transit',Departure('at_query_time',None))
        request=prepare(CONFIG,CityRoute(A,B,'transit','北京'),'route-1',NOW)
        self.assertEqual(request.path,'/v3/direction/transit/integrated')
        params=dict(request.params)
        self.assertEqual(params['city'],'北京')
        self.assertNotIn('date',params);self.assertNotIn('time',params)
        self.assertNotIn('key',params);self.assertNotIn('cityd',params)
        self.assertEqual(params['extensions'],'base')
        with self.assertRaises(ValueError):CityRoute(A,B,'transit','110000')

    def test_transit_uses_observed_segment_distances_not_top_level_walking_distance(self):
        request=prepare(CONFIG,CityRoute(A,B,'transit','北京'),'route-1',NOW)
        result=parse(CONFIG,request,reply(request,transit()),NOW)
        self.assertEqual(result.distance_m,Decimal('2000'))
        self.assertEqual(result.duration_seconds,Decimal('900'))

    def test_missing_or_ambiguous_transit_and_cross_city_railway_do_not_produce_estimates(self):
        request=prepare(CONFIG,CityRoute(A,B,'transit','北京'),'route-1',NOW)
        for mutation in (lambda v:v['route']['transits'][0]['segments'][0].update(railway={'id':'rail'}),
                         lambda v:v['route']['transits'][0]['segments'][0]['bus']['buslines'].append(
                             deepcopy(v['route']['transits'][0]['segments'][0]['bus']['buslines'][0])),
                         lambda v:v['route']['transits'][0]['segments'][0]['walking'].pop('distance'),
                         lambda v:v['route']['transits'][0].update(duration=[])):
            value=transit();mutation(value)
            self.assertIsNone(parse(CONFIG,request,reply(request,value),NOW))

    def test_original_binding_geometry_and_time_mismatches_fail_closed(self):
        request=prepare(CONFIG,CityRoute(A,B,'transit','北京'),'route-1',NOW)
        response=reply(request,transit())
        for invalid in (replace(response,binding_digest='0'*64),replace(response,path='/other'),
                        replace(response,received_at=NOW-timedelta(seconds=1)),
                        replace(response,body=b'x'*65537)):
            with self.assertRaises(ReceiptMismatch):parse(CONFIG,request,invalid,NOW)
        for mutation in (lambda v:v['route'].update(origin='117,40'),
                         lambda v:v['route']['transits'][0]['segments'][0]['bus']['buslines'][0].update(polyline='117,40;118,40')):
            value=transit();mutation(value)
            with self.assertRaises(ReceiptMismatch):parse(CONFIG,request,reply(request,value),NOW)

    def test_walking_and_taxi_keep_basic_requests_and_new_original_digest(self):
        for mode,path in (('walking','walking'),('taxi','driving')):
            request=prepare(CONFIG,CityRoute(A,B,mode,'北京'),'route-1',NOW)
            self.assertEqual(request.path,'/v3/direction/'+path)
            self.assertEqual(dict(request.params)['origin'],A.coordinate.raw)
            value=dict(status='1',infocode='10000',count='1',route=dict(origin=A.coordinate.raw,destination=B.coordinate.raw,
                paths=[dict(distance='2000',duration='900',steps=[dict(polyline=A.coordinate.raw+';'+B.coordinate.raw)])]))
            result=parse(CONFIG,request,reply(request,value),NOW)
            self.assertEqual(result.distance_m,Decimal('2000'))
            self.assertEqual(result.duration_seconds,Decimal('900'))


if __name__=='__main__':unittest.main()
