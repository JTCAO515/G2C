"""HOTEL.2 hotel search for Tools → Hotels (#1511, contract contracts/api/HOTEL.2.md).

Step one of #1508 (JT 2026-11-25): Gaode lists hotels (M4 entry 12 item 3), the nearest subway station is
measured from one Gaode around-search, English names come from the existing translation relay (entry 9),
and "Book" is a relay hand-off to a plain Trip.com search page without an affiliate ID until JT hands over
the Trip.com credentials. Gaode has no foreign-guest data, so every hotel says "unknown". Nothing is booked
or paid through this service. Deployment wiring (routes, socket, roster) belongs to deploy/hk (S line).
"""

from collections import Counter, OrderedDict
import copy
from datetime import date
import logging
import math
import re
import secrets
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from urllib.parse import urlencode
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cj_place.models import Coordinate
from cj_usage.hotel_budget import HotelDuplicate, HotelLimit
from cj_usage.metered_exit import BudgetUnknown

from .plugin_tools import PluginError
from .taxi_tools import TaxiService, WireModel, _visible


VERSION = 'HOTEL.2'
ROUTE = '/v1/tools/hotel/search'
HANDOFF_PATH = '/v1/tools/hotel/out/'
HOTEL_TYPES = '100000'    # Gaode 住宿服务
SUBWAY_TYPES = '150500'   # Gaode 地铁站
SEARCH_RADIUS_M = 3000
SUBWAY_RADIUS_M = 3000
NEAREST_SUBWAY_M = 2000   # farther stations are not worth showing as "nearest metro"
PAGE_SIZE = 20
SUBWAY_PAGE_SIZE = 25
CACHE_SECONDS = 60
CACHE_CAPACITY = 64
APPLIED = ['near']
UNAPPLIED = ['check_in', 'check_out', 'guests', 'price']
_LOGGER = logging.getLogger(__name__)

# Trip.com hotel list city IDs, each checked on www.trip.com/hotels/list?cityId=… on 2026-11-25 (#1511).
TRIP_CITIES = {
    '北京': ('Beijing', 1), '上海': ('Shanghai', 2), '天津': ('Tianjin', 3), '重庆': ('Chongqing', 4),
    '哈尔滨': ('Harbin', 5), '大连': ('Dalian', 6), '青岛': ('Qingdao', 7), '西安': ("Xi'an", 10),
    '敦煌': ('Dunhuang', 11), '南京': ('Nanjing', 12), '无锡': ('Wuxi', 13), '苏州': ('Suzhou', 14),
    '扬州': ('Yangzhou', 15), '杭州': ('Hangzhou', 17), '黄山': ('Huangshan', 23), '厦门': ('Xiamen', 25),
    '张家界': ('Zhangjiajie', 27), '成都': ('Chengdu', 28), '深圳': ('Shenzhen', 30), '珠海': ('Zhuhai', 31),
    '广州': ('Guangzhou', 32), '桂林': ('Guilin', 33), '昆明': ('Kunming', 34), '大理': ('Dali', 36),
    '丽江': ('Lijiang', 37), '贵阳': ('Guiyang', 38), '乌鲁木齐': ('Urumqi', 39), '拉萨': ('Lhasa', 41),
    '海口': ('Haikou', 42), '三亚': ('Sanya', 43), '济南': ('Jinan', 144), '长沙': ('Changsha', 206),
    '洛阳': ('Luoyang', 350), '宁波': ('Ningbo', 375), '南宁': ('Nanning', 380), '沈阳': ('Shenyang', 451),
    '武汉': ('Wuhan', 477), '郑州': ('Zhengzhou', 559),
}
TRIP_CITY_IDS = {name: city_id for name, (_, city_id) in TRIP_CITIES.items()}
_ENGLISH_CITIES = {re.sub(r"[^a-z]", '', english.lower()): name for name, (english, _) in TRIP_CITIES.items()}
TRIP_LIST = 'https://www.trip.com/hotels/list'
TRIP_HOME = 'https://www.trip.com/hotels/'
_HANDLE = re.compile(r'[A-Za-z0-9_-]{22}')


def _clean_text(value, *, limit=100):
    if not value.strip() or len(value) > limit or not _visible(value):
        raise ValueError('visible text required')
    return value.strip()


def chinese_city(value):
    """Gaode wants a Chinese city name; travellers often type the English one."""
    text = value.strip()
    english = _ENGLISH_CITIES.get(re.sub(r'[^a-z]', '', text.lower()))
    if english is not None:
        return english
    return text[:-1] if len(text) > 2 and text.endswith('市') else text


class Near(WireModel):
    query: Annotated[str, Field(min_length=1, max_length=100)]

    @field_validator('query')
    @classmethod
    def visible(cls, value):
        return _clean_text(value)


class PriceRange(WireModel):
    min: Annotated[int, Field(ge=0, le=100_000)] | None = None
    max: Annotated[int, Field(ge=0, le=100_000)] | None = None

    @model_validator(mode='after')
    def ordered(self):
        if self.min is None and self.max is None:
            raise ValueError('choose a bound')
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError('min must not exceed max')
        return self


class HotelSearchRequest(WireModel):
    version: Literal['HOTEL.2']
    request_id: Annotated[str, Field(min_length=36, max_length=36)]
    city: Annotated[str, Field(min_length=1, max_length=100)]
    near: Near | None = None
    check_in: str
    check_out: str
    guests: Annotated[int, Field(ge=1, le=10)]
    price_cny: PriceRange | None = None
    language: Literal['zh', 'en']

    @field_validator('request_id')
    @classmethod
    def valid_id(cls, value):
        if str(UUID(value)) != value.lower():
            raise ValueError('explicit request UUID required')
        return value

    @field_validator('city')
    @classmethod
    def visible_city(cls, value):
        return _clean_text(value)

    @field_validator('check_in', 'check_out')
    @classmethod
    def iso_date(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('expected YYYY-MM-DD')
        return value

    @model_validator(mode='after')
    def stay(self):
        nights = (date.fromisoformat(self.check_out) - date.fromisoformat(self.check_in)).days
        if not 1 <= nights <= 30:
            raise ValueError('stay must be 1 to 30 nights')
        return self


def handoff_target(hotel_name, city, check_in, check_out, guests, language):
    """A plain Trip.com hotel list for the city, dates and guests, with the hotel name in the search box.

    Parameters checked on www.trip.com on 2026-11-25: the list needs `cityId` (city names are ignored),
    `checkin`/`checkout`/`adult`/`crn` prefill the stay, `searchWord` fills the search box. The host and path
    are fixed here; no affiliate ID until JT hands over the Trip.com credentials (#1368). `locale` stays
    en-US: Trip.com's own locale switch for Chinese was not verified. `language` is kept for that change.
    """
    del language
    city_id = TRIP_CITY_IDS.get(chinese_city(city))
    if city_id is None:
        return TRIP_HOME
    return TRIP_LIST + '?' + urlencode(dict(
        cityId=city_id, searchWord=hotel_name, checkin=check_in, checkout=check_out, crn=1, adult=guests,
        curr='CNY', locale='en-US'))


class HandoffStore:
    """Opaque, unguessable handle → Trip.com URL, bounded and short-lived. Handles do not survive a restart."""

    def __init__(self, *, capacity=10_000, ttl_seconds=24 * 3600, clock=monotonic):
        self.capacity = capacity
        self.ttl = ttl_seconds
        self.clock = clock
        self._targets = OrderedDict()
        self._lock = Lock()

    def put(self, url):
        if not (url == TRIP_HOME or url.startswith(TRIP_LIST + '?')):
            raise ValueError('hand-off only to the fixed Trip.com pages')
        handle = secrets.token_urlsafe(16)
        with self._lock:
            self._targets[handle] = (self.clock() + self.ttl, url)
            while len(self._targets) > self.capacity:
                self._targets.popitem(last=False)
        return handle

    def get(self, handle):
        if type(handle) is not str or _HANDLE.fullmatch(handle) is None:
            return None
        with self._lock:
            entry = self._targets.get(handle)
            if entry is None:
                return None
            expires, url = entry
            if self.clock() >= expires:
                del self._targets[handle]
                return None
            return url


def _text(value, limit=200):
    if type(value) is str and value.strip() and len(value) <= limit and _visible(value):
        return value.strip()
    return None


def _station_name(name):
    stem = re.sub(r'[(（]地铁站[)）]$', '', name).removesuffix('地铁站').strip()
    return stem if stem.endswith('站') else stem + '站'


def _metres(lat1, lng1, lat2, lng2):
    """Great-circle distance; GCJ-02 offsets cancel out over a few kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(a))


class _InvalidHotel(ValueError):
    """A row cannot become a hotel card without inventing a required field."""


def _hotel(row, fallback_city):
    if type(row) is not dict:
        raise _InvalidHotel('row_shape')
    name, identifier, code = (_text(row.get(field)) for field in ('name', 'id', 'typecode'))
    if not name or not identifier:
        raise _InvalidHotel('identity')
    if not code or re.fullmatch(r'10[0-9]{4}', code) is None:
        raise _InvalidHotel('type_code')
    address = _text(row.get('address'))
    if not address:
        raise _InvalidHotel('address')  # the driver card needs a Chinese address
    try:
        point = Coordinate(row.get('location'))
    except ValueError:
        raise _InvalidHotel('coordinate') from None
    business = row.get('business') if type(row.get('business')) is dict else {}
    item = dict(id=identifier, name_zh=name, address_zh=address, lat=float(point.latitude),
                lng=float(point.longitude), coordinate_system='GCJ-02', foreign_guests='unknown',
                city=_text(row.get('cityname')) or fallback_city)
    rating = _text(business.get('rating'), 10)
    if rating:
        item['rating'] = rating
    cost = business.get('cost')
    if type(cost) is str and re.fullmatch(r'[0-9]{1,6}(\.[0-9]{1,2})?', cost) and float(cost) > 0:
        price = round(float(cost))
        item['price_cny'] = dict(min=price, max=price)
        item['price_kind'] = 'reference'
    return item


def _pois(value, limit):
    pois = value.get('pois')
    if 'pois' not in value and value.get('count') == '0':
        pois = []
    if type(pois) is not list or len(pois) > limit:
        raise PluginError(502, 'supplier_unavailable')
    return pois


class HotelSearchService:
    def __init__(self, provider, budget, handoffs, *, public_origin, translator=None, clock=monotonic):
        self.provider = provider
        self.budget = budget
        self.handoffs = handoffs
        self.public_origin = public_origin
        self.clock = clock
        # Reuse the taxi place-name translation (entry 9, amended #1523): batching, alignment checks, cache.
        self._english = TaxiService(None, translator=translator) if translator is not None else None
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
        except HotelLimit:
            raise PluginError(429, 'quota_exceeded') from None
        except HotelDuplicate:
            raise PluginError(409, 'request_already_used') from None
        except BudgetUnknown:
            raise PluginError(503, 'unavailable') from None
        self.budget.finish(reservation, raw)
        return value

    def _lookup(self, scope, request, city, near, authorize):
        if near is not None:
            found = self._query(scope, request, 'geocode', {'address': near, 'city': city}, authorize)
            geocodes = found.get('geocodes')
            if type(geocodes) is not list or not geocodes or type(geocodes[0]) is not dict:
                raise PluginError(404, 'place_not_found')
            try:
                center = Coordinate(geocodes[0].get('location')).raw
            except ValueError:
                raise PluginError(502, 'supplier_unavailable') from None
            listed = self._query(scope, request, 'hotels_around', dict(
                location=center, types=HOTEL_TYPES, radius=SEARCH_RADIUS_M, sortrule='distance',
                page_size=PAGE_SIZE, page_num=1, show_fields='business'), authorize)
        else:
            center = None
            listed = self._query(scope, request, 'hotels_text', dict(
                region=city, city_limit='true', types=HOTEL_TYPES, page_size=PAGE_SIZE, page_num=1,
                show_fields='business'), authorize)
        rows = _pois(listed, PAGE_SIZE)
        items, rejected, seen = [], Counter(), set()
        for row in rows:
            try:
                item = _hotel(row, city)
            except _InvalidHotel as error:
                rejected[str(error)] += 1
                continue
            if item['id'] in seen:
                rejected['duplicate'] += 1  # the App rejects a page with repeated IDs
                continue
            seen.add(item['id'])
            items.append(item)
        if rejected:
            _LOGGER.warning('G2C_HOTEL_POI_PROJECTION rows=%d omitted=%d reasons=%s',
                            len(rows), sum(rejected.values()), dict(rejected))
        if not items:
            return items, sum(rejected.values())
        if center is None:
            center = '{:.6f},{:.6f}'.format(sum(i['lng'] for i in items) / len(items),
                                            sum(i['lat'] for i in items) / len(items))
        stations = []
        for row in _pois(self._query(scope, request, 'subway', dict(
                location=center, types=SUBWAY_TYPES, radius=SUBWAY_RADIUS_M, sortrule='distance',
                page_size=SUBWAY_PAGE_SIZE, page_num=1), authorize), SUBWAY_PAGE_SIZE):
            name = _text(row.get('name')) if type(row) is dict else None
            try:
                point = Coordinate(row.get('location')) if name else None
            except ValueError:
                point = None
            if point is not None:
                stations.append((_station_name(name), float(point.latitude), float(point.longitude)))
        for item in items:
            nearest = min(((_metres(item['lat'], item['lng'], lat, lng), name) for name, lat, lng in stations),
                          default=None)
            if nearest is not None and nearest[0] <= NEAREST_SUBWAY_M:
                item['metro'] = dict(name_zh=nearest[1], distance_m=round(nearest[0]))
        return items, sum(rejected.values())

    def search(self, scope, request, authorize, token=None):
        authorize()
        city = chinese_city(request.city)
        near = request.near.query if request.near is not None else None
        key = (city, near)
        cached = None
        with self.cache_lock:
            if key in self.cache:
                expires, value = self.cache[key]
                if self.clock() < expires:
                    self.cache.move_to_end(key)
                    cached = value
                else:
                    del self.cache[key]
        if cached is None:
            try:
                cached = self._lookup(scope, request, city, near, authorize)
            except (KeyError, TypeError, ValueError):
                raise PluginError(502, 'supplier_unavailable') from None
            with self.cache_lock:
                self.cache[key] = (self.clock() + CACHE_SECONDS, cached)
                self.cache.move_to_end(key)
                if len(self.cache) > CACHE_CAPACITY:
                    self.cache.popitem(last=False)
        base, omitted = cached
        items = copy.deepcopy(base)
        if request.language == 'en' and self._english is not None and token is not None:
            self._english._add_english(items, token)
        for item in items:
            hotel_city = item.pop('city')
            target = handoff_target(item['name_zh'], hotel_city, request.check_in, request.check_out,
                                    request.guests, request.language)
            item['booking_url'] = self.public_origin + HANDOFF_PATH + self.handoffs.put(target)
        authorize()
        # The App shows the affiliate disclosure only when the hand-off carries an affiliate ID (#225).
        result = dict(version=VERSION, source='Gaode', affiliate_links=False, applied_filters=list(APPLIED),
                      unapplied_filters=list(UNAPPLIED), items=items)
        if omitted:
            result['omitted_items'] = omitted
        return result
