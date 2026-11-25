"""TRANSPORT.1: intercity trains and flights for the Tools tab (#1520).

Read-only. Trains come from AMap cross-city transit planning through the private worker relay (the AMap key
and the AMap cash ledger live only in the worker; `rail_items` is the projection that relay applies), flights
from the existing VariFlight relay.
Booking and payment always happen outside the app; seat availability is never claimed (12306 decides).
Each mode is reserved and fails on its own, so one supplier problem never hides the other mode.
Authorization: docs/authorizations/M4.md items 11, 12 (④) and 14 (JT 2026-11-25, #1518).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import logging
import re
from typing import Literal
from uuid import uuid4

from pydantic import field_validator, model_validator

from .plugin_tools import SHANGHAI, PluginError, register_plugin
from .taxi_tools import WireModel
from .variflight_tools import ROUTE as FLIGHTS_ROUTE, DAILY_LIMIT as FLIGHTS_DAILY_LIMIT


ROUTE = '/v1/tools/transport/search'
VERSION = 'TRANSPORT.1'
DAILY_LIMIT = 50                      # searches per person per day (route)
RAIL_DAILY_LIMIT = 30                 # M4 item 12 ④: per person per day, enforced by the worker budget
RAIL_TOTAL_LIMIT = 1500               # M4 item 12 ④: all accounts together, shared AMap cash service table
MAX_DAYS_AHEAD = 60
MAX_ITEMS = 20
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')
TRAIN = re.compile(r'[A-Z]{0,2}[0-9]{1,5}')
CLOCK = re.compile(r'([01][0-9]|2[0-3]):?([0-5][0-9])')
STAMP = re.compile(r'([0-9]{4}-[0-9]{2}-[0-9]{2})[ T]([01][0-9]|2[0-3]):([0-5][0-9])(:[0-5][0-9])?')
RAIL_NOTE = dict(availability_note_zh='余票以 12306 为准', availability_note_en='Seats left: check on 12306')
FLIGHT_NOTE = dict(price_note_zh='价格随时变动，以订票页为准', price_note_en='Prices change often; check when booking')
# 12306 seat-class codes; any other code is dropped rather than guessed.
LOGGER = logging.getLogger(__name__)
ITEM_KEYS = frozenset({'number', 'depart_station', 'arrive_station', 'depart_time', 'arrive_time', 'duration_min',
                       'next_day', 'seats', 'availability'})
TIME = re.compile(r'([01][0-9]|2[0-3]):[0-5][0-9]')
SEATS = {
    '9': ('商务座', 'Business class'), 'P': ('特等座', 'Premium class'), 'M': ('一等座', 'First class'),
    'O': ('二等座', 'Second class'), '4': ('软卧', 'Soft sleeper'), '3': ('硬卧', 'Hard sleeper'),
    '1': ('硬座', 'Hard seat'),
}
# AMap cross-city transit names its seat classes in Chinese (HK smoke run -42, #1521): 「火车」 prefix, berths per
# sleeper (上/中/下铺). Berths fold into their sleeper class; 「不分仓位级别」 and anything else is dropped.
SEAT_NAMES = {
    '商务座': ('商务座', 'Business class'), '特等座': ('特等座', 'Premium class'), '一等座': ('一等座', 'First class'),
    '二等座': ('二等座', 'Second class'), '软卧': ('软卧', 'Soft sleeper'), '硬卧': ('硬卧', 'Hard sleeper'),
    '软座': ('软座', 'Soft seat'), '硬座': ('硬座', 'Hard seat'), '无座': ('无座', 'Standing (no seat)'),
}
SEAT_CLASSES = set(SEATS.values()) | set(SEAT_NAMES.values())
SEAT_RANK = {pair: rank for rank, pair in enumerate(SEAT_NAMES.values())}


@dataclass(frozen=True)
class City:
    id: str
    name_zh: str
    name_en: str
    centre: tuple[float, float]       # GCJ-02 (lng, lat), city centre used as the transit planning point
    rail_slug: str                    # Trip.com China train route page slug (checked 2026-11-25)
    flight_code: str                  # Trip.com flight search city code
    stations: tuple[tuple[str, str], ...]
    airports: tuple[tuple[str, str, str], ...]


def _city(id, zh, en, centre, code, stations, airports):
    return City(id, zh, en, centre, id, code, tuple(stations), tuple(airports))


# Same twelve cities as the App (LioTransport.swift).
CITIES = {city.id: city for city in (
    _city('beijing', '北京', 'Beijing', (116.407526, 39.904030), 'BJS',
          [('北京南站', 'Beijing South Railway Station'), ('北京西站', 'Beijing West Railway Station'),
           ('北京站', 'Beijing Railway Station')],
          [('PEK', '北京首都国际机场', 'Beijing Capital International Airport'),
           ('PKX', '北京大兴国际机场', 'Beijing Daxing International Airport')]),
    _city('shanghai', '上海', 'Shanghai', (121.473701, 31.230416), 'SHA',
          [('上海虹桥站', 'Shanghai Hongqiao Railway Station'), ('上海站', 'Shanghai Railway Station'),
           ('上海南站', 'Shanghai South Railway Station')],
          [('SHA', '上海虹桥国际机场', 'Shanghai Hongqiao International Airport'),
           ('PVG', '上海浦东国际机场', 'Shanghai Pudong International Airport')]),
    _city('guangzhou', '广州', 'Guangzhou', (113.264385, 23.129112), 'CAN',
          [('广州南站', 'Guangzhou South Railway Station'), ('广州东站', 'Guangzhou East Railway Station'),
           ('广州站', 'Guangzhou Railway Station')],
          [('CAN', '广州白云国际机场', 'Guangzhou Baiyun International Airport')]),
    _city('shenzhen', '深圳', 'Shenzhen', (114.057868, 22.543099), 'SZX',
          [('深圳北站', 'Shenzhen North Railway Station'), ('福田站', 'Futian Railway Station'),
           ('深圳站', 'Shenzhen Railway Station')],
          [('SZX', '深圳宝安国际机场', "Shenzhen Bao'an International Airport")]),
    _city('chengdu', '成都', 'Chengdu', (104.065735, 30.659462), 'CTU',
          [('成都东站', 'Chengdu East Railway Station'), ('成都西站', 'Chengdu West Railway Station'),
           ('成都南站', 'Chengdu South Railway Station')],
          [('TFU', '成都天府国际机场', 'Chengdu Tianfu International Airport'),
           ('CTU', '成都双流国际机场', 'Chengdu Shuangliu International Airport')]),
    _city('chongqing', '重庆', 'Chongqing', (106.551556, 29.563009), 'CKG',
          [('重庆北站', 'Chongqing North Railway Station'), ('重庆西站', 'Chongqing West Railway Station')],
          [('CKG', '重庆江北国际机场', 'Chongqing Jiangbei International Airport')]),
    _city('xian', '西安', "Xi'an", (108.948024, 34.263161), 'SIA',
          [('西安北站', "Xi'an North Railway Station"), ('西安站', "Xi'an Railway Station")],
          [('XIY', '西安咸阳国际机场', "Xi'an Xianyang International Airport")]),
    _city('hangzhou', '杭州', 'Hangzhou', (120.155070, 30.274084), 'HGH',
          [('杭州东站', 'Hangzhou East Railway Station'), ('杭州西站', 'Hangzhou West Railway Station'),
           ('杭州站', 'Hangzhou Railway Station')],
          [('HGH', '杭州萧山国际机场', 'Hangzhou Xiaoshan International Airport')]),
    _city('nanjing', '南京', 'Nanjing', (118.796877, 32.060255), 'NKG',
          [('南京南站', 'Nanjing South Railway Station'), ('南京站', 'Nanjing Railway Station')],
          [('NKG', '南京禄口国际机场', 'Nanjing Lukou International Airport')]),
    _city('wuhan', '武汉', 'Wuhan', (114.305393, 30.593099), 'WUH',
          [('武汉站', 'Wuhan Railway Station'), ('汉口站', 'Hankou Railway Station'),
           ('武昌站', 'Wuchang Railway Station')],
          [('WUH', '武汉天河国际机场', 'Wuhan Tianhe International Airport')]),
    _city('guilin', '桂林', 'Guilin', (110.290194, 25.273566), 'KWL',
          [('桂林北站', 'Guilin North Railway Station'), ('桂林西站', 'Guilin West Railway Station'),
           ('桂林站', 'Guilin Railway Station')],
          [('KWL', '桂林两江国际机场', 'Guilin Liangjiang International Airport')]),
    _city('kunming', '昆明', 'Kunming', (102.832891, 24.880095), 'KMG',
          [('昆明南站', 'Kunming South Railway Station'), ('昆明站', 'Kunming Railway Station')],
          [('KMG', '昆明长水国际机场', 'Kunming Changshui International Airport')]),
)}
STATIONS_EN = {zh: en for city in CITIES.values() for zh, en in city.stations}
AIRPORTS = {code: (zh, en) for city in CITIES.values() for code, zh, en in city.airports}


def today():
    return datetime.now(SHANGHAI).date()


class TransportInput(WireModel):
    version: Literal['TRANSPORT.1']
    origin: str
    destination: str
    date: str
    modes: list[Literal['rail', 'flight']]

    @field_validator('origin', 'destination')
    @classmethod
    def known_city(cls, value):
        if value not in CITIES:
            raise ValueError('unsupported city')
        return value

    @field_validator('date')
    @classmethod
    def travel_day(cls, value):
        if not DATE.fullmatch(value):
            raise ValueError('ISO calendar date required')
        day = date.fromisoformat(value)
        if not today() <= day <= today() + timedelta(days=MAX_DAYS_AHEAD):
            raise ValueError('travel day out of range')
        return day.isoformat()

    @model_validator(mode='after')
    def distinct(self):
        if self.origin == self.destination:
            raise ValueError('two different cities required')
        if not self.modes or len(set(self.modes)) != len(self.modes):
            raise ValueError('one or two distinct modes required')
        return self


def _text(value, limit=40):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or 0x7f <= ord(char) < 0xa0 or 0xd800 <= ord(char) <= 0xdfff for char in value)):
        raise ValueError('invalid supplier text')
    return value.strip()


def _clock(value):
    match = CLOCK.fullmatch(value) if type(value) is str else None
    if match is None:
        raise ValueError('invalid supplier time')
    return match[1] + ':' + match[2], int(match[1]) * 60 + int(match[2])


def _span(depart, arrive):
    minutes = arrive - depart
    return (minutes + 1440, True) if minutes <= 0 else (minutes, False)


def _station(value):
    name = _text(value)
    name = name if name.endswith('站') else name + '站'
    station = dict(name_zh=name)
    if name in STATIONS_EN:
        station['name_en'] = STATIONS_EN[name]
    return station


SEAT_CODE = re.compile(r'[A-Za-z0-9]{1,8}')


def _seat_class(code):
    """The (zh, en) class for a 12306 letter code or an AMap Chinese seat name, or None."""
    if type(code) is not str:
        return None
    if code in SEATS:
        return SEATS[code]
    name = code.removeprefix('火车')
    for berth in ('上铺', '中铺', '下铺'):
        name = name.removesuffix(berth)
    return SEAT_NAMES.get(name)


def _seats(spaces, dropped):
    """One entry per seat class at its lowest listed price (AMap repeats classes and berths), cheapest first."""
    if spaces in (None, [], {}):
        return []
    if type(spaces) is not list or len(spaces) > 32:
        raise ValueError('invalid seat list')
    lowest = {}
    for space in spaces:
        seat_class = _seat_class(space.get('code')) if type(space) is dict else None
        if type(space) is dict and seat_class is None:
            code = space.get('code')
            dropped.append(code if type(code) is str and SEAT_CODE.fullmatch(code) else '?')
        if seat_class is None or type(space.get('cost')) is not str:
            continue
        try:
            price = Decimal(space['cost'])
        except InvalidOperation:
            continue
        if not price.is_finite() or not 0 < price <= 100000 or price != price.quantize(Decimal('0.01')):
            continue
        minor = int(price * 100)
        if seat_class not in lowest or minor < lowest[seat_class]:
            lowest[seat_class] = minor
    ordered = sorted(lowest.items(), key=lambda pair: (pair[1], SEAT_RANK.get(pair[0], -1)))
    return [dict(class_zh=zh, class_en=en, price_cny_minor=minor) for (zh, en), minor in ordered]


def rail_items(value):
    """Project an AMap /v3/direction/transit/integrated reply to train items (used by the worker relay)."""
    route = value.get('route') if type(value) is dict else None
    transits = route.get('transits') if type(route) is dict else None
    if type(transits) is not list or len(transits) > 32:
        raise ValueError('bounded transit options required')
    items, seen, dropped, without_seats = [], set(), [], 0
    for transit in transits:
        segments = transit.get('segments') if type(transit) is dict else None
        if type(segments) is not list or len(segments) > 64:
            raise ValueError('bounded transit segments required')
        for segment in segments:
            railway = segment.get('railway') if type(segment) is dict else None
            # Walking and metro segments often carry an empty railway object ({"alters": [], "spaces": []});
            # only a segment with a train number is a train.
            if railway in (None, {}, []) or type(railway) is dict and railway.get('trip') in (None, '', []):
                continue
            number = _text(railway['trip'], 8)
            if not TRAIN.fullmatch(number):
                raise ValueError('invalid train number')
            departure, arrival = railway['departure_stop'], railway['arrival_stop']
            depart_time, depart = _clock(departure['time'])
            arrive_time, arrive = _clock(arrival['time'])
            minutes, next_day = _span(depart, arrive)
            item = dict(number=number, depart_station=_station(departure['name']),
                        arrive_station=_station(arrival['name']), depart_time=depart_time, arrive_time=arrive_time,
                        duration_min=minutes, next_day=next_day, seats=_seats(railway.get('spaces'), dropped),
                        availability=None)
            if railway.get('spaces') in (None, [], {}):
                without_seats += 1
            if (number, depart_time) not in seen:
                seen.add((number, depart_time))
                items.append(item)
    # Content-free smoke diagnostics (#1521): supplier seat-class codes only, never names or prices.
    if without_seats:
        LOGGER.info('transport_rail_segments_without_seats count=%d', without_seats)
    if dropped:
        LOGGER.info('transport_rail_seat_codes_dropped codes=%s', ','.join(dict.fromkeys(dropped[:20])))
    items.sort(key=lambda item: (item['depart_time'], item['number']))
    return items[:MAX_ITEMS]


def _valid_station(station):
    if type(station) is not dict or 'name_zh' not in station or not station.keys() <= {'name_zh', 'name_en'}:
        return False
    try:
        _text(station['name_zh'], 41)
        if 'name_en' in station:
            _text(station['name_en'], 120)
    except ValueError:
        return False
    return station['name_zh'].endswith('站')


def validate_rail_items(items):
    """Whether a worker reply has exactly the shape `rail_items` produces; checked once where it enters the API."""
    if type(items) is not list or len(items) > MAX_ITEMS:
        return False
    classes = SEAT_CLASSES
    for item in items:
        if (type(item) is not dict or item.keys() != ITEM_KEYS or item['availability'] is not None
                or type(item['number']) is not str or not TRAIN.fullmatch(item['number'])
                or not _valid_station(item['depart_station']) or not _valid_station(item['arrive_station'])
                or type(item['depart_time']) is not str or not TIME.fullmatch(item['depart_time'])
                or type(item['arrive_time']) is not str or not TIME.fullmatch(item['arrive_time'])
                or type(item['duration_min']) is not int or not 0 < item['duration_min'] <= 7 * 1440
                or type(item['next_day']) is not bool
                or type(item['seats']) is not list or len(item['seats']) > len(SEAT_CLASSES)):
            return False
        named = [(seat.get('class_zh'), seat.get('class_en')) for seat in item['seats'] if type(seat) is dict]
        if len(set(map(str, named))) != len(item['seats']):
            return False
        for seat in item['seats']:
            if (type(seat) is not dict or seat.keys() != {'class_zh', 'class_en', 'price_cny_minor'}
                    or type(seat['class_zh']) is not str or type(seat['class_en']) is not str
                    or (seat['class_zh'], seat['class_en']) not in classes
                    or type(seat['price_cny_minor']) is not int or not 0 < seat['price_cny_minor'] <= 10_000_000):
                return False
    return True


def _stamp(value):
    match = STAMP.fullmatch(value) if type(value) is str else None
    if match is None:
        raise ValueError('invalid flight time')
    return match[1], match[2] + ':' + match[3], int(match[2]) * 60 + int(match[3])


def _airport(code, fallback_zh, fallback_en):
    zh, en = AIRPORTS.get(code, (fallback_zh, fallback_en))
    airport = dict(iata=code)
    if zh:
        airport['name_zh'] = zh
    if en:
        airport['name_en'] = en
    return airport


def _flight_items(rows, day):
    items, seen = [], set()
    for row in rows:
        try:
            depart_day, depart_time, depart = _stamp(row.get('planned_departure'))
            arrive_day, arrive_time, arrive = _stamp(row.get('planned_arrival'))
            if depart_day != day or 'departure' not in row or 'arrival' not in row:
                continue
            if arrive_day == depart_day:
                minutes, next_day = _span(depart, arrive)
            elif date.fromisoformat(arrive_day) == date.fromisoformat(depart_day) + timedelta(days=1):
                minutes, next_day = arrive + 1440 - depart, True
            else:
                continue
        except ValueError:
            continue
        key = (row['departure'], row['arrival'], depart_time, arrive_time)
        if key in seen:
            continue
        seen.add(key)
        item = dict(number=row['flight_number'])
        carrier = {name: row[field] for name, field in (('name_zh', 'airline_name_zh'), ('name_en', 'airline_name_en'))
                   if field in row}
        if carrier:
            item['carrier'] = carrier
        item.update(
            depart_airport=_airport(row['departure'], row.get('departure_airport_name_zh'),
                                    row.get('departure_airport_name_en')),
            arrive_airport=_airport(row['arrival'], row.get('arrival_airport_name_zh'),
                                    row.get('arrival_airport_name_en')),
            depart_time=depart_time, arrive_time=arrive_time, duration_min=minutes, next_day=next_day)
        items.append(item)
    items.sort(key=lambda item: (item['depart_time'], item['number']))
    return items[:MAX_ITEMS]


def links(origin, destination, day, modes, wrap=lambda url: url):
    result = []
    if 'rail' in modes:
        result.append(dict(mode='rail', provider='12306', url='https://www.12306.cn/en/index.html'))
        result.append(dict(mode='rail', provider='trip.com', url=wrap(
            f'https://www.trip.com/trains/china/route/{origin.rail_slug}-to-{destination.rail_slug}/')))
    if 'flight' in modes:
        # Trip.com's own parameter order; every value is a fixed ASCII code or an ISO date.
        query = '&'.join(name + '=' + value for name, value in (
            ('dcity', origin.flight_code.lower()), ('acity', destination.flight_code.lower()), ('ddate', day),
            ('triptype', 'ow'), ('class', 'y'), ('quantity', '1')))
        result.append(dict(mode='flight', provider='trip.com',
                           url=wrap('https://www.trip.com/flights/showfarefirst?' + query)))
    return result


@dataclass(frozen=True)
class RouteLookup:
    """A VariFlight route lookup over all airports of both cities (codes come from CITIES, never from input)."""
    date: str
    departure: str
    arrival: str

    def tool_call(self):
        return 'getFlightList', dict(dep=self.departure, arr=self.arrival, date=self.date)


def _status(error):
    if error.code == 'sign_in_required':
        raise error
    if error.code == 'quota_exceeded':
        return 'quota_exceeded'
    if error.code == 'not_enabled':
        return 'not_enabled'
    return 'unavailable'


class TransportService:
    """`rail` is the worker relay client, `flights` the (payment-guarded) VariFlight relay; either may be absent.

    The rail client is called as `trains(token, request_id, origin_id, destination_id, day)`; the worker
    re-authorizes the caller's own bearer, meters AMap per person and in the shared cash ledger, and returns
    `rail_items` or raises PluginError.
    """

    def __init__(self, *, rail=None, flights=None, wrap_link=lambda url: url):
        self.rail, self.flights, self.wrap_link = rail, flights, wrap_link

    def _rail(self, origin, destination, day, token):
        result = dict(status='not_enabled', source='AMap', items=[], **RAIL_NOTE)
        if self.rail is None:
            return result
        try:
            items = self.rail.trains(token, str(uuid4()), origin.id, destination.id, day)
        except PluginError as error:
            return dict(result, status=_status(error))
        except (OSError, ValueError, KeyError, TypeError):
            return dict(result, status='unavailable')
        if not validate_rail_items(items):
            # Content-free: never log what the worker sent.
            LOGGER.warning('transport_rail_reply_invalid')
            return dict(result, status='unavailable')
        return dict(result, status='ok' if items else 'empty', items=items)

    def _flight(self, origin, destination, day, reserve):
        result = dict(status='not_enabled', source='VariFlight', items=[], **FLIGHT_NOTE)
        if self.flights is None:
            return result
        try:
            # Same operation name as the FLIGHTS.1 route on the shared flights counter (M4 item 14: 50 a day together).
            reserve(FLIGHTS_ROUTE, FLIGHTS_DAILY_LIMIT)
        except PluginError as error:
            return dict(result, status=_status(error))
        # One getFlightList per search: VariFlight takes up to three airports per side, comma separated (#1521).
        lookup = RouteLookup(day, ','.join(code for code, _, _ in origin.airports[:3]),
                             ','.join(code for code, _, _ in destination.airports[:3]))
        try:
            rows = self.flights.query(lookup, reserve)['items']
        except PluginError as error:
            return dict(result, status=_status(error))
        except (KeyError, TypeError):
            return dict(result, status='unavailable')
        items = _flight_items(rows, day)
        return dict(result, status='ok' if items else 'empty', items=items)

    def query(self, request, reserve, token):
        origin, destination, day = CITIES[request.origin], CITIES[request.destination], request.date
        body = dict(version=VERSION, date=day,
                    origin=dict(id=origin.id, name_zh=origin.name_zh, name_en=origin.name_en),
                    destination=dict(id=destination.id, name_zh=destination.name_zh, name_en=destination.name_en))
        if 'rail' in request.modes:
            body['rail'] = self._rail(origin, destination, day, token)
        if 'flight' in request.modes:
            body['flight'] = self._flight(origin, destination, day, reserve)
        body['links'] = links(origin, destination, day, request.modes, self.wrap_link)
        return body


def register_transport(app, *, service=None, checker=None, internal=frozenset(), calls=None):
    register_plugin(app, ROUTE, TransportInput, service.query if service else None, enabled=service is not None,
                    checker=checker, internal=internal, calls=calls, limit=DAILY_LIMIT, count_provider_calls=True,
                    pass_token=True)
