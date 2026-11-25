"""ROADBOOK.1 place enrichment for Tools → Roadbook (#1516, contract contracts/api/ROADBOOK.1.md).

M4 item 18 (JT 2026-11-25): for each place not yet cached, Gaode identifies it once (detail when the POI is
known, otherwise a name + city text search) and searches around it once (restaurants and metro stations);
then the flash model writes eight short bilingual fields, Chinese and English in one call each, using only
those facts; the restaurant line is written by the server from Gaode's around-search. Every model field is
checked: prices must be approximate ranges in tickets, nothing live (availability, open or closed now, today or
for the time being), clock times only as HH:MM from Gaode's opening hours. A field that fails becomes
"check official sources". Nothing about the traveller is sent: only public place names and the city.
Routes, the worker socket, the roster and deployment belong to deploy/hk (S line).
"""

from collections import OrderedDict
from http.client import HTTPException, HTTPSConnection
import json
import logging
import re
import copy
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
import unicodedata
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cj_place.models import Coordinate
from cj_strict_json import reject_duplicates
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.roadbook_budget import MAX_OUTPUT_TOKENS, MAX_REQUEST_PLACES, MODEL, RoadbookDuplicate, RoadbookLimit

from .plugin_tools import PluginError
from .taxi_tools import WireModel, _visible

_AUDIT = logging.getLogger('cj_usage.audit')


VERSION = 'ROADBOOK.1'
ROUTE = '/v1/tools/roadbook/places'
PROMPT_VERSION = 1
FIELDS = ('summary', 'why_go', 'time_needed', 'hours_booking', 'tickets', 'getting_there', 'food_tip', 'notes')
# The restaurant tip is written by the server from Gaode's around-search, never by the model (#1569 review).
MODEL_FIELDS = tuple(field for field in FIELDS if field != 'food_tip')
LANGUAGES = ('zh', 'en')
FIELD_LIMITS = {'zh': 120, 'en': 320}
OFFICIAL = {'zh': '以官方为准。', 'en': 'Check official sources.'}
AROUND_TYPES = '050000|150500'   # Gaode 餐饮服务 | 地铁站
AROUND_RADIUS_M = 1000
AROUND_PAGE_SIZE = 25
MAX_RESTAURANTS = 3
MAX_STATIONS = 2
REQUEST_SECONDS = 120  # no supplier call starts after this, counted from the start of a request (8 places ≈ 72 s)
DASHSCOPE = 'dashscope.aliyuncs.com'
CHAT = '/compatible-mode/v1/chat/completions'
MAX_PROVIDER_RESPONSE = 128 * 1024
SUPPLIER_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
PLACE_ID = re.compile(r'[A-Za-z0-9._-]{1,64}')
POI_ID = re.compile(r'[A-Za-z0-9]{1,32}')

# Checks run on NFKC-normalized text, so full-width digits and colons count as ordinary ones.
# 块 is also a measure word (一块石碑): only 块钱, or 块 not followed by a Chinese character other than
# 左右/钱/以上/上下, is money.
_UNIT = (r'(?:元|圆|块钱|块(?![\u4e00-\u9fff])|块(?=左右|钱|以上|上下|就)|人民币|港币|港元|欧元|美元|'
         r'(?<![a-z])(?:yuan|kuai|rmb|cny|usd|hkd|eur|bucks?|dollars?)(?![a-z])|€)')
_CN_NUMBER = r'[零〇一二三四五六七八九十百千万两]'
_EN_WORDS = (r'one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|'
             r'seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand')
_EN_NUMBER = r'\b(?:' + _EN_WORDS + r')\b'
_NUMBER = r'(?:\d|' + _CN_NUMBER + r'|' + _EN_NUMBER + r')'
_PRICE = re.compile(
    r'(?:[¥$€]|(?<![a-z])us\$|(?<![a-z])(?:rmb|cny|usd|hkd|eur)(?![a-z])|人民币|港币)\s*' + _NUMBER
    + r'|' + _NUMBER + r'\s*(?:多|几|余)?\s*' + _UNIT
    + r'|(?:门票|票价|\b(?:ticket|tickets|fare|fares|price|costs?)\b)\s*(?:[:：是为约]\s*)?\d+(?!\d)'
      r'(?!\s*(?:天|日|周|个?小时|days?|weeks?|hours?))', re.IGNORECASE)
_ANY_UNIT = re.compile(r'[¥$€]|' + _UNIT, re.IGNORECASE)
# Unit-less amounts in tickets: Chinese numbers with 十/百/千/万 standing alone (成人六十，学生三十), not names or
# counts followed by a character (十一黄金周、十三陵、十人以上), or English number words from ten up.
_BIG_NUMBER = re.compile(r'[零〇一二三四五六七八九两]*[十百千万]' + _CN_NUMBER + r'*(?![\u4e00-\u9fff])|'
                         r'\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|'
                         r'twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)\b', re.IGNORECASE)
_APPROX_RANGE = re.compile(
    r'(?:约|大约|大概|about|around|approximately|roughly)\s*(?:[¥$€]\s*)?(\d{1,4})(?:\s*' + _UNIT + r')?\s*'
    r'(?:–|—|-|~|至|到|to)\s*(?:[¥$€]\s*)?(\d{1,4})(?:\s*' + _UNIT + r')?', re.IGNORECASE)
# Nothing live: availability, closures for the time being, or whether it is open now or today.
_LIVE = re.compile(r'余票|售罄|售完|已满|约满|满员|修缮|恢复开放|'
                   r'\b(?:sold out|fully booked|booked out|tickets? (?:left|remaining|available)|availability|'
                   r'renovation|under repair|reopened)\b', re.IGNORECASE)
_NOW = re.compile(r'今天|今日|今晚|目前|现在|当前|此刻|眼下|暂时|暂不|暂停|临时|正在|近期|近日|这几天|本周|这周|本月|即日起|'
                  r'\b(?:today|tonight|now|currently|right now|at the moment|at present|presently|temporarily|'
                  r'this week|this month|for now|until further notice)\b', re.IGNORECASE)
_STATE = re.compile(r'开放|营业|开门|闭馆|闭园|关门|关闭|不开|开着|休息|停业|维修|入园|开园|'
                    r'\b(?:open|opens|opened|closed|closing|shut)\b', re.IGNORECASE)
_HHMM = re.compile(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)')
_OTHER_CLOCK = re.compile(
    r'\d{1,2}\s*(?:点钟|点半|点|时(?!间|代|期|候|节))|' + _CN_NUMBER + r'{1,3}\s*(?:点钟|点半|点(?!心|评|赞|菜))|'
    r'\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|h)(?![a-z])', re.IGNORECASE)


def _clocks(text):
    return {(int(hour), int(minute)) for hour, minute in _HHMM.findall(text)}


RULES = {
    'zh': ('你在为外国游客写中国景点的简短说明。只用用户消息里给出的高德事实，不要补充事实。'
           '只输出一个 JSON 对象，键必须正好是：' + '、'.join(MODEL_FIELDS) + '，值都是简短中文字符串。'
           '价格只能写成「约 X–Y 元」这样的区间，并说明以官方为准；不要写任何实时信息，'
           '比如今天是否开放、余票、当天价格。时刻只能照抄事实里的开放时间。'
           '不要写任何餐馆或商店的名字。开放时间和预约方式最后加「以官方为准」。'),
    'en': ('You write short notes on a Chinese sight for foreign visitors. Use only the Gaode facts in the user '
           'message and add no facts of your own. Output one JSON object whose keys are exactly: '
           + ', '.join(MODEL_FIELDS) + ', each a short English string. Write prices only as a range such as '
           '"about 40–60 yuan" and say to check official sources; never state anything live such as whether '
           'it is open today, tickets left or today\'s price. Copy clock times only from the opening hours in '
           'the facts. Do not name any restaurant or shop. End the hours '
           'and booking note with "check official sources".'),
}


def _text(value, limit=200):
    if type(value) is str and value.strip() and len(value) <= limit and _visible(value):
        return value.strip()
    return None


class PlaceRequest(WireModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    name_zh: Annotated[str, Field(min_length=1, max_length=100)]
    name_en: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    city: Annotated[str, Field(min_length=1, max_length=50)]
    poi_id: Annotated[str, Field(min_length=1, max_length=32)] | None = None

    @field_validator('id')
    @classmethod
    def plain_id(cls, value):
        if PLACE_ID.fullmatch(value) is None:
            raise ValueError('plain place id required')
        return value

    @field_validator('poi_id')
    @classmethod
    def plain_poi(cls, value):
        if value is not None and POI_ID.fullmatch(value) is None:
            raise ValueError('Gaode POI id required')
        return value

    @field_validator('name_zh', 'name_en', 'city')
    @classmethod
    def visible(cls, value):
        if value is not None and _text(value, 100) is None:
            raise ValueError('visible text required')
        return value if value is None else value.strip()


class RoadbookRequest(WireModel):
    version: Literal['ROADBOOK.1']
    request_id: Annotated[str, Field(min_length=36, max_length=36)]
    places: Annotated[list[PlaceRequest], Field(min_length=1, max_length=MAX_REQUEST_PLACES)]

    @field_validator('request_id')
    @classmethod
    def valid_id(cls, value):
        if str(UUID(value)) != value.lower():
            raise ValueError('explicit request UUID required')
        return value

    @model_validator(mode='after')
    def unique(self):
        if len({place.id for place in self.places}) != len(self.places):
            raise ValueError('place ids must be unique')
        return self


def cache_key(place):
    """The Gaode POI when the App knows it, otherwise the public name in its city."""
    return f'poi:{place.poi_id}' if place.poi_id else f'name:{place.city}:{place.name_zh}'


class MemoryRoadbookCache:
    """Process cache of public place content (no account data), bounded; a Postgres table replaces it later."""

    def __init__(self, capacity=5_000):
        self.capacity = capacity
        self.values = OrderedDict()
        self._lock = Lock()

    def get(self, key):
        with self._lock:
            value = self.values.get((key, PROMPT_VERSION))
            if value is not None:
                self.values.move_to_end((key, PROMPT_VERSION))
            return copy.deepcopy(value)

    def put(self, key, value):
        with self._lock:
            self.values[(key, PROMPT_VERSION)] = copy.deepcopy(value)
            self.values.move_to_end((key, PROMPT_VERSION))
            while len(self.values) > self.capacity:
                self.values.popitem(last=False)


def _station_name(name):
    stem = re.sub(r'[(（]地铁站[)）]$', '', name).removesuffix('地铁站').strip()
    return stem if stem.endswith('站') else stem + '站'


def _distance(row):
    value = row.get('distance')
    return int(value) if type(value) is str and re.fullmatch(r'[0-9]{1,5}', value) else None


def _facts(row, around):
    """Public Gaode facts the model may use; phone numbers and ratings are left out."""
    name = _text(row.get('name'), 100)
    identifier = _text(row.get('id'), 32)
    if not name or not identifier or POI_ID.fullmatch(identifier) is None:
        return None
    business = row.get('business') if type(row.get('business')) is dict else {}
    opening = _text(business.get('opentime_week'), 200) or _text(business.get('opentime_today'), 200)
    metro, restaurants = [], []
    for item in around:
        if type(item) is not dict:
            continue
        code, title, distance = _text(item.get('typecode'), 10), _text(item.get('name'), 100), _distance(item)
        if not code or not title or distance is None:
            continue
        if code.startswith('1505') and len(metro) < MAX_STATIONS:
            metro.append(dict(name_zh=_station_name(title), distance_m=distance))
        elif code.startswith('05') and len(restaurants) < MAX_RESTAURANTS:
            address = _text(item.get('address'), 200)
            try:
                point = Coordinate(item.get('location'))
            except (TypeError, ValueError):
                continue
            if address:  # the driver card needs a Chinese address
                restaurants.append(dict(name_zh=title, address_zh=address, lat=float(point.latitude),
                                        lng=float(point.longitude), distance_m=distance))
    facts = dict(poi_id=identifier, name=name, address=_text(row.get('address'), 200),
                 city=_text(row.get('cityname'), 50), opening=opening, metro=metro, restaurants=restaurants)
    return facts


def messages_for(language, facts):
    public = {key: facts[key] for key in ('name', 'opening', 'metro') if key in facts}
    return [dict(role='system', content=RULES[language]),
            dict(role='user', content=json.dumps(public, ensure_ascii=False))]


def _field(name, value, facts, language):
    text = _text(value, FIELD_LIMITS[language])
    if text is None:
        return None
    plain = unicodedata.normalize('NFKC', text)
    if _LIVE.search(plain) or (_NOW.search(plain) and _STATE.search(plain)):
        return None  # nothing live: availability, or whether it is open now, today or for now
    if name == 'tickets':
        rest = _APPROX_RANGE.sub(lambda match: '' if int(match.group(1)) < int(match.group(2)) else match.group(0), plain)
        if _PRICE.search(rest) or _ANY_UNIT.search(rest) or re.search(r'\d', rest) or _BIG_NUMBER.search(rest):
            return None  # every amount must sit in an "about X–Y" range with X < Y
    elif _PRICE.search(plain):
        return None  # prices only in tickets
    if _OTHER_CLOCK.search(plain):
        return None  # only HH:MM copied from Gaode's opening hours
    clocks = _clocks(plain)
    if clocks and (name != 'hours_booking'
                   or not clocks <= _clocks(unicodedata.normalize('NFKC', facts.get('opening') or ''))):
        return None
    return text


def food_tip(restaurants, language):
    """The restaurant line, written from Gaode's around-search only, within the field limit."""
    def line(rows):
        if language == 'zh':
            return '附近可就餐：' + '、'.join(f"{item['name_zh']}（约 {item['distance_m']} 米）" for item in rows) + '。'
        return 'Places to eat nearby: ' + ', '.join(f"{item['name_zh']} (about {item['distance_m']} m)" for item in rows) + '.'

    for count in range(len(restaurants), 0, -1):
        if len(line(restaurants[:count])) <= FIELD_LIMITS[language]:
            return line(restaurants[:count])
    return ('附近没有找到带地址的餐馆，以地图为准。' if language == 'zh'
            else 'No restaurant with an address was found nearby; check a map.')


def checked_fields(raw, facts, language):
    """The model's JSON with every unchecked claim replaced, or None when it is not the agreed object."""
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate roadbook field'))
    except (TypeError, ValueError):
        return None
    if type(value) is not dict or set(value) != set(MODEL_FIELDS):
        return None
    fields = {name: _field(name, value[name], facts, language) or OFFICIAL[language] for name in MODEL_FIELDS}
    return {name: fields.get(name) or food_tip(facts.get('restaurants') or [], language) for name in FIELDS}


def refusal(raw, finish):
    """Why a model reply was not used, with counts only: never any of the reply's text."""
    if finish != 'stop':
        return dict(reason='model_cut_off')
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate roadbook field'))
    except (TypeError, ValueError):
        return dict(reason='model_not_json')
    if type(value) is not dict:
        return dict(reason='model_not_object')
    return dict(reason='model_fields', missing=len(set(MODEL_FIELDS) - set(value)),
                extra=len(set(value) - set(MODEL_FIELDS)), food_tip=int('food_tip' in value))


def _unavailable(request, index, language, why):
    _AUDIT.info('ROADBOOK_PLACE_UNAVAILABLE request_id=%s index=%s language=%s %s', request.request_id, index,
                language or '-', ' '.join(f'{key}={value}' for key, value in why.items()))


class DashScopeRoadbook:
    """Minimal Beijing DashScope chat client for flash, JSON output, no thinking, at most 1000 tokens."""

    def __init__(self, api_key, *, connection=None, timeout=30):
        if type(api_key) is not str or not api_key:
            raise ValueError('server-side DashScope key required')
        self._api_key = api_key
        self._connection = connection or (lambda: HTTPSConnection(DASHSCOPE, timeout=timeout))

    def generate(self, language, messages, reserve):
        body = json.dumps(dict(model=MODEL, messages=messages, max_tokens=MAX_OUTPUT_TOKENS, temperature=0.3,
                               response_format={'type': 'json_object'}, enable_thinking=False),
                          ensure_ascii=False).encode()
        connection = self._connection()
        try:
            if hasattr(connection, 'connect'):
                connection.connect()  # DNS and TLS first; the call is reserved only when it can be sent
            reserve()
            connection.request('POST', CHAT, body, {'Authorization': 'Bearer ' + self._api_key,
                                                    'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = response.read(MAX_PROVIDER_RESPONSE + 1)
            if response.status != 200 or len(data) > MAX_PROVIDER_RESPONSE:
                raise PluginError(502, 'supplier_unavailable')
            reply = json.loads(data, object_pairs_hook=reject_duplicates(ValueError, 'duplicate DashScope field'))
            choice, = reply['choices']
            supplier, text, finish = reply['id'], choice['message']['content'], choice['finish_reason']
            usage = {'input_tokens': reply['usage']['prompt_tokens'],
                     'output_tokens': reply['usage']['completion_tokens']}
            if (reply['model'] != MODEL or type(supplier) is not str or SUPPLIER_ID.fullmatch(supplier) is None
                    or type(text) is not str or finish not in ('stop', 'length') or self._api_key in text):
                raise ValueError('unexpected receipt')
        except PluginError:
            raise
        except (KeyError, TypeError, ValueError, OSError, HTTPException):
            raise PluginError(502, 'supplier_unavailable') from None
        finally:
            connection.close()
        return supplier, usage, text, finish


class RoadbookService:
    def __init__(self, gaode, model, budget, places, cache):
        self.gaode = gaode
        self.model = model
        self.budget = budget
        self.places = places
        self.cache = cache

    def _gaode(self, scope, request, index, operation, params, authorize):
        def reserve():
            nonlocal attempt
            authorize()
            attempt = self.places.begin(scope, UUID(request.request_id), index, operation)

        attempt = None
        value, raw = self.gaode.query(operation, params, reserve)
        self.places.finish(attempt, raw)
        if type(value) is not dict or (value.get('status') not in (None, '1')):
            raise PluginError(502, 'supplier_unavailable')
        pois = value.get('pois')
        if 'pois' not in value and value.get('count') == '0':
            pois = []
        if type(pois) is not list:
            raise PluginError(502, 'supplier_unavailable')
        return pois

    def _model(self, operation, stage, language, facts, authorize):
        def reserve():
            authorize()
            self.budget.begin(operation, stage)

        supplier, usage, text, finish = self.model.generate(language, messages_for(language, facts), reserve)
        self.budget.finish(operation, stage, supplier, usage)
        checked = checked_fields(text, facts, language) if finish == 'stop' else None
        return checked, (refusal(text, finish) if checked is None else None)

    def _enrich_one(self, scope, request, operation, index, place, stages, authorize):
        if place.poi_id:
            rows = self._gaode(scope, request, index, 'detail', dict(id=place.poi_id, show_fields='business'),
                               authorize)
        else:
            rows = self._gaode(scope, request, index, 'text', dict(
                keywords=place.name_zh, region=place.city, city_limit='true', page_size=1, page_num=1,
                show_fields='business'), authorize)
        row = rows[0] if rows and type(rows[0]) is dict else None
        try:
            location = Coordinate(row.get('location')).raw if row else None
        except (TypeError, ValueError):
            location = None
        if row is None or location is None:
            _unavailable(request, index, None, dict(reason='gaode_no_place' if row is None else 'gaode_no_location'))
            return None
        around = self._gaode(scope, request, index, 'around', dict(
            location=location, types=AROUND_TYPES, radius=AROUND_RADIUS_M, sortrule='distance',
            page_size=AROUND_PAGE_SIZE, page_num=1, show_fields='business'), authorize)
        facts = _facts(row, around)
        if facts is None:
            _unavailable(request, index, None, dict(reason='gaode_bad_place'))
            return None
        content = {}
        for language in LANGUAGES:
            # Model stages run in order across the request: a skipped place does not leave a gap.
            stage = stages[0]
            stages[0] += 1
            checked, why = self._model(operation, stage, language, facts, authorize)
            if checked is None:
                _unavailable(request, index, language, why)
                return None
            content[language] = checked
        return dict(poi_id=facts['poi_id'], content=content, metro=facts['metro'], restaurants=facts['restaurants'])

    def enrich(self, scope, request, authorize):
        deadline = monotonic() + REQUEST_SECONDS
        outer = authorize

        def authorize():
            if monotonic() >= deadline:
                raise PluginError(503, 'unavailable')
            outer()

        outer()
        results, todo = {}, []
        for place in request.places:
            cached = self.cache.get(cache_key(place))
            if cached is not None:
                results[place.id] = dict(id=place.id, status='ready', **cached)
            else:
                todo.append(place)
        if todo:
            try:
                operation = self.budget.operation(scope, UUID(request.request_id), len(todo))
                allowed = not self.budget.cache_only() and self.budget.admits(operation)
            except RoadbookLimit:
                allowed = False
            except Exception:
                raise PluginError(503, 'unavailable') from None  # nothing was sent
            stopped = None if allowed else 'limited'
            stages = [0]
            for index, place in enumerate(todo):
                if stopped is not None:
                    results[place.id] = dict(id=place.id, status=stopped)
                    continue
                try:
                    value = self._enrich_one(scope, request, operation, index, place, stages, authorize)
                except RoadbookDuplicate:
                    raise PluginError(409, 'request_already_used') from None
                except RoadbookLimit:
                    stopped = 'limited'
                    results[place.id] = dict(id=place.id, status=stopped)
                    continue
                except (BudgetUnknown, PluginError) as error:
                    # A failed or unknown supplier call keeps its hold; later model stages cannot start.
                    _unavailable(request, index, None, dict(reason='supplier', code=getattr(error, 'code', 'unknown')))
                    stopped = 'unavailable'
                    results[place.id] = dict(id=place.id, status=stopped)
                    continue
                if value is None:
                    results[place.id] = dict(id=place.id, status='unavailable')
                    continue
                self.cache.put(cache_key(place), value)
                results[place.id] = dict(id=place.id, status='ready', **value)
        outer()
        return dict(version=VERSION, places=[results[place.id] for place in request.places])
