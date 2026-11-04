"""Narrow live data producers; the formal host owns admission and Meter dispatch.

No caller URL, auto redirect, credentials in results, applicability inference or
write authority. The frozen synthetic FACT-result.1 is not widened or relabeled.
"""
import asyncio
from datetime import datetime,timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import socket
import ssl
from urllib.parse import urlsplit

import certifi
import httpx

from .acquisition import PinnedTarget
from .https_transport import PinnedHTTPSTransport
from .policy import FactFailure,SourcePolicy,public_addresses
from cj_strict_json import reject_duplicates

NOTICE_URL='https://en.nia.gov.cn/'
WEATHER_URL='https://restapi.amap.com/v3/weather/weatherInfo'
PAGE_POLICY=SourcePolicy(('https://en.nia.gov.cn',),262144,1024,0,20,24,16384)


def tls():
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=certifi.where())
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(['http/1.1'])
    return context


class _Excerpts(HTMLParser):
    def __init__(self,raw):
        super().__init__(convert_charrefs=False)
        self.raw=raw;self.hidden=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.hidden:self.hidden-=1
    def handle_data(self,value):
        text=value.strip()
        if not self.hidden and len(text)>=20 and len(self.parts)<12:
            start=self.raw.find(text)
            if start>=0:self.parts.append(dict(text=text[:512],start=start,end=start+len(text[:512])))


async def public_page(*,guard):
    loop=asyncio.get_running_loop();deadline=loop.time()+PAGE_POLICY.timeout_seconds
    host=urlsplit(NOTICE_URL).hostname
    async with asyncio.timeout_at(deadline):
        records=await loop.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        addresses=public_addresses(tuple(dict.fromkeys(row[4][0] for row in records)))
        transport=PinnedHTTPSTransport(PAGE_POLICY,tls_context=tls(),max_header_bytes=16384,
            max_wire_bytes=524288,max_reads=512,allow_html=True)
        if guard() is not True:raise FactFailure('original_page_authority_invalid')
        response=await transport(PinnedTarget(NOTICE_URL,host,addresses,PAGE_POLICY.max_bytes,deadline))
        try:
            if response.status!=200:raise FactFailure('public_page_status_unavailable')
            body=bytearray()
            async for chunk in response.body:body.extend(chunk)
        finally:await response.close()
    raw=bytes(body);text=raw.decode('utf8',errors='strict')
    parser=_Excerpts(text);parser.feed(text)
    if not parser.parts:raise FactFailure('public_page_excerpt_unavailable')
    return dict(source_url=NOTICE_URL,retrieved_at=datetime.now(timezone.utc).isoformat(),
        original_sha256=sha256(raw).hexdigest(),original_bytes=len(raw),excerpts=parser.parts,
        status='unknown',reason='source_excerpts_only_dates_region_and_eligibility_not_verified')


def weather(query,key,*,guard,transport=None):
    if query.fact_key!='weather' or query.region not in ('beijing','110000','北京'):
        raise FactFailure('M4_beijing_weather_only')
    if dict(query.conditions).get('calendar_timezone','Asia/Shanghai')!='Asia/Shanghai':
        raise FactFailure('weather_calendar_timezone_unavailable')
    options=dict(timeout=20,follow_redirects=False,trust_env=False)
    if transport is None:options['verify']=tls()
    else:options['transport']=transport
    with httpx.Client(**options) as client:
        if guard() is not True:raise FactFailure('original_weather_authority_invalid')
        with client.stream('GET',WEATHER_URL,params=dict(key=key,city='110000',extensions='all',output='JSON'),
                           headers={'Accept-Encoding':'identity'}) as response:
            if response.status_code!=200:raise FactFailure('weather_http_response_unavailable')
            raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>65536:raise FactFailure('weather_response_size_limit')
    raw=bytes(raw)
    if key.encode() in raw:raise FactFailure('weather_secret_echo_rejected')
    value=json.loads(raw.decode('utf8'),object_pairs_hook=reject_duplicates(FactFailure,'weather_duplicate_field'))
    if key in json.dumps(value,ensure_ascii=False):raise FactFailure('weather_secret_echo_rejected')
    if value.get('status')!='1' or value.get('infocode')!='10000' or value.get('count')!='1':
        raise FactFailure('weather_provider_result_unavailable')
    forecasts=value.get('forecasts')
    if type(forecasts) is not list or len(forecasts)!=1 or forecasts[0].get('adcode')!='110000':
        raise FactFailure('weather_region_mismatch')
    forecast=forecasts[0];casts=forecast.get('casts')
    if type(casts) is not list or not 1<=len(casts)<=4:raise FactFailure('weather_forecast_invalid')
    from datetime import date
    observed=[]
    for day in casts:
        if type(day) is not dict or type(day.get('date')) is not str:raise FactFailure('weather_forecast_invalid')
        d=date.fromisoformat(day['date'])
        if query.dates.start<=d<=query.dates.end:observed.append(day)
    return dict(source_url=WEATHER_URL,retrieved_at=datetime.now(timezone.utc).isoformat(),
        original_sha256=sha256(raw).hexdigest(),provider_reporttime=forecast.get('reporttime','UNKNOWN'),
        region_adcode='110000',calendar_timezone='Asia/Shanghai',forecasts=observed,
        status='observed' if observed else 'unknown',reason='provider_forecast_not_future_guarantee',actual_cost_cny='UNKNOWN')
