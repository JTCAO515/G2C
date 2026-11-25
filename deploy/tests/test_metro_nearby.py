from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cj_api.metro_nearby import (
    RADIUS_M, VERSION, MetroNearbyRequest, MetroNearbyService, build_station_table, load_stations,
)
from cj_api.plugin_tools import PluginError
from cj_usage.authorization_budget import AMAP_PRICE, AuthorizationBudget, authorization_usage, shared_place_services
from cj_usage.metro_nearby_budget import SERVICE, MetroNearbyBudget, SHANGHAI
from cj_usage.nearby_budget import NearbyBudget

ROOT = Path(__file__).resolve().parents[2]
METRO = ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/Metro'
STATIONS = {('guangzhou', 'gz012'): '113.322900,23.132500', ('guangzhou', 'gz013'): '113.330000,23.140000'}


def payload(**other):
    body = dict(version=VERSION, request_id=str(uuid4()), city_id='guangzhou', station_id='gz012',
                categories=['sights', 'shopping'], language='zh')
    body.update(other)
    return body


class Supplier:
    def __init__(self, pois=None):
        self.calls = []
        self.pois = pois if pois is not None else [
            dict(name='天河城', id='B001', typecode='060101', location='113.322700,23.132700', distance='31',
                 address='天河路208号', business={'rating': '4.6'}),
        ]

    def query(self, operation, params, reserve):
        reserve()
        self.calls.append((operation, params))
        data = {'pois': self.pois}
        return data, json.dumps(data).encode()


@pytest.fixture
def ledger(tmp_path):
    return AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 25, 19, tzinfo=SHANGHAI))


def service_for(ledger, supplier=None, translator=None):
    return MetroNearbyService(supplier or Supplier(), MetroNearbyBudget(ledger), stations=dict(STATIONS),
                              translator=translator)


def test_searches_around_the_station_once_and_shares_the_day_long_cache(ledger):
    supplier = Supplier()
    service = service_for(ledger, supplier)
    request = MetroNearbyRequest.model_validate(payload(categories=['shopping', 'sights']))
    result = service.search('owner-a', request, lambda: None)
    assert result['version'] == VERSION and result['source'] == 'Gaode' and result['radius_m'] == RADIUS_M == 800
    assert (result['city_id'], result['station_id']) == ('guangzhou', 'gz012')
    assert result['items'][0]['name_zh'] == '天河城' and result['items'][0]['distance_m'] == 31
    assert supplier.calls == [('search', dict(
        location='113.322900,23.132500', types='060000|110000', radius=800, sortrule='distance', page_size=25,
        page_num=1, show_fields='business,photos'))]
    # Another account, the categories in another order, another language: the same cached search.
    again = MetroNearbyRequest.model_validate(payload(categories=['sights', 'shopping'], language='en'))
    assert service.search('owner-b', again, lambda: None)['items'] == result['items']
    assert len(supplier.calls) == 1
    with ledger.connect() as db:
        counts, estimates, _ = authorization_usage(db)
    assert counts['place'] == 1 and estimates['place'] == AMAP_PRICE
    assert '113.322900' not in str(ledger.inspect())


def test_an_unknown_station_is_404_before_any_budget_or_supplier_call(ledger):
    supplier = Supplier()
    service = service_for(ledger, supplier)
    for city, station in [('guangzhou', 'gz999'), ('beijing', 'gz012')]:
        with pytest.raises(PluginError) as missing:
            service.search('owner', MetroNearbyRequest.model_validate(payload(city_id=city, station_id=station)),
                           lambda: None)
        assert (missing.value.status, missing.value.code) == (404, 'station_not_found')
    assert supplier.calls == [] and ledger.inspect() == []


@pytest.mark.parametrize('change', [
    dict(center=dict(lat=23.13, lng=113.32, coordinate_system='GCJ-02')),  # never a position
    dict(radius_m=800), dict(city_id='Guangzhou'), dict(city_id='g'), dict(station_id='gz12'),
    dict(station_id='GZ012'), dict(categories=[]), dict(categories=['sights', 'sights']),
    dict(categories=['hotel']), dict(language='fr'), dict(version='NEARBY.1'), dict(request_id='not-a-uuid'),
])
def test_requests_carry_a_station_only(change):
    with pytest.raises(ValidationError):
        MetroNearbyRequest.model_validate(payload(**change))


def test_daily_and_total_limits_refuse_before_the_supplier_and_stay_apart_from_nearby(ledger, monkeypatch):
    from cj_usage import metro_nearby_budget, nearby_budget

    monkeypatch.setattr(metro_nearby_budget, 'DAILY_ACCOUNT_LIMIT', 1)
    supplier = Supplier()
    service = service_for(ledger, supplier)
    service.search('owner-a', MetroNearbyRequest.model_validate(payload(station_id='gz012')), lambda: None)
    with pytest.raises(PluginError) as daily:
        service.search('owner-a', MetroNearbyRequest.model_validate(payload(station_id='gz013')), lambda: None)
    assert (daily.value.status, daily.value.code) == (429, 'quota_exceeded')
    assert len(supplier.calls) == 1
    # Another account still has its own day; then the M4 total stops everyone.
    monkeypatch.setattr(metro_nearby_budget, 'M4_OPERATION_LIMIT', 2)
    service.search('owner-b', MetroNearbyRequest.model_validate(payload(station_id='gz013')), lambda: None)
    service.cache.clear()
    with pytest.raises(PluginError) as total:
        service.search('owner-c', MetroNearbyRequest.model_validate(payload(station_id='gz012')), lambda: None)
    assert (total.value.status, total.value.code) == (429, 'quota_exceeded')
    assert len(supplier.calls) == 2
    # Station searches never use Nearby's own count.
    monkeypatch.setattr(nearby_budget, 'DAILY_ACCOUNT_LIMIT', 1)
    monkeypatch.setattr(nearby_budget, 'M4_OPERATION_LIMIT', 1)
    attempt = NearbyBudget(ledger).begin('owner-a', uuid4(), 'search')
    assert attempt[0].startswith('amap-nearby.1:')


def test_a_request_id_is_never_sent_twice(ledger):
    supplier = Supplier()
    service = service_for(ledger, supplier)
    original = MetroNearbyRequest.model_validate(payload(station_id='gz012'))
    service.search('owner', original, lambda: None)
    service.cache.clear()
    with pytest.raises(PluginError) as duplicate:
        service.search('owner', original, lambda: None)
    assert (duplicate.value.status, duplicate.value.code) == (409, 'request_already_used')
    assert len(supplier.calls) == 1


@pytest.mark.parametrize('mode', ['mixed', 'empty', 'invalid'])
def test_projection_keeps_usable_rows(ledger, mode):
    good = Supplier().pois[0]
    broken = dict(name='no position', id='B002', typecode='060101', location=[])
    rows = {'mixed': [good, broken, dict(good)], 'empty': [], 'invalid': [broken]}[mode]
    service = service_for(ledger, Supplier(rows))
    request = MetroNearbyRequest.model_validate(payload())
    if mode == 'invalid':
        with pytest.raises(PluginError) as failed:
            service.search('owner', request, lambda: None)
        assert failed.value.status == 502
        return
    result = service.search('owner', request, lambda: None)
    if mode == 'mixed':
        assert [row['id'] for row in result['items']] == ['B001'] and result['omitted_items'] == 2
    else:
        assert result['items'] == [] and 'omitted_items' not in result


def test_english_names_are_best_effort_and_never_cached_into_chinese(ledger):
    def translator(token, text):
        assert token == 'app-token'
        return '[1] Teemall\n[2] 208 Tianhe Road'

    service = service_for(ledger, translator=translator)
    english = service.search('owner', MetroNearbyRequest.model_validate(payload(language='en')), lambda: None,
                             token='app-token')
    assert english['items'][0]['name_en'] == 'Teemall' and english['items'][0]['address_en'] == '208 Tianhe Road'
    chinese = service.search('owner', MetroNearbyRequest.model_validate(payload(language='zh')), lambda: None,
                             token='app-token')
    assert 'name_en' not in chinese['items'][0]
    broken = service_for(ledger, translator=lambda token, text: 'nonsense')
    plain = broken.search('owner-b', MetroNearbyRequest.model_validate(payload(language='en')), lambda: None,
                          token='app-token')
    assert plain['items'][0]['name_zh'] == '天河城' and 'name_en' not in plain['items'][0]


def test_the_service_is_a_separately_counted_place_service():
    origin, operations, separate = shared_place_services()[SERVICE]
    assert origin == 'https://restapi.amap.com' and operations == {'search': '/v5/place/around'} and separate


def test_the_station_table_is_the_apps_bundled_positions():
    """The server's table is generated from the App's own maps (#1585); the two never drift apart."""
    bundled = build_station_table(METRO)
    stations = load_stations()
    expected = {(city, station): f'{point[0]:.6f},{point[1]:.6f}'
                for city, rows in bundled.items() for station, point in rows.items()}
    assert stations == expected
    assert len(bundled) == 41 and len(stations) > 6500


def test_a_damaged_station_table_is_refused(tmp_path):
    for table in [{'guangzhou': {'gz012': [200, 23]}}, {'guangzhou': {'gz012': [113.3]}},
                  {'Guangzhou': {'gz012': [113.3, 23.1]}}, {'guangzhou': {'012': [113.3, 23.1]}}]:
        path = tmp_path / 'table.json'
        path.write_text(json.dumps(table))
        with pytest.raises(ValueError):
            load_stations(path)
