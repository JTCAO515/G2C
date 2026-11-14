"""Bounded POI2 query/response adapter. No credential, network or write grant.

Provider field reference: https://lbs.amap.com/api/webservice/guide/api/newpoisearch
The old v3 adapter and PLACE contract remain separate.
"""
from dataclasses import asdict,dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from urllib.parse import urlencode

from .gaode import Config,PreparedRequest,Response,_binding_json,_decode,_observed
from .models import Coordinate,FieldState,Observed,aware,identifier,text_value

VERSION='CJ-PLACE-POI2.1'


class ReceiptMismatch(ValueError):
    """No proof this is the complete bounded receipt of the original query."""


def _keyword(value):
    text_value(value,320)
    if len(value)>80 or '|'in value:raise ValueError('one_bounded_keyword_required')


def _region(value):
    text_value(value,128)
    if not (re.fullmatch('[0-9]{6}',value)or re.fullmatch(r'[\u3400-\u9fff·]{1,40}',value)):
        raise ValueError('explicit_chinese_city_or_adcode_required')


def _size(value):
    if type(value)is not int or not 1<=value<=25:raise ValueError('poi2_page_size')


@dataclass(frozen=True)
class TextSearch:
    keyword:str
    region:str
    page_size:int

    def __post_init__(self):
        _keyword(self.keyword);_region(self.region);_size(self.page_size)


@dataclass(frozen=True)
class Nearby:
    keyword:str
    region:str
    center:Coordinate
    radius_m:int
    page_size:int

    def __post_init__(self):
        _keyword(self.keyword);_region(self.region);_size(self.page_size)
        if type(self.radius_m)is not int or not 1<=self.radius_m<=50000:raise ValueError('poi2_radius')
        if any(len(part.split('.')[1])>6 for part in self.center.raw.split(',')if'.'in part):
            raise ValueError('around_requires_original_coordinate_precision')


@dataclass(frozen=True)
class POIDetail:
    provider_id:str
    def __post_init__(self):identifier(self.provider_id)


def prepare(config:Config,query:TextSearch|Nearby|POIDetail,request_ref:str,started_at:datetime):
    aware(started_at);identifier(request_ref)
    params=dict(output='json',show_fields='business,navi')
    if isinstance(query,TextSearch):
        path='/v5/place/text'
        params.update(keywords=query.keyword,region=query.region,city_limit='true',page_num='1',page_size=str(query.page_size))
    elif isinstance(query,Nearby):
        path='/v5/place/around'
        params.update(keywords=query.keyword,region=query.region,city_limit='true',location=query.center.raw,
            radius=str(query.radius_m),sortrule='distance',page_num='1',page_size=str(query.page_size))
    elif isinstance(query,POIDetail):path='/v5/place/detail';params.update(id=query.provider_id)
    else:raise ValueError('explicit_poi2_query_required')
    pairs=tuple(sorted(params.items()))
    if len((config.origin+path+'?'+urlencode(pairs)).encode())>config.max_request_bytes:raise ValueError('request_too_large')
    raw=json.dumps(dict(version=VERSION,query_type=type(query).__name__,query=asdict(query),
        origin=config.origin,path=path,params=pairs,request_ref=request_ref,started_at=started_at,limits=asdict(config)),
        ensure_ascii=False,sort_keys=True,separators=(',',':'),default=_binding_json).encode()
    return PreparedRequest(query,config.origin,path,pairs,request_ref,started_at,sha256(raw).hexdigest())


@dataclass(frozen=True)
class POI:
    provider_id:str
    name_zh:str
    center:Observed[Coordinate]
    entrance:Observed[Coordinate]
    exit:Observed[Coordinate]
    address:Observed[str]
    opening_today:Observed[str]
    opening_week:Observed[str]

    def place_projection(self,role):
        """Projection of an observed coordinate, never a guessed entrance."""
        coordinate={'poi_center':self.center,'entrance':self.entrance,'exit':self.exit}[role]
        if coordinate.state is not FieldState.PRESENT:return None
        point=coordinate.value
        return dict(amap_id=self.provider_id,name_zh=self.name_zh,coordinate=dict(raw=point.raw,
            longitude=str(point.longitude),latitude=str(point.latitude),crs='GCJ-02'),coordinate_role=role,
            address=self.address.value if self.address.state is FieldState.PRESENT else None)


@dataclass(frozen=True)
class POISnapshot:
    request_ref:str
    binding_digest:str
    raw_response_sha256:str
    observed_at:datetime
    pois:tuple[POI,...]


def _optional_object(value,key,field,parser):
    if key not in value:return Observed(FieldState.MISSING)
    block=value[key]
    if block is None:return Observed(FieldState.NULL)
    if block==[]:return Observed(FieldState.EMPTY_ARRAY)
    if not isinstance(block,dict):return Observed(FieldState.INVALID)
    return _observed(block,field,parser)


def _in_region(poi,region):
    if re.fullmatch('[0-9]{6}',region):
        actual=poi.get('adcode')
        if not isinstance(actual,str)or re.fullmatch('[0-9]{6}',actual)is None:return False
        width=2 if region.endswith('0000')else 4 if region.endswith('00')else 6
        return actual[:width]==region[:width]
    actual=poi.get('cityname')
    return isinstance(actual,str)and actual.removesuffix('市')==region.removesuffix('市')


def parse(config:Config,request:PreparedRequest,response:Response,now:datetime):
    aware(now);aware(response.received_at)
    if (response.binding_digest!=request.binding_digest or response.origin!=request.origin or
            response.path!=request.path or
            response.received_at<request.started_at or response.received_at>now or
            (now-response.received_at).total_seconds()>config.max_age_seconds or
            len(response.body)>config.max_response_bytes):
        raise ReceiptMismatch('bounded_same_request_poi2_receipt_required')
    if response.http_status!=200:raise ValueError('poi2_http_failure')
    if not isinstance(request.query,(TextSearch,Nearby,POIDetail)):
        raise ValueError('explicit_poi2_request_required')
    value=_decode(response.body)
    if value.get('status')!='1'or value.get('infocode')!='10000':raise ValueError('poi2_provider_rejected')
    rows=value.get('pois');maximum=1 if isinstance(request.query,POIDetail)else request.query.page_size
    if not isinstance(rows,list)or len(rows)>maximum:raise ValueError('bounded_poi2_records_required')
    count=value.get('count')
    if not isinstance(count,str)or re.fullmatch('[0-9]+',count)is None or int(count)!=len(rows):
        raise ValueError('poi2_count_differs')
    pois=[];ids=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('poi2_record_required')
        pid=identifier(row.get('id'));name=text_value(row.get('name'),500)
        if pid in ids:raise ValueError('duplicate_poi2_identity')
        ids.add(pid)
        if isinstance(request.query,POIDetail):
            if pid!=request.query.provider_id:raise ValueError('poi2_detail_identity_differs')
        elif not _in_region(row,request.query.region):raise ValueError('poi2_outside_requested_region')
        pois.append(POI(pid,name,_observed(row,'location',Coordinate),
            _optional_object(row,'navi','entr_location',Coordinate),_optional_object(row,'navi','exit_location',Coordinate),
            _observed(row,'address',text_value),_optional_object(row,'business','opentime_today',text_value),
            _optional_object(row,'business','opentime_week',text_value)))
    return POISnapshot(request.request_ref,request.binding_digest,sha256(response.body).hexdigest(),response.received_at,tuple(pois))
