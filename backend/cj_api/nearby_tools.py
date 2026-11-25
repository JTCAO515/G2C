"""Bounded Gaode Nearby and reverse lookup, independent of the Lio run path."""

from collections import Counter, OrderedDict
from contextlib import closing
from http.client import HTTPException, HTTPSConnection
import json
import logging
import re
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from urllib.parse import unquote, urlencode, urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cj_place.models import Coordinate
from cj_strict_json import reject_duplicates
from cj_usage.nearby_budget import OPERATIONS, NearbyDuplicate, NearbyLimit

from .plugin_tools import PluginError
from .taxi_tools import WireModel


VERSION = 'NEARBY.1'
# NEARBY.2 (contracts/api/NEARBY.2.md, M4 entry 12 item 1, JT 2026-11-25): the same search with the
# "essentials" — ATMs, pharmacies, public toilets and luggage storage found by name. NEARBY.1 is frozen.
VERSIONS = ('NEARBY.1', 'NEARBY.2')
SEARCH = '/v1/tools/nearby/search'
REVERSE = '/v1/tools/nearby/reverse'
HOST = 'restapi.amap.com'
BODY_LIMIT = 256 * 1024
CATEGORY_CODES = {'food': '050000', 'coffee': '050500', 'sights': '110000', 'shopping': '060000',
                  # Gaode POI code table V1.06: 自动提款机, 药房, 公共厕所. Gaode has no foreign-card data.
                  'atm': '160300', 'pharmacy': '090601', 'toilet': '200300'}
NEARBY1_CATEGORIES = frozenset({'food', 'coffee', 'sights', 'shopping'})
# Gaode has no luggage storage category: a fixed keyword, asked for on its own so a search stays one call.
LUGGAGE_KEYWORDS = '行李寄存'
CACHE_SECONDS = 60
CACHE_CAPACITY = 32
_LOGGER = logging.getLogger(__name__)


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
    version: Literal['NEARBY.1', 'NEARBY.2']
    categories: Annotated[list[Literal['food', 'coffee', 'sights', 'shopping', 'atm', 'pharmacy', 'toilet', 'luggage']],
                          Field(min_length=1, max_length=4)]
    radius_m: Literal[500, 1000, 3000]
    sort: Literal['relevance', 'distance']

    @field_validator('categories')
    @classmethod
    def unique_categories(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('duplicate categories')
        return values

    @model_validator(mode='after')
    def known_to_the_version(self):
        if self.version == 'NEARBY.1' and not set(self.categories) <= NEARBY1_CATEGORIES:
            raise ValueError('NEARBY.1 has only the original four categories')
        if 'luggage' in self.categories and len(self.categories) > 1:
            raise ValueError('luggage storage is searched on its own')
        return self


class GaodeNearby:
    def __init__(self, key, *, connection=HTTPSConnection, operations=OPERATIONS):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,256}', key):
            raise ValueError('valid Gaode server configuration required')
        self._key = key
        self._connection = connection
        # Hotel search (#1511) reuses the same bounded transport with its own budgeted operations.
        self._operations = operations

    def query(self, operation, params, before_send):
        path = self._operations[operation] + '?' + urlencode(dict(params, key=self._key, output='json'))
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
            if type(value) is not dict:
                raise ValueError('invalid Gaode response')
            normalized = json.dumps(value, ensure_ascii=False)
            if self._key in normalized or self._key in unquote(normalized):
                raise ValueError('Gaode response echoed private configuration')
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
            if (parsed.scheme == 'https' and parsed.netloc == host and not parsed.query and not parsed.fragment
                    and '%' not in parsed.path
                    and host.endswith(('.autonavi.com', '.amap.com'))):
                return url
        except ValueError:
            pass
    return None


class _InvalidPoi(ValueError):
    """A single POI cannot be projected without inventing required fields."""


def _poi(row):
    if type(row) is not dict:
        raise _InvalidPoi('row_shape')
    name, identifier, code = (_text(row.get(field)) for field in ('name', 'id', 'typecode'))
    if not name or not identifier:
        raise _InvalidPoi('identity')
    if not code or re.fullmatch(r'[0-9]{6}', code) is None:
        raise _InvalidPoi('type_code')
    try:
        coord = Coordinate(row.get('location'))
    except ValueError:
        raise _InvalidPoi('coordinate') from None
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
        if request.categories == ['luggage']:
            what = dict(keywords=LUGGAGE_KEYWORDS)
        else:
            what = dict(types='|'.join(CATEGORY_CODES[category] for category in sorted(request.categories)))
        key = (request.version, request.center.coordinate_system, coords, tuple(sorted(what.items())),
               request.radius_m, request.sort)
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
                location=location, **what, radius=request.radius_m,
                sortrule='distance' if request.sort == 'distance' else 'weight', page_size=25,
                page_num=1, show_fields='business,photos'), authorize)
        except (KeyError, ValueError):
            raise PluginError(502, 'supplier_unavailable') from None
        pois = value.get('pois')
        if 'pois' not in value and value.get('count') == '0':
            pois = []
        if type(pois) is not list or len(pois) > 25:
            _LOGGER.warning('G2C_NEARBY_POI_PROJECTION reason=collection_shape')
            raise PluginError(502, 'supplier_unavailable')
        items = []
        rejected = Counter()
        for row in pois:
            try:
                items.append(_poi(row))
            except _InvalidPoi as error:
                rejected[str(error)] += 1
        result = dict(version=request.version, source='Gaode', items=items)
        if rejected:
            omitted = sum(rejected.values())
            _LOGGER.warning('G2C_NEARBY_POI_PROJECTION rows=%d omitted=%d reasons=%s',
                            len(pois), omitted, dict(rejected))
            if not items:
                raise PluginError(502, 'supplier_unavailable')
            result['omitted_items'] = omitted
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
