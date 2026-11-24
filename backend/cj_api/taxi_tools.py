"""Information-only taxi contracts. HK stays disabled until provider verification."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from time import sleep
import unicodedata
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from cj_strict_json import reject_duplicates

from .didi_mcp import DiDiTool
from .plugin_tools import PluginError, register_plugin
from .taxi_geography import gcj_to_wgs, in_mainland, wgs_to_gcj


VERSION = 'TAXI.1'
ESTIMATE = '/v1/tools/taxi/estimate'
LINK = '/v1/tools/taxi/link'
SEARCH = '/v1/tools/taxi/search'
DAILY_LIMIT = 50
REVERSE_COUNT = 'didi:maps_regeocode'
APP_LINK_HOST = 'v.didi.cn'
APP_LINK_PATH = '/XvYQEWe'
LINK_COORDINATES = {
    'slng': 'from_lng', 'slat': 'from_lat', 'dlng': 'to_lng', 'dlat': 'to_lat',
}
_LOGGER = logging.getLogger(__name__)


class DiDiEstimateExpired(PluginError):
    def __init__(self):
        super().__init__(502, 'supplier_unavailable')


class DiDiInformation:
    """Transport receives only fixed-tool calls. This adapter owns error mapping."""

    def __init__(self, transport, *, wait=sleep):
        self._transport = transport
        self._wait = wait

    def _send(self, selected, params):
        try:
            result = self._transport(selected, params)
        except TimeoutError:
            raise PluginError(504, 'supplier_timeout') from None
        except OSError:
            raise PluginError(502, 'supplier_unavailable') from None
        if type(result) is not dict:
            raise PluginError(502, 'supplier_unavailable')
        error = result.get('error')
        return result, error.get('code') if type(error) is dict else None

    def call(self, tool, params, *, retry=True, before_retry=None):
        selected = DiDiTool(tool)
        result, code = self._send(selected, params)
        if retry and (code == -32001 or (code == -32021 and selected is DiDiTool.ESTIMATE)):
            if code == -32001:
                self._wait(0.25)
            if before_retry is not None:
                before_retry()
            result, code = self._send(selected, params)
        if code == -32001:
            raise PluginError(429, 'rate_limited')
        if code == -32002:
            _LOGGER.warning('ALERT didi_key_rejected')
        if code == -32010:
            raise PluginError(400, 'invalid_request')
        if code == -32021:
            raise DiDiEstimateExpired()
        if 'error' in result or result.get('isError') is True:
            raise PluginError(502, 'supplier_unavailable')
        return result


class WireModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


INVISIBLE = frozenset({'Cc', 'Cf', 'Cs', 'Zl', 'Zp'})


def _visible(text):
    """Reject C0/DEL/C1 controls, bidi and other format characters, and surrogates."""
    return all(unicodedata.category(char) not in INVISIBLE for char in text)


class Point(WireModel):
    lat: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    lng: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    coordinate_system: Literal['WGS-84', 'GCJ-02']
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, name):
        if name is not None:
            if not name.strip() or not _visible(name):
                raise ValueError('invalid name')
        return name


class EstimateRequest(WireModel):
    version: Literal['TAXI.1']
    origin: Point
    destination: Point


class LinkRequest(EstimateRequest):
    vehicle_category: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')] | None = None


CITY_ALIASES = {'beijing': '北京市', 'shanghai': '上海市', 'chengdu': '成都市',
                'hong kong': '香港', 'hongkong': '香港', 'macau': '澳门', 'macao': '澳门',
                'taipei': '台北', 'taiwan': '台湾'}
CITY_NAME = re.compile(r'[\u3400-\u9fff]{2,24}')
# Outside the mainland service area: never suffixed with 市 and never sent to DiDi.
NON_MAINLAND = ('香港', '澳门', '澳門', '台湾', '台灣', '臺灣', '臺湾', '台北', '臺北', '新北', '台中', '臺中',
                '台南', '臺南', '高雄', '桃园', '桃園', '基隆', '新竹', '嘉义', '嘉義')


def _city(raw):
    city = raw.strip()
    city = CITY_ALIASES.get(city.lower(), city)
    if not CITY_NAME.fullmatch(city):
        raise ValueError('a city name is required')
    if city.startswith(NON_MAINLAND):
        return city
    return city if city.endswith(('市', '自治州', '地区', '盟')) else city + '市'


class SearchRequest(WireModel):
    version: Literal['TAXI.1']
    query: Annotated[str, Field(min_length=1, max_length=100)]
    city: Annotated[str, Field(min_length=1, max_length=50)]
    near: Point | None = None

    @field_validator('city')
    @classmethod
    def full_city(cls, value):
        return _city(value)

    @field_validator('query')
    @classmethod
    def visible_query(cls, value):
        query = value.strip()
        if not query or not _visible(query):
            raise ValueError('nonempty search keyword required')
        return query


COORDINATE_TEXT = re.compile(r'-?[0-9]{1,3}(?:\.[0-9]{1,15})?')


def _coordinate(value):
    # Real maps_textsearch returns JSON numbers; plain decimal text is accepted, anything else fails Point.
    return float(value) if type(value) is str and COORDINATE_TEXT.fullmatch(value) else value


def _row_city(value):
    try:
        return _city(value)
    except ValueError:
        return None


def _search_rows(result, city):
    try:
        rows = json.loads(result['content'][0]['text'],
                          object_pairs_hook=reject_duplicates(ValueError, 'duplicate POI field'))
        if type(rows) is not list or len(rows) > 100:
            raise ValueError('invalid POI list')
    except (IndexError, KeyError, TypeError, ValueError, RecursionError):
        raise PluginError(502, 'supplier_unavailable') from None

    items = []
    malformed = 0
    for row in rows:
        try:
            point = Point(lat=_coordinate(row['location']['lat']), lng=_coordinate(row['location']['lng']),
                          coordinate_system='GCJ-02', name=row['display_name'])
            row_city = _row_city(row['city']) if type(row['city']) is str else None
            address = row.get('address') or row.get('address_all')
        except (AttributeError, KeyError, TypeError, ValueError):
            malformed += 1
            continue
        if row_city != city or not in_mainland(*gcj_to_wgs(point.lng, point.lat)):
            continue
        if type(address) is not str or not address.strip() or len(address) > 240 or not _visible(address):
            address = None
        items.append(dict(name_zh=point.name, address_zh=address, city=city, lat=point.lat, lng=point.lng,
                          coordinate_system='GCJ-02'))
        if len(items) == 20:
            break
    if malformed and not items:
        raise PluginError(502, 'supplier_unavailable')
    return items


class Vehicle(WireModel):
    category: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    price_display: Annotated[str, Field(min_length=1, max_length=120)]
    currency: Literal['CNY'] = 'CNY'
    price_min_minor: Annotated[int, Field(ge=0)] | None = None
    price_max_minor: Annotated[int, Field(ge=0)] | None = None


class EstimateOutput(WireModel):
    vehicles: Annotated[list[Vehicle], Field(min_length=1, max_length=32)]
    distance_m: Annotated[int, Field(ge=0)] | None = None
    trace_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')] | None = None


def _public_link(raw, params):
    try:
        if type(raw) is not str or len(raw) > 512 or any(ord(char) <= 32 for char in raw):
            raise ValueError('invalid link')
        target = urlsplit(raw)
        if ((target.scheme, target.netloc, target.path) != ('https', APP_LINK_HOST, APP_LINK_PATH)
                or target.fragment):
            raise ValueError('invalid link target')
        pairs = parse_qsl(target.query, strict_parsing=True)
        query = dict(pairs)
        if (len(pairs) != len(LINK_COORDINATES) or query.keys() != LINK_COORDINATES.keys()
                or any(Decimal(query[key]) != Decimal(params[field]) for key, field in LINK_COORDINATES.items())):
            raise ValueError('invalid link coordinates')
    except (InvalidOperation, ValueError):
        raise PluginError(502, 'supplier_unavailable') from None
    return dict(url=raw, link_type='https')


def _gcj_strings(point):
    source = (point.lng, point.lat)
    if not 72 < point.lng < 136 or not 17 < point.lat < 55:
        raise PluginError(422, 'out_of_service_area')
    original_wgs = source if point.coordinate_system == 'WGS-84' else gcj_to_wgs(*source)
    if not in_mainland(*original_wgs):
        raise PluginError(422, 'out_of_service_area')
    lng, lat = wgs_to_gcj(*source) if point.coordinate_system == 'WGS-84' else source
    return f'{lng:.6f}', f'{lat:.6f}'


class TaxiService:
    def __init__(self, provider, *, clock=lambda: datetime.now(timezone.utc)):
        self.provider = provider
        self.clock = clock

    def _points(self, request):
        # Validate both before any DiDi call, including reverse geocoding.
        first_lng, first_lat = _gcj_strings(request.origin)
        last_lng, last_lat = _gcj_strings(request.destination)
        return dict(from_lat=first_lat, from_lng=first_lng, to_lat=last_lat, to_lng=last_lng)

    def search(self, request, reserve):
        if request.city.startswith(NON_MAINLAND):
            raise PluginError(422, 'out_of_service_area')
        params = dict(keywords=request.query, city=request.city)
        if request.near is not None:
            lng, lat = _gcj_strings(request.near)
            params['location'] = f'{lng},{lat}'
        reserve('didi:maps_textsearch', DAILY_LIMIT)
        result = self.provider.call(DiDiTool.TEXT_SEARCH, params, retry=False)
        return dict(version=VERSION, items=_search_rows(result, request.city))

    def _resolve_name(self, lng, lat, reserve):
        def count():
            reserve(REVERSE_COUNT, None)

        count()
        result = self.provider.call(DiDiTool.REGEOCODE, {'location': f'{lng},{lat}'}, before_retry=count)
        try:
            text = result['content'][0]['text']
            address = json.loads(text, object_pairs_hook=reject_duplicates(ValueError, 'duplicate address field'))
        except (IndexError, KeyError, RecursionError, TypeError, ValueError):
            raise PluginError(422, 'coordinate_unverified') from None
        for key in ('display_name', 'formatted_address'):
            name = address.get(key) if type(address) is dict else None
            if (type(name) is str and 0 < len(name) <= 120 and not any(ord(char) < 32 for char in name)
                    and any('\u4e00' <= char <= '\u9fff' for char in name)):
                return name
        raise PluginError(422, 'coordinate_unverified')

    def _named_estimate(self, params, reserve, *, retry=True):
        origin = self._resolve_name(params['from_lng'], params['from_lat'], reserve)
        destination = self._resolve_name(params['to_lng'], params['to_lat'], reserve)
        return self.provider.call(DiDiTool.ESTIMATE, dict(params, from_name=origin, to_name=destination),
                                  retry=retry, before_retry=lambda: reserve(ESTIMATE, DAILY_LIMIT))

    def estimate(self, request, reserve):
        result = self._named_estimate(self._points(request), reserve)
        try:
            data = result['structuredContent']
            output = EstimateOutput.model_validate(dict(
                vehicles=[dict(category=item['productCategory'], name=item['productName'],
                               price_display=item['priceText']) for item in data['items']],
                trace_id=data.get('traceId'),
            ))
        except (AttributeError, KeyError, TypeError, ValidationError):
            raise PluginError(502, 'supplier_unavailable') from None
        return dict(version=VERSION, **output.model_dump(exclude_none=True),
                    observed_at=self.clock().isoformat())

    def link(self, request, reserve):
        points = self._points(request)
        try:
            result = self.provider.call(DiDiTool.LINK, points, before_retry=lambda: reserve(LINK, DAILY_LIMIT))
        except DiDiEstimateExpired:
            reserve(ESTIMATE, DAILY_LIMIT)
            self._named_estimate(points, reserve, retry=False)
            reserve(LINK, DAILY_LIMIT)
            result = self.provider.call(DiDiTool.LINK, points, retry=False)
        data = result.get('structuredContent')
        raw = data.get('appLink') if type(data) is dict else None
        return dict(version=VERSION, **_public_link(raw, points))


def register_taxi_routes(app, *, taxi=None, checker=None, internal=frozenset(), calls=None):
    enabled = taxi is not None
    register_plugin(app, SEARCH, SearchRequest, taxi.search if enabled else None,
                    enabled=enabled, checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT,
                    count_provider_calls=True)
    register_plugin(app, ESTIMATE, EstimateRequest, taxi.estimate if enabled else None,
                    enabled=enabled, checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT,
                    count_provider_calls=True)
    register_plugin(app, LINK, LinkRequest, taxi.link if enabled else None,
                    enabled=enabled, checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT,
                    count_provider_calls=True)
