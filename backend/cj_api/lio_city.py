"""Nationwide administrative destination resolution from original Amap data."""
from dataclasses import asdict,dataclass
from hashlib import sha256
import json
import re
import unicodedata

import asyncio
import ssl
from urllib.parse import urlencode
from cj_fact.live_source import tls
from cj_place.https_transport import _read_response,_WireFailure
from pypinyin import lazy_pinyin
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import canonical
from cj_usage.metered_exit import BudgetUnknown

VERSION='LIO-city-resolution.1'
ENDPOINT='https://restapi.amap.com/v3/config/district'
PARAMETERS=dict(keywords='100000',subdistrict='3',extensions='base',output='JSON')
MAX_CATALOG_BYTES=2*1024*1024


@dataclass(frozen=True)
class CityReference:
    adcode:str
    name:str
    province:str
    parent_city:str|None
    level:str
    timezone:str


def _normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())


def _base(name,level):
    suffixes={'province':('壮族自治区','回族自治区','维吾尔自治区','自治区','特别行政区','省','市'),
              'city':('自治州','地区','盟','市'), 'district':('林区','县','区','市')}
    for suffix in suffixes[level]:
        if name.endswith(suffix) and len(name)>len(suffix):return name[:-len(suffix)]
    return name


def forms(name,level):
    values=(name,_base(name,level))
    return {_normalize(v) for v in values}|{_normalize(''.join(lazy_pinyin(v))) for v in values}


def catalog(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_CATALOG_BYTES:raise ValueError('bounded city catalog required')
    value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate administrative field'))
    if (type(value) is not dict or value.get('status')!='1' or value.get('infocode')!='10000'
            or type(value.get('districts')) is not list or not value['districts']):
        raise ValueError('successful administrative catalog required')
    candidates={};visited=0
    def visit(node,province=None,city=None,depth=0):
        nonlocal visited
        visited+=1
        if visited>6000 or depth>4 or type(node) is not dict:raise ValueError('administrative catalog bound exceeded')
        name,adcode,level=node.get('name'),node.get('adcode'),node.get('level')
        children=node.get('districts')
        if (type(name) is not str or not name or len(name.encode())>256 or type(adcode) is not str
                or re.fullmatch('[0-9]{6}',adcode) is None or type(children) is not list
                or level not in ('country','province','city','district','street')):
            raise ValueError('original administrative record unavailable')
        if level=='province':province=name
        if level=='city':city=name
        if level in ('province','city','district'):
            if province is None:raise ValueError('administrative province missing')
            zone={'81':'Asia/Hong_Kong','82':'Asia/Macau','71':'Asia/Taipei'}.get(adcode[:2],'Asia/Shanghai')
            candidate=CityReference(adcode,name,province,city,level,zone)
            previous=candidates.get(adcode)
            if previous is not None and previous!=candidate:raise ValueError('administrative code has conflicting records')
            candidates[adcode]=candidate
        for child in children:visit(child,province,city,depth+1)
    for root in value['districts']:visit(root)
    # A municipality may be represented as province and an identical-name city.
    # These are one destination; preserve the provider's broader administrative code.
    equivalent={c.adcode for c in candidates.values() if c.level=='city' and any(
        p.level=='province' and p.name==c.name==c.province and p.adcode[:2]==c.adcode[:2]
        for p in candidates.values())}
    return tuple(c for code,c in sorted(candidates.items()) if code not in equivalent)


def resolve(raw,name,province=None,normalized_name=None):
    if type(name) is not str or not name.strip() or len(name.encode())>256:
        raise ValueError('explicit destination mention required')
    if province is not None and (type(province) is not str or not province.strip() or len(province.encode())>256):
        raise ValueError('bounded province hint required')
    if normalized_name is not None and (type(normalized_name) is not str or not normalized_name.strip()
                                         or len(normalized_name.encode())>256):
        raise ValueError('bounded proposed administrative name required')
    candidates=catalog(raw);key=_normalize(name)
    exact=[c for c in candidates if _normalize(c.name)==key]
    matches=exact or [c for c in candidates if key in forms(c.name,c.level)]
    translated=False
    if not matches and normalized_name is not None:
        normalized=_normalize(normalized_name)
        matches=[c for c in candidates if normalized in forms(c.name,c.level)]
        translated=bool(matches)
    province_unconfirmed=False
    if province is not None:
        hint=_normalize(province)
        filtered=[c for c in matches if hint in forms(c.province,'province')]
        if filtered:matches=filtered
        elif matches:province_unconfirmed=True
    status='not_found' if not matches else 'ambiguous' if len(matches)>1 else 'confirmation_required' if translated or province_unconfirmed else 'resolved'
    if status=='resolved' and matches[0].level=='province' and matches[0].adcode not in {
            '110000','120000','310000','500000','810000','820000'}:
        status='needs_city'
    return dict(version=VERSION,status=status,requested_name=name,
                candidates=[asdict(c) for c in matches],
                source=dict(name='Amap Administrative Districts',endpoint=ENDPOINT,
                            parameters=PARAMETERS,raw_response_sha256=sha256(raw).hexdigest()))


async def _catalog_exchange(key,guard):
    writer=None
    try:
        async with asyncio.timeout(20):
            reader,writer=await asyncio.open_connection('restapi.amap.com',443,ssl=tls(),
                server_hostname='restapi.amap.com',limit=16384)
            if guard() is not True:raise BudgetUnknown('original city lookup authority unavailable')
            target='/v3/config/district?'+urlencode({**PARAMETERS,'key':key})
            # Reuse the established narrow Amap reader. No URL logger, proxy,
            # cookie, redirect, TLS key log, retry or ambient HTTP hook.
            writer.write(('GET '+target+' HTTP/1.1\r\nHost: restapi.amap.com\r\nAccept: application/json\r\n'
                          'Accept-Encoding: identity\r\nConnection: close\r\n\r\n').encode('ascii'))
            await writer.drain()
            status,raw=await _read_response(reader,MAX_CATALOG_BYTES)
            if status!=200:raise BudgetUnknown('original city lookup HTTP outcome unavailable')
            return raw
    except (TimeoutError,OSError,ssl.SSLError,_WireFailure):
        raise BudgetUnknown('original city lookup transport unknown') from None
    finally:
        if writer is not None:writer.transport.abort()


def fetch_catalog(key,guard):
    # Exactly one HTTP exchange after the original registered INTENT.
    if guard() is not True:raise BudgetUnknown('original city lookup authority unavailable')
    return asyncio.run(_catalog_exchange(key,guard))
