"""Maintainer summaries from the explicit visitor catalog, never official excerpts.

No network, credentials, write authority, date inference or FACT@1.0 behavior.
The trusted host supplies the catalog directory and current server instant.
"""
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from cj_strict_json import compact,reject_duplicates
from .model import aware
from .policy import FactFailure,canonical_url

QUERY_VERSION='FACT-query.2'
RESULT_VERSION='FACT-result.2'
TOPICS=frozenset({'payment','passport_booking','transport','internet','emergency'})
CITIES=frozenset({'beijing','chengdu','xian','shanghai','hangzhou','chongqing','shenzhen'})
# JT-approved exact-host inventory: #843/6818584957. No subdomain expansion.
SOURCE_HOSTS=frozenset({'english.www.gov.cn','www.beijing.gov.cn','www.chengdu.gov.cn',
    'www.cq.gov.cn','www.hangzhou.gov.cn','www.mfa.gov.cn','www.miit.gov.cn','www.mot.gov.cn',
    'www.nia.gov.cn','www.nra.gov.cn','www.pbc.gov.cn','www.shanghai.gov.cn','www.sz.gov.cn','www.xa.gov.cn'})
ALIASES={alias.casefold():city for city,aliases in (
    ('beijing',('beijing','北京','北京市','110000')),
    ('chengdu',('chengdu','成都','成都市','510100')),
    ('xian',('xian',"xi'an",'西安','西安市','610100')),
    ('shanghai',('shanghai','上海','上海市','310000')),
    ('hangzhou',('hangzhou','杭州','杭州市','330100')),
    ('chongqing',('chongqing','重庆','重庆市','500000')),
    ('shenzhen',('shenzhen','深圳','深圳市','440300')),
) for alias in aliases}
FIELDS=frozenset({'id','topic','cities','text_zh','text_en','source_urls','checked_on','expires_on'})
CHINA=ZoneInfo('Asia/Shanghai')
MAX_CATALOGUE_BYTES=1048576
MAX_RESULT_BYTES=131072


def _text(value,limit):
    if type(value)is not str or not value.strip() or len(value)>limit:
        raise FactFailure('bounded_visitor_text_required')
    try:value.encode('utf8')
    except UnicodeError:raise FactFailure('invalid_visitor_text')from None
    return value


def _constant(_):raise FactFailure('nonfinite_visitor_json')


def _load(raw,limit):
    if type(raw)is not bytes or not 0<len(raw)<=limit:raise FactFailure('bounded_visitor_json_required')
    try:
        return json.loads(raw.decode('utf8'),object_pairs_hook=reject_duplicates(FactFailure,'duplicate_visitor_key'),parse_constant=_constant)
    except (ValueError,UnicodeError,RecursionError):raise FactFailure('invalid_visitor_json')from None


def _day(value):
    if type(value)is not str or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value)is None:
        raise FactFailure('invalid_visitor_date')
    try:return date.fromisoformat(value)
    except ValueError:raise FactFailure('invalid_visitor_date')from None


@dataclass(frozen=True)
class Query:
    topic:str
    city:str


def decode_query(raw):
    value=_load(raw,1024)
    if type(value)is not dict or value.keys()!={'version','topic','city'} or value['version']!=QUERY_VERSION:
        raise FactFailure('invalid_visitor_query')
    if type(value['topic'])is not str or value['topic']not in TOPICS:raise FactFailure('invalid_visitor_topic')
    return Query(value['topic'],_text(value['city'],128))


@dataclass(frozen=True)
class Entry:
    entry_id:str
    topic:str
    cities:tuple[str,...]
    text_zh:str
    text_en:str
    source_urls:tuple[str,...]
    checked_on:date
    expires_on:date

    @classmethod
    def parse(cls,value,today):
        if type(value)is not dict or value.keys()!=FIELDS:raise FactFailure('invalid_visitor_entry')
        identifier=_text(value['id'],256)
        if re.fullmatch(r'visitor\.[a-z0-9][a-z0-9.-]*',identifier)is None:raise FactFailure('invalid_visitor_id')
        if type(value['topic'])is not str or value['topic']not in TOPICS:raise FactFailure('invalid_visitor_topic')
        lists={}
        for key,limit in (('cities',7),('source_urls',32)):
            items=value[key]
            if type(items)is not list or not 1<=len(items)<=limit:raise FactFailure('invalid_visitor_list')
            texts=tuple(_text(item,2048 if key=='source_urls' else 128)for item in items)
            if len(set(texts))!=len(texts):raise FactFailure('duplicate_visitor_value')
            lists[key]=texts
        if any(city not in CITIES for city in lists['cities']):raise FactFailure('invalid_visitor_city')
        for url in lists['source_urls']:
            canonical_url(url)
            if urlsplit(url).hostname not in SOURCE_HOSTS or urlsplit(url).path in ('','/'):
                raise FactFailure('unapproved_visitor_source')
        checked,expires=_day(value['checked_on']),_day(value['expires_on'])
        if checked>today or expires<=checked:raise FactFailure('invalid_visitor_review_range')
        return cls(identifier,value['topic'],lists['cities'],_text(value['text_zh'],4096),
                   _text(value['text_en'],4096),lists['source_urls'],checked,expires)

    def public_value(self):
        return dict(id=self.entry_id,topic=self.topic,cities=list(self.cities),text_zh=self.text_zh,text_en=self.text_en,
                    source_urls=list(self.source_urls),checked_on=self.checked_on.isoformat(),expires_on=self.expires_on.isoformat())


def lookup(directory:Path,query:Query,*,evaluated_at,request_ref):
    """One bounded public-file read; expired entries are omitted, malformed data fails."""
    aware(evaluated_at)
    reference=_text(request_ref,256)
    today=evaluated_at.astimezone(CHINA).date()
    try:
        paths=sorted(directory.glob('*.json'))
        if not paths:raise FactFailure('visitor_catalogue_unavailable')
        entries=[];ids=set();manifest=[];size=0
        for path in paths:
            if path.is_symlink() or not path.is_file():raise FactFailure('invalid_visitor_catalogue_file')
            with path.open('rb')as source:raw=source.read(MAX_CATALOGUE_BYTES+1)
            size+=len(raw)
            if size>MAX_CATALOGUE_BYTES:raise FactFailure('visitor_catalogue_too_large')
            values=_load(raw,MAX_CATALOGUE_BYTES)
            if type(values)is not list or not values:raise FactFailure('invalid_visitor_catalogue_file')
            manifest.append((path.name,sha256(raw).hexdigest()))
            for value in values:
                entry=Entry.parse(value,today)
                if entry.entry_id in ids:raise FactFailure('duplicate_visitor_id')
                ids.add(entry.entry_id);entries.append(entry)
    except OSError:raise FactFailure('visitor_catalogue_unavailable')from None
    city=ALIASES.get(query.city.casefold())
    matched=sorted((entry for entry in entries if entry.topic==query.topic and city in entry.cities
                    and today<entry.expires_on),key=lambda entry:entry.entry_id)
    result=dict(version=RESULT_VERSION,request_ref=reference,query=dict(version=QUERY_VERSION,topic=query.topic,city=query.city),
        data_origin='maintainer_summary',status='matched'if matched else'no_match',
        evaluated_at=evaluated_at.isoformat(timespec='microseconds'),
        catalogue_sha256=sha256(compact(manifest)).hexdigest(),entries=[entry.public_value()for entry in matched])
    raw=compact(result)
    if len(raw)>MAX_RESULT_BYTES:raise FactFailure('visitor_result_too_large')
    return raw
