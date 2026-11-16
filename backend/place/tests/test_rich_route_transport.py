"""Rich fixed-path transport registration, fixture sockets only."""
import asyncio
from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
import unittest
from unittest.mock import AsyncMock,patch

from cj_place.gaode import Config
from cj_place.gaode_v2 import TextSearch,prepare as prepare_poi2
from cj_place.models import Coordinate,Endpoint
from cj_place.rich_routes import CityRoute,prepare,parse
from cj_place.https_transport import ProviderCredentials
from cj_place import https_transport as transport
from test_poi2_transport import Writer

CONFIG=Config('https://restapi.amap.com',8192,65536,2,60)
A=Endpoint('SYN_A',Coordinate('116.4,39.9'),'entrance')
B=Endpoint('SYN_B',Coordinate('116.42,39.9'),'poi_center')


class RichRouteTransport(unittest.TestCase):
    def credentials(self):
        return ProviderCredentials('synthetic_route_key',datetime.now(timezone.utc)+timedelta(minutes=1))
    def request(self,mode='transit'):
        return prepare(CONFIG,CityRoute(A,B,mode,'北京'),'original-route',datetime.now(timezone.utc))

    def test_new_paths_send_once_then_receive_outside_the_original_frame(self):
        for mode in ('walking','transit','taxi'):
            held=ContextVar('actual-route-dispatch',default=False)
            request=self.request(mode);writer=Writer()
            if mode=='transit':
                route=dict(origin=A.coordinate.raw,destination=B.coordinate.raw,transits=[dict(duration='900',segments=[
                    dict(bus=dict(buslines=[dict(distance='2000',polyline=A.coordinate.raw+';'+B.coordinate.raw)]))])])
            else:route=dict(origin=A.coordinate.raw,destination=B.coordinate.raw,
                paths=[dict(distance='2000',duration='900',steps=[dict(polyline=A.coordinate.raw+';'+B.coordinate.raw)])])
            body=json.dumps(dict(status='1',infocode='10000',count='1',route=route)).encode()
            async def dial():
                reader=asyncio.StreamReader()
                reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
                reader.feed_eof()
                return reader,writer
            receive=transport._read_response
            phases=[]
            async def read(*args):
                self.assertFalse(held.get());phases.append('receive')
                return await receive(*args)
            def guard():phases.append('guard-held'if held.get()else'guard-released');return True
            with patch.object(transport,'_connect',AsyncMock(side_effect=dial)),patch.object(transport,'_read_response',read):
                stream=transport.route_candidate_stream(CONFIG,request,self.credentials(),before_send=guard)
                token=held.set(True)
                self.assertIs(next(stream),transport.ROUTE_REQUEST_SENT)
                self.assertEqual(phases,['guard-held']);self.assertEqual(len(writer.writes),1)
                held.reset(token)
                result,=stream
            self.assertEqual(result.state,'received');self.assertTrue(writer.closed)
            self.assertEqual(phases,['guard-held','guard-released','receive'])
            self.assertEqual(parse(CONFIG,request,result.response,datetime.now(timezone.utc)).distance_m,2000)

    def test_wrong_entry_missing_guard_and_tampered_path_never_dial(self):
        request=self.request();dial=AsyncMock()
        poi=prepare_poi2(CONFIG,TextSearch('博物馆','北京',1),'original-poi',datetime.now(timezone.utc))
        with patch.object(transport,'_connect',dial):
            for source in (
                transport.route_candidate_stream(CONFIG,request,self.credentials(),before_send=None),
                transport.route_candidate_stream(CONFIG,replace(request,path='/v5/place/text'),self.credentials(),before_send=lambda:True),
                transport.route_candidate_stream(CONFIG,poi,self.credentials(),before_send=lambda:True),
                transport.poi2_candidate_stream(CONFIG,request,self.credentials(),before_send=lambda:True)):
                result,=source;self.assertEqual(result.state,'rejected')
            self.assertEqual(asyncio.run(transport.fetch_candidate(CONFIG,request,self.credentials())).state,'rejected')
        dial.assert_not_called()

    def test_withdrawal_after_send_preserves_unknown_without_a_second_request(self):
        writer=Writer();allowed=True;receive=AsyncMock()
        dial=AsyncMock(return_value=(object(),writer))
        with patch.object(transport,'_connect',dial),patch.object(transport,'_read_response',receive):
            stream=transport.route_candidate_stream(CONFIG,self.request(),self.credentials(),before_send=lambda:allowed)
            self.assertIs(next(stream),transport.ROUTE_REQUEST_SENT)
            allowed=False
            result,=stream
        self.assertEqual(result.state,'unknown');self.assertIsNone(result.response)
        self.assertEqual(len(writer.writes),1);self.assertTrue(writer.closed)
        self.assertEqual(dial.await_count,1);receive.assert_not_called()


if __name__=='__main__':unittest.main()
