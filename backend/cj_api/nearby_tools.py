"""Bounded Gaode Nearby and reverse lookup, independent of the Lio run path."""

from collections import OrderedDict
from contextlib import closing
from http.client import HTTPException, HTTPSConnection
import json
import re
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from pydantic import Field, field_validator

from cj_place.models import Coordinate
from cj_strict_json import reject_duplicates
from cj_usage.nearby_budget import OPERATIONS, NearbyDuplicate, NearbyLimit

from .plugin_tools import PluginError
from .taxi_tools import WireModel


VERSION = 'NEARBY.1'
SEARCH = '/v1/tools/nearby/search'
REVERSE = '/v1/tools/nearby/reverse'
HOST = 'restapi.amap.com'
BODY_LIMIT = 256 * 1024
CATEGORY_CODES = {'food': '050000', 'coffee': '050500', 'sights': '110000', 'shopping': '060000'}
CACHE_SECONDS = 60
CACHE_CAPACITY = 32


class Position(WireModel):
    lat: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
    lng: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    coordinate_system: Literal['WGS-84', 'GCJ-02']


class NearbyLocationRequest(WireModel):
    version: Literal['NEARBY.1']
    request_id: Annotated[str, Field(min_length=36, max_length=36)]
    center: Position

    @field_validator('request_id')
    @classmethod
    def valid_id(cls, value):
        if str(UUID(value)) != value.lower():
            raise ValueError('explicit request UUID required')
        return value


class NearbySearchRequest(NearbyLocationRequest):
    categories: Annotated[list[Literal['food', 'coffee', 'sights', 'shopping']], Field(min_length=1, max_length=4)]
    radius_m: Literal[500, 1000, 3000]
    sort: Literal['relevance', 'distance']

    @field_validator('categories')
    @classmethod
    def unique_categories(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('duplicate categories')
        return values


class GaodeNearby:
    def __init__(self, key, *, connection=HTTPSConnection):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,256}', key):
            raise ValueError('valid Gaode server configuration required')
        self._key = key
        self._connection = connection

    def query(self, operation, params, before_send):
        path = OPERATIONS[operation] + '?' + urlencode(dict(params, key=self._key, output='json'))
        try:
            with closing(self._connection(HOST, timeout=8)) as connection:
                connection.connect()
                before_send()
                connection.request('GET', path, headers={'Accept': 'application/json'})
                with closing(connection.getresponse()) as response:
                    if response.status == 429:
                        raise PluginError(429, 'rate_limited')
                    if response.status != 200:
                        raise PluginError(502, 'supplier_unavailable')
                    raw = response.read(BODY_LIMIT + 1)
            if len(raw) > BODY_LIMIT:
                raise ValueError('Gaode response bound')
            value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate Gaode field'))
            if type(value) is not dict or self._key in json.dumps(value, ensure_ascii=False):
                raise ValueError('invalid Gaode response')
            code = value.get('infocode')
            if type(code) is str and code in {'10003', '10004', '10019', '10020', '10021', '10044'}:
                raise PluginError(429, 'rate_limited')
            if value.get('status') != '1' or code != '10000':
                raise ValueError('Gaode did not return a success receipt')
            return value, raw
        except TimeoutError:
            raise PluginError(504, 'supplier_timeout') from None
        except (HTTPException, OSError, RecursionError, UnicodeError, ValueError):
            raise PluginError(502, 'supplier_unavailable') from None


def _text(value):
    if (type(value) is str and value.strip() and len(value) <= 500
            and all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        return value
    return None


def _photo(entries):
    if type(entries) is not list:
        return None
    for item in entries:
        url = item.get('url') if type(item) is dict else None
        if type(url) is not str or len(url) > 1500 or any(ord(c) <= 32 for c in url):
            continue
        try:
            parsed = urlsplit(url)
            host = parsed.hostname or ''
            if (parsed.scheme == 'https' and parsed.netloc == host and not parsed.fragment
                    and host.endswith(('.autonavi.com', '.amap.com'))):
                return url
        except ValueError:
            pass
    return None


def _poi(row):
    name, identifier, code = (_text(row.get(field)) for field in ('name', 'id', 'typecode'))
    if not (name and identifier and code and re.fullmatch(r'[0-9]{6}', code)):
        raise ValueError('Gaode POI core fields unavailable')
    coord = Coordinate(row['location'])
    business = row.get('business')
    if type(business) is not dict:
        business = {}
    distance = row.get('distance')
    return {
        'id': identifier, 'name_zh': name, 'address_zh': _text(row.get('address')), 'type_code': code,
        'lat': float(coord.latitude), 'lng': float(coord.longitude), 'coordinate_system': 'GCJ-02',
        'distance_m': int(distance) if type(distance) is str and re.fullmatch(r'[0-9]{1,5}', distance) else None,
        'rating': _text(business.get('rating')), 'cost_cny': _text(business.get('cost')),
        'opening_hours': _text(business.get('opentime_today')), 'photo_url': _photo(row.get('photos')),
    }


class NearbyService:
    def __init__(self, provider, budget, *, clock=monotonic):
        self.provider = provider
        self.budget = budget
        self.clock = clock
        self.cache = OrderedDict()
        self.cache_lock = Lock()

    def _query(self, scope, request, operation, params, authorize):
        def before_send():
            nonlocal reservation
            authorize()
            reservation = self.budget.begin(scope, UUID(request.request_id), operation)

        reservation = None
        try:
            value, raw = self.provider.query(operation, params, before_send)
        except NearbyLimit:
            raise PluginError(429, 'quota_exceeded') from None
        except NearbyDuplicate:
            raise PluginError(409, 'request_already_used') from None
        self.budget.finish(reservation, raw)
        return value

    def _point(self, scope, request, coords, authorize):
        if request.center.coordinate_system == 'GCJ-02':
            return coords
        value = self._query(scope, request, 'convert', {'locations': coords, 'coordsys': 'gps'}, authorize)
        return Coordinate(value['locations']).raw

    def search(self, scope, request, authorize):
        authorize()
        coords = f'{request.center.lng:.6f},{request.center.lat:.6f}'
        types = '|'.join(CATEGORY_CODES[category] for category in sorted(request.categories))
        key = (request.center.coordinate_system, coords, types, request.radius_m, request.sort)
        with self.cache_lock:
            if key in self.cache:
                expires, cached = self.cache[key]
                if self.clock() < expires:
                    self.cache.move_to_end(key)
                    return cached
                del self.cache[key]
        try:
            location = self._point(scope, request, coords, authorize)
            value = self._query(scope, request, 'search', dict(
                location=location, types=types, radius=request.radius_m,
                sortrule='distance' if request.sort == 'distance' else 'weight', page_size=25,
                page_num=1, show_fields='business,photos'), authorize)
            pois = value['pois']
            if type(pois) is not list or len(pois) > 25 or any(type(row) is not dict for row in pois):
                raise ValueError('Gaode POI list unavailable')
            result = dict(version=VERSION, source='Gaode', items=[_poi(row) for row in pois])
        except (KeyError, ValueError):
            raise PluginError(502, 'supplier_unavailable') from None
        authorize()
        with self.cache_lock:
            self.cache[key] = (self.clock()+CACHE_SECONDS, result)
            self.cache.move_to_end(key)
            if len(self.cache) > CACHE_CAPACITY:
                self.cache.popitem(last=False)
        return result

    def reverse(self, scope, request, authorize):
        coords = f'{request.center.lng:.6f},{request.center.lat:.6f}'
        try:
            location = self._point(scope, request, coords, authorize)
            value = self._query(scope, request, 'reverse', {'location': location, 'extensions': 'base'}, authorize)
            block = value['regeocode']
            address = _text(block['formatted_address'])
            if not address:
                raise ValueError('Gaode address unavailable')
        except (KeyError, TypeError, ValueError):
            raise PluginError(502, 'supplier_unavailable') from None
        authorize()
        return dict(version=VERSION, source='Gaode', address_zh=address)
