"""METRO-NEARBY.1 station surroundings for the metro map (#1450, contract contracts/api/METRO-NEARBY.1.md).

M4 entry 12 item 5 (JT 2026-11-25, #1577): sights, shopping, food and coffee around a bundled metro station.
The App sends a city and station id only; the position comes from the station table generated from the
App's own bundled maps, so this route can never receive the traveller's location. Gaode is asked once per
search (fixed 800 m, nearest first); results are cached per station and category set for a day and shared by
all accounts. English names come from the existing place-name translation (entry 9), best effort.
Deployment wiring (route, socket, roster) belongs to deploy/hk (S line).
"""

from collections import Counter, OrderedDict
import copy
import json
import logging
from pathlib import Path
import re
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from cj_strict_json import reject_duplicates
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.metro_nearby_budget import MetroNearbyDuplicate, MetroNearbyLimit

from .nearby_tools import CATEGORY_CODES, _InvalidPoi, _poi
from .plugin_tools import PluginError
from .taxi_tools import TaxiService, WireModel


VERSION = 'METRO-NEARBY.1'
ROUTE = '/v1/tools/metro/nearby'
RADIUS_M = 800
PAGE_SIZE = 25
CACHE_SECONDS = 24 * 3600
CACHE_CAPACITY = 4096
STATIONS = Path(__file__).with_name('metro_stations.v1.json')
_LOGGER = logging.getLogger(__name__)


class MetroNearbyRequest(WireModel):
    version: Literal['METRO-NEARBY.1']
    request_id: Annotated[str, Field(min_length=36, max_length=36)]
    city_id: Annotated[str, Field(pattern=r'^[a-z]{2,20}$')]
    station_id: Annotated[str, Field(pattern=r'^[a-z]{2}[0-9]{3}$')]
    categories: Annotated[list[Literal['sights', 'shopping', 'food', 'coffee']], Field(min_length=1, max_length=4)]
    language: Literal['zh', 'en']

    @field_validator('request_id')
    @classmethod
    def valid_id(cls, value):
        if str(UUID(value)) != value.lower():
            raise ValueError('explicit request UUID required')
        return value

    @field_validator('categories')
    @classmethod
    def unique_categories(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('duplicate categories')
        return values


def build_station_table(metro_dir):
    """Every bundled station with a position: {city: {station: [lng, lat]}} (GCJ-02), from the App's maps."""
    table = {}
    for path in sorted(Path(metro_dir).glob('LioMetroMap.*.v1.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        table[data['city']] = {station['id']: station['geo'] for station in data['stations'] if 'geo' in station}
    return table


def write_station_table(table, path=STATIONS):
    lines = [f' {json.dumps(city)}: {json.dumps(stations, separators=(",", ":"))}' for city, stations in table.items()]
    path.write_text('{\n' + ',\n'.join(lines) + '\n}\n', encoding='utf-8')


def load_stations(path=STATIONS):
    """(city, station) → Gaode 'lng,lat'. Positions are checked once here, at the boundary."""
    table = json.loads(Path(path).read_text(encoding='utf-8'),
                       object_pairs_hook=reject_duplicates(ValueError, 'duplicate station table field'))
    if type(table) is not dict:
        raise ValueError('invalid station table')
    stations = {}
    for city, rows in table.items():
        if re.fullmatch(r'[a-z]{2,20}', city) is None or type(rows) is not dict:
            raise ValueError('invalid station table')
        for station, point in rows.items():
            if (re.fullmatch(r'[a-z]{2}[0-9]{3}', station) is None or type(point) is not list or len(point) != 2
                    or not all(type(v) in (int, float) for v in point)
                    or not (73 <= point[0] <= 136 and 3 <= point[1] <= 54)):
                raise ValueError('invalid station table')
            stations[(city, station)] = f'{point[0]:.6f},{point[1]:.6f}'
    return stations


class MetroNearbyService:
    def __init__(self, provider, budget, *, stations=None, translator=None, clock=monotonic):
        self.provider = provider
        self.budget = budget
        self.stations = load_stations() if stations is None else stations
        self.clock = clock
        # Reuse the taxi place-name translation (entry 9): batching, alignment checks and its own cache.
        self._english = TaxiService(None, translator=translator) if translator is not None else None
        self.cache = OrderedDict()
        self.cache_lock = Lock()

    def _query(self, scope, request, params, authorize):
        def before_send():
            nonlocal reservation
            authorize()
            reservation = self.budget.begin(scope, UUID(request.request_id), 'search')

        reservation = None
        try:
            value, raw = self.provider.query('search', params, before_send)
        except MetroNearbyLimit:
            raise PluginError(429, 'quota_exceeded') from None
        except MetroNearbyDuplicate:
            raise PluginError(409, 'request_already_used') from None
        except BudgetUnknown:
            raise PluginError(503, 'unavailable') from None
        self.budget.finish(reservation, raw)
        return value

    def _lookup(self, scope, request, point, categories, authorize):
        try:
            value = self._query(scope, request, dict(
                location=point, types='|'.join(CATEGORY_CODES[c] for c in categories), radius=RADIUS_M,
                sortrule='distance', page_size=PAGE_SIZE, page_num=1, show_fields='business,photos'), authorize)
        except (KeyError, ValueError):
            raise PluginError(502, 'supplier_unavailable') from None
        pois = value.get('pois')
        if 'pois' not in value and value.get('count') == '0':
            pois = []
        if type(pois) is not list or len(pois) > PAGE_SIZE:
            _LOGGER.warning('G2C_METRO_NEARBY_POI_PROJECTION reason=collection_shape')
            raise PluginError(502, 'supplier_unavailable')
        items, rejected, seen = [], Counter(), set()
        for row in pois:
            try:
                item = _poi(row)
            except _InvalidPoi as error:
                rejected[str(error)] += 1
                continue
            if item['id'] in seen:
                rejected['duplicate'] += 1
                continue
            seen.add(item['id'])
            items.append(item)
        if rejected:
            _LOGGER.warning('G2C_METRO_NEARBY_POI_PROJECTION rows=%d omitted=%d reasons=%s',
                            len(pois), sum(rejected.values()), dict(rejected))
            if not items:
                raise PluginError(502, 'supplier_unavailable')
        return items, sum(rejected.values())

    def search(self, scope, request, authorize, token=None):
        authorize()
        point = self.stations.get((request.city_id, request.station_id))
        if point is None:
            raise PluginError(404, 'station_not_found')
        categories = tuple(sorted(request.categories))
        key = (request.city_id, request.station_id, categories)
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
            cached = self._lookup(scope, request, point, categories, authorize)
            with self.cache_lock:
                self.cache[key] = (self.clock() + CACHE_SECONDS, cached)
                self.cache.move_to_end(key)
                if len(self.cache) > CACHE_CAPACITY:
                    self.cache.popitem(last=False)
        base, omitted = cached
        items = copy.deepcopy(base)
        if request.language == 'en' and self._english is not None and token is not None:
            self._english._add_english(items, token)
        authorize()
        result = dict(version=VERSION, source='Gaode', city_id=request.city_id, station_id=request.station_id,
                      radius_m=RADIUS_M, items=items)
        if omitted:
            result['omitted_items'] = omitted
        return result


if __name__ == '__main__':  # regenerate after the bundled maps change: python -m cj_api.metro_nearby <Metro dir>
    import sys

    write_station_table(build_station_table(sys.argv[1]))
