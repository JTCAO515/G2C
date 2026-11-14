"""POI2 fixed-preparation dispatch controls. All socket reads are fixtures.

The shared transport's real TLS/cancellation/framing controls remain in the old
https_transport_checks suite. No real Gaode request occurs here.
"""
import asyncio
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch

from cj_place.gaode import Config
from cj_place.gaode_v2 import TextSearch,Nearby,POIDetail,prepare,parse
from cj_place.models import Coordinate
from cj_place.https_transport import ProviderCredentials,fetch_candidate,fetch_poi2_candidate
from cj_place import https_transport as transport

CONFIG=Config('https://restapi.amap.com',4096,4096,2,60)
SYNTHETIC_KEY='fixture_poi2_key_0123456789'


class Writer:
    def __init__(self):
        self.writes=[];self.closed=False;self.aborted=False
        self.transport=SimpleNamespace(abort=self.abort)
    def write(self,body):self.writes.append(body)
    async def drain(self):pass
    def close(self):self.closed=True
    async def wait_closed(self):pass
    def abort(self):self.aborted=True


class POI2TransportTests(unittest.IsolatedAsyncioTestCase):
    def credentials(self):return ProviderCredentials(SYNTHETIC_KEY,datetime.now(timezone.utc)+timedelta(minutes=1))
    def request(self,query):return prepare(CONFIG,query,'fixture-registered-operation',datetime.now(timezone.utc))

    def reader(self,body):
        reader=asyncio.StreamReader()
        reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
        reader.feed_eof();return reader

    async def test_new_query_paths_send_once_and_preserve_request_binding(self):
        for query in (TextSearch('博物馆','北京',2),Nearby('餐馆','北京',Coordinate('116.4,39.9'),1500,2),POIDetail('B000SYNTH1')):
            request=self.request(query)
            body=json.dumps(dict(status='1',infocode='10000',count='1',pois=[dict(id='B000SYNTH1',name='合成地点',
                cityname='北京市',adcode='110101',location='116.4,39.9')]),ensure_ascii=False).encode()
            writer=Writer();dial=AsyncMock(return_value=(self.reader(body),writer));guards=[]
            with patch.object(transport,'_connect',dial):
                result=await fetch_poi2_candidate(CONFIG,request,self.credentials(),before_send=lambda:guards.append(True)or True)
            self.assertEqual(result.state,'received');self.assertEqual(dial.await_count,1)
            self.assertEqual(len(writer.writes),1);self.assertTrue(writer.closed)
            self.assertEqual(guards,[True])
            self.assertTrue(writer.writes[0].startswith(('GET '+request.path+'?').encode()))
            self.assertEqual(parse(CONFIG,request,result.response,datetime.now(timezone.utc)).pois[0].provider_id,'B000SYNTH1')

    async def test_missing_guard_tampered_path_or_old_entry_refuses_before_any_dial(self):
        request=self.request(TextSearch('博物馆','北京',2));dial=AsyncMock()
        with patch.object(transport,'_connect',dial):
            self.assertEqual((await fetch_poi2_candidate(CONFIG,request,self.credentials(),before_send=None)).state,'rejected')
            self.assertEqual((await fetch_poi2_candidate(CONFIG,replace(request,path='/v3/place/text'),self.credentials(),before_send=lambda:True)).state,'rejected')
            self.assertEqual((await fetch_candidate(CONFIG,request,self.credentials())).state,'rejected')
        self.assertEqual(dial.await_count,0)

    async def test_transport_failure_or_secret_echo_stays_unknown_without_a_second_send(self):
        request=self.request(TextSearch('博物馆','北京',2))
        dial=AsyncMock(side_effect=OSError('synthetic connection failure'))
        with patch.object(transport,'_connect',dial):
            result=await fetch_poi2_candidate(CONFIG,request,self.credentials(),before_send=lambda:True)
        self.assertEqual(result.state,'unknown');self.assertIsNone(result.response);self.assertEqual(dial.await_count,1)
        writer=Writer();body=json.dumps(dict(status='1',echo=SYNTHETIC_KEY)).encode()
        dial=AsyncMock(return_value=(self.reader(body),writer))
        with patch.object(transport,'_connect',dial):
            result=await fetch_poi2_candidate(CONFIG,request,self.credentials(),before_send=lambda:True)
        self.assertEqual(result.state,'unknown');self.assertIsNone(result.response)
        self.assertEqual(len(writer.writes),1);self.assertTrue(writer.closed);self.assertEqual(dial.await_count,1)


if __name__=='__main__':unittest.main()
