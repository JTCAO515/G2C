"""Narrow live data producers; the formal host owns admission and Meter dispatch.

No caller URL, auto redirect, credentials in results, applicability inference or
write authority. The frozen synthetic FACT-result.1 is not widened or relabeled.
"""
import asyncio
from datetime import datetime,timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import logging
import socket
import ssl
from urllib.parse import urlsplit
from urllib.parse import urlencode

import certifi

from .acquisition import PinnedTarget
from .https_transport import PinnedHTTPSTransport
from .policy import FactFailure,SourcePolicy,public_addresses
from cj_strict_json import reject_duplicates
from cj_place.https_transport import _read_response,_WireFailure

NOTICE_URL='https://en.nia.gov.cn/'
WEATHER_URL='https://restapi.amap.com/v3/weather/weatherInfo'
PAGE_POLICY=SourcePolicy(('https://en.nia.gov.cn',),262144,1024,0,20,24,16384)
PAGE_FAILURE_CODES=frozenset(('invalid_dns_answer','non_public_dns_answer',
    'original_page_authority_invalid','original_source_authority_invalid','timeout',
    'tls_certificate_invalid','https_exchange_failed','peer_not_pinned',
    'unsupported_tls_protocol','unsupported_http_response','header_limit',
    'duplicate_response_header','ambiguous_body_framing','unsupported_content_type',
    'encoded_body_rejected','body_limit','response_closed','wire_read_limit',
    'wire_byte_limit','chunk_limit','http_trailers_rejected','malformed_http_body',
    'https_body_failed','public_page_status_unavailable','public_page_excerpt_unavailable'))


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
    phase='dns';status='UNKNOWN';body=bytearray()
    try:
        async with asyncio.timeout_at(deadline):
            records=await loop.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            addresses=public_addresses(tuple(dict.fromkeys(row[4][0] for row in records)))
            phase='https_exchange'
            transport=PinnedHTTPSTransport(PAGE_POLICY,tls_context=tls(),max_header_bytes=16384,
                max_wire_bytes=524288,max_reads=512,allow_html=True,before_send=guard)
            if guard() is not True:raise FactFailure('original_page_authority_invalid')
            response=await transport(PinnedTarget(NOTICE_URL,host,addresses,PAGE_POLICY.max_bytes,deadline))
            try:
                phase='http_status';status=response.status
                if status!=200:raise FactFailure('public_page_status_unavailable')
                phase='body'
                async for chunk in response.body:body.extend(chunk)
            finally:await response.close()
        phase='utf8';raw=bytes(body);text=raw.decode('utf8',errors='strict')
        phase='excerpt';parser=_Excerpts(text);parser.feed(text)
        if not parser.parts:raise FactFailure('public_page_excerpt_unavailable')
    except (FactFailure,TimeoutError,OSError,UnicodeError,ValueError) as error:
        # Only fixed internal codes and counts. Never stringify an arbitrary
        # transport exception, URL, response header/body, address, or credential.
        reason=('timeout' if isinstance(error,TimeoutError) else
                'utf8_invalid' if isinstance(error,UnicodeError) else
                'transport_error' if isinstance(error,OSError) else 'other')
        if isinstance(error,FactFailure) and error.args and type(error.args[0]) is str:
            reason=error.args[0] if error.args[0] in PAGE_FAILURE_CODES else 'other'
        logging.getLogger('cj_provider.audit').warning(
            'M4_FACT_PAGE_UNKNOWN phase=%s reason=%s http_status=%s observed_body_bytes=%s',
            phase,reason,status,len(body))
        raise
    return dict(source_url=NOTICE_URL,retrieved_at=datetime.now(timezone.utc).isoformat(),
        original_sha256=sha256(raw).hexdigest(),original_bytes=len(raw),excerpts=parser.parts,
        status='unknown',reason='source_excerpts_only_dates_region_and_eligibility_not_verified')


async def _weather_exchange(key,guard):
    writer=None
    try:
        async with asyncio.timeout(20):
            reader,writer=await asyncio.open_connection('restapi.amap.com',443,ssl=tls(),server_hostname='restapi.amap.com',limit=16384)
            if guard() is not True:raise FactFailure('original_weather_authority_invalid')
            target='/v3/weather/weatherInfo?'+urlencode(dict(key=key,city='110000',extensions='all',output='JSON'))
            # Use the existing narrow wire reader, without HTTPX's URL logging.
            # This request has no cookie, proxy, redirect, retry or ambient hook.
            writer.write(('GET '+target+' HTTP/1.1\r\nHost: restapi.amap.com\r\nAccept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n').encode('ascii'))
            await writer.drain()
            status,raw=await _read_response(reader,65536)
            if status!=200:raise FactFailure('weather_http_response_unavailable')
            return raw
    except (TimeoutError,OSError,ssl.SSLError,_WireFailure):
        raise FactFailure('weather_transport_unknown') from None
    finally:
        if writer is not None:writer.transport.abort()


def weather(query,key,*,guard):
    if query.fact_key!='weather' or query.region not in ('beijing','110000','北京'):
        raise FactFailure('M4_beijing_weather_only')
    if dict(query.conditions).get('calendar_timezone','Asia/Shanghai')!='Asia/Shanghai':
        raise FactFailure('weather_calendar_timezone_unavailable')
    raw=asyncio.run(_weather_exchange(key,guard))
    if key.encode() in raw:raise FactFailure('weather_secret_echo_rejected')
    value=json.loads(raw.decode('utf8'),object_pairs_hook=reject_duplicates(FactFailure,'weather_duplicate_field'))
    if key in json.dumps(value,ensure_ascii=False):raise FactFailure('weather_secret_echo_rejected')
    if type(value) is not dict or value.get('status')!='1' or value.get('infocode')!='10000' or value.get('count')!='1':
        raise FactFailure('weather_provider_result_unavailable')
    forecasts=value.get('forecasts')
    if type(forecasts) is not list or len(forecasts)!=1 or type(forecasts[0]) is not dict or forecasts[0].get('adcode')!='110000':
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
