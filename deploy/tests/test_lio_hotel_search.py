"""HOTEL.2 hotel search (#1511): Gaode list, nearest subway, Trip.com hand-off, budget (M4 entries 3, 9, 12③)."""

from datetime import datetime, timedelta
import json
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cj_api.lio_hotel_search import (
    HANDOFF_PATH, HandoffStore, HotelSearchRequest, HotelSearchService, ROUTE, TRIP_CITY_IDS, VERSION,
    handoff_target,
)
from cj_api.nearby_tools import GaodeNearby
from cj_api.plugin_tools import PluginError
from cj_usage.authorization_budget import (
    AMAP_PRICE, CNY_SCALE, LIMITS, AuthorizationBudget, authorization_usage,
)
from cj_usage.hotel_budget import HotelBudget, SHANGHAI
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.nearby_budget import NearbyBudget

ORIGIN = 'https://relay.example.invalid'


def payload(**other):
    body = dict(version='HOTEL.2', request_id=str(uuid4()), city='北京', near=dict(query='王府井'),
                check_in='2026-12-03', check_out='2026-12-05', guests=2, price_cny=dict(min=300, max=600),
                language='en')
    body.update(other)
    return {key: value for key, value in body.items() if value is not None}


HOTELS = [
    dict(name='北京王府井希尔顿酒店', id='B0H1', typecode='100102', location='116.412700,39.913900',
         address='王府井东街8号', cityname='北京市', business={'rating': '4.7', 'cost': '980'}),
    dict(name='全季酒店(北京东单店)', id='B0H2', typecode='100105', location='116.418000,39.915700',
         address='东单北大街甲98号', cityname='北京市', business={'rating': '4.6'}),
    # Far from every station: no metro line rather than a misleading one.
    dict(name='郊外客栈', id='B0H3', typecode='100105', location='116.600000,40.100000',
         address='某村1号', cityname='北京市', business={'cost': 'free'}),
    dict(name='缺地址酒店', id='B0H4', typecode='100105', location='116.41,39.91', address=[]),
]
STATIONS = [
    dict(name='王府井(地铁站)', id='BV1', typecode='150500', location='116.411200,39.910800'),
    dict(name='东单(地铁站)', id='BV2', typecode='150500', location='116.418500,39.909500'),
]


class Supplier:
    def __init__(self, hotels=HOTELS):
        self.calls = []
        self.hotels = hotels

    def query(self, operation, params, reserve):
        reserve()
        self.calls.append((operation, params))
        replies = dict(
            geocode={'geocodes': [{'location': '116.410886,39.911521'}]},
            hotels_around={'pois': self.hotels}, hotels_text={'pois': self.hotels},
            subway={'pois': STATIONS},
        )
        data = replies[operation]
        return data, json.dumps(data, ensure_ascii=False).encode()


@pytest.fixture
def ledger(tmp_path):
    return AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 25, 19, tzinfo=SHANGHAI))


def service_for(ledger, supplier=None, translator=None):
    return HotelSearchService(supplier or Supplier(), HotelBudget(ledger), HandoffStore(), public_origin=ORIGIN,
                              translator=translator)


# --- request -------------------------------------------------------------------------------------------------

def test_request_accepts_only_the_contract_fields():
    request = HotelSearchRequest.model_validate(payload())
    assert request.near.query == '王府井' and request.price_cny.max == 600
    assert HotelSearchRequest.model_validate(payload(near=None, price_cny=None)).near is None
    for bad in (
        payload(version='HOTEL.1'), payload(request_id='not-a-uuid'), payload(city=' '), payload(city='北\n京'),
        payload(near=dict(query='')), payload(near=dict(query='街' * 101)), payload(check_in='2026-12-3'),
        payload(check_out='2026-12-03'), payload(check_out='2027-01-03'), payload(guests=0), payload(guests=11),
        payload(price_cny=dict()), payload(price_cny=dict(min=600, max=300)), payload(price_cny=dict(min=-1)),
        payload(language='fr'), payload(phone='13800000000'), payload(user_id='u1'),
    ):
        with pytest.raises(ValidationError):
            HotelSearchRequest.model_validate(bad)


# --- search --------------------------------------------------------------------------------------------------

def test_landmark_search_geocodes_lists_hotels_and_measures_the_nearest_subway(ledger):
    supplier = Supplier()
    result = service_for(ledger, supplier).search('owner-a', HotelSearchRequest.model_validate(payload()),
                                                  lambda: None)
    assert [operation for operation, _ in supplier.calls] == ['geocode', 'hotels_around', 'subway']
    assert supplier.calls[0][1] == {'address': '王府井', 'city': '北京'}
    assert supplier.calls[1][1] == dict(location='116.410886,39.911521', types='100000', radius=3000,
                                        sortrule='distance', page_size=20, page_num=1, show_fields='business')
    assert supplier.calls[2][1]['types'] == '150500' and supplier.calls[2][1]['location'] == '116.410886,39.911521'
    assert result['version'] == VERSION == 'HOTEL.2' and result['source'] == 'Gaode'
    assert result['affiliate_links'] is False  # no affiliate ID until JT hands over the credentials
    assert result['applied_filters'] == ['near']
    assert result['unapplied_filters'] == ['check_in', 'check_out', 'guests', 'price']
    hilton, ji, far = result['items']
    assert result['omitted_items'] == 1  # no usable address: the driver card needs one
    assert hilton['name_zh'] == '北京王府井希尔顿酒店' and hilton['address_zh'] == '王府井东街8号'
    assert hilton['coordinate_system'] == 'GCJ-02' and hilton['lat'] == 39.9139 and hilton['lng'] == 116.4127
    assert hilton['rating'] == '4.7'
    assert hilton['price_cny'] == {'min': 980, 'max': 980} and hilton['price_kind'] == 'reference'
    assert hilton['metro']['name_zh'] == '王府井站' and 300 <= hilton['metro']['distance_m'] <= 400
    assert ji['metro']['name_zh'] == '东单站' and 'price_cny' not in ji
    assert 'metro' not in far and 'price_cny' not in far
    # Gaode has no foreign-guest data: never claim a policy (#1508 step one).
    assert {item['foreign_guests'] for item in result['items']} == {'unknown'}
    assert all(item['booking_url'].startswith(ORIGIN + HANDOFF_PATH) for item in result['items'])
    assert len({item['booking_url'] for item in result['items']}) == 3
    assert 'name_en' not in hilton  # Chinese screen never asks for translation


def test_city_only_search_uses_text_search_and_the_hotels_centre_for_subways(ledger):
    supplier = Supplier(hotels=HOTELS[:2])
    result = service_for(ledger, supplier).search(
        'owner-a', HotelSearchRequest.model_validate(payload(near=None, language='zh')), lambda: None)
    assert [operation for operation, _ in supplier.calls] == ['hotels_text', 'subway']
    assert supplier.calls[0][1] == dict(region='北京', city_limit='true', types='100000', page_size=20,
                                        page_num=1, show_fields='business')
    assert supplier.calls[1][1]['location'] == '116.415350,39.914800'
    assert result['applied_filters'] == ['near'] and len(result['items']) == 2


def test_unknown_landmark_and_empty_lists_are_explicit(ledger):
    class Nowhere(Supplier):
        def query(self, operation, params, reserve):
            if operation == 'geocode':
                reserve()
                self.calls.append((operation, params))
                return {'count': '0', 'geocodes': []}, b'{}'
            return super().query(operation, params, reserve)

    with pytest.raises(PluginError) as missing:
        service_for(ledger, Nowhere()).search('owner-a', HotelSearchRequest.model_validate(payload()), lambda: None)
    assert (missing.value.status, missing.value.code) == (404, 'place_not_found')
    empty = service_for(ledger, Supplier(hotels=[])).search(
        'owner-b', HotelSearchRequest.model_validate(payload(near=None)), lambda: None)
    assert empty['items'] == []


def test_repeated_gaode_ids_become_one_card(ledger):
    # The App rejects a page with repeated hotel IDs, so the server keeps only the first row of each.
    supplier = Supplier(hotels=[HOTELS[0], dict(HOTELS[0], name='重复行'), HOTELS[1]])
    result = service_for(ledger, supplier).search(
        'owner-a', HotelSearchRequest.model_validate(payload()), lambda: None)
    assert [item['id'] for item in result['items']] == ['B0H1', 'B0H2']
    assert result['items'][0]['name_zh'] == '北京王府井希尔顿酒店'
    assert result['omitted_items'] == 1


def test_daily_limit_refuses_before_any_call_and_leaves_no_intent(ledger, monkeypatch):
    from cj_usage import hotel_budget

    monkeypatch.setattr(hotel_budget, 'DAILY_SEARCH_LIMIT', 0)
    supplier = Supplier()
    with pytest.raises(PluginError) as limit:
        service_for(ledger, supplier).search('owner-a', HotelSearchRequest.model_validate(payload()), lambda: None)
    assert (limit.value.status, limit.value.code) == (429, 'quota_exceeded') and supplier.calls == []
    with ledger.connect() as db:
        assert db.execute("SELECT count(*) FROM attempt WHERE id GLOB 'amap-hotel.1:*'").fetchone()[0] == 0


def test_english_names_use_the_existing_translation_relay_and_fail_soft(ledger):
    seen = []

    def translator(token, text):
        seen.append((token, text))
        lines = text.split('\n')
        return '\n'.join(f'[{n}] Hotel {n}' for n in range(1, len(lines) + 1))

    service = service_for(ledger, Supplier(hotels=HOTELS[:1]), translator=translator)
    result = service.search('owner-a', HotelSearchRequest.model_validate(payload()), lambda: None,
                            token='bearer-fixture')
    assert result['items'][0]['name_en'] == 'Hotel 1' and result['items'][0]['address_en'] == 'Hotel 2'
    assert seen == [('bearer-fixture', '[1] 北京王府井希尔顿酒店\n[2] 王府井东街8号')]

    broken = service_for(ledger, Supplier(hotels=HOTELS[:1]), translator=lambda token, text: 'nonsense')
    plain = broken.search('owner-b', HotelSearchRequest.model_validate(payload()), lambda: None, token='t')
    assert 'name_en' not in plain['items'][0]


def test_short_cache_saves_supplier_calls_but_mints_fresh_handles(ledger):
    supplier = Supplier()
    service = service_for(ledger, supplier)
    first = service.search('owner-a', HotelSearchRequest.model_validate(payload()), lambda: None)
    second = service.search('owner-b', HotelSearchRequest.model_validate(payload(guests=3)), lambda: None)
    assert len(supplier.calls) == 3
    assert [item['id'] for item in first['items']] == [item['id'] for item in second['items']]
    assert first['items'][0]['booking_url'] != second['items'][0]['booking_url']


# --- hand-off ------------------------------------------------------------------------------------------------

def test_handoff_target_is_a_fixed_trip_com_search_page():
    url = handoff_target('北京王府井希尔顿酒店', '北京', '2026-12-03', '2026-12-05', 2, 'en')
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == ('https', 'www.trip.com', '/hotels/list')
    query = parse_qs(parts.query)
    assert query == {'cityId': ['1'], 'searchWord': ['北京王府井希尔顿酒店'], 'checkin': ['2026-12-03'],
                     'checkout': ['2026-12-05'], 'crn': ['1'], 'adult': ['2'], 'curr': ['CNY'],
                     'locale': ['en-US']}
    # No affiliate ID until JT hands over the Trip.com credentials (#1368).
    assert 'allianceid' not in url.lower() and 'sid=' not in url.lower()
    assert parse_qs(urlsplit(handoff_target('x', '上海市', '2026-12-03', '2026-12-04', 1, 'zh')).query)['cityId'] == ['2']
    unknown = urlsplit(handoff_target('客栈', '某县', '2026-12-03', '2026-12-04', 1, 'en'))
    assert (unknown.netloc, unknown.path, unknown.query) == ('www.trip.com', '/hotels/', '')
    assert TRIP_CITY_IDS['北京'] == 1 and TRIP_CITY_IDS['广州'] == 32 and TRIP_CITY_IDS['深圳'] == 30


def test_handoff_store_is_opaque_bounded_and_expires():
    now = [0.0]
    store = HandoffStore(capacity=2, ttl_seconds=10, clock=lambda: now[0])
    first = store.put('https://www.trip.com/hotels/list?cityId=1')
    assert len(first) == 22 and set(first) <= set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_')
    assert store.get(first) == 'https://www.trip.com/hotels/list?cityId=1'
    second = store.put('https://www.trip.com/hotels/')
    store.put('https://www.trip.com/hotels/')
    assert store.get(first) is None and store.get(second) is not None  # oldest evicted at capacity
    now[0] = 11
    assert store.get(second) is None  # expired
    assert store.get('../../etc') is None and store.get('') is None
    with pytest.raises(ValueError):
        store.put('https://evil.example/')


# --- budget --------------------------------------------------------------------------------------------------

def test_fifty_searches_per_account_per_day_counted_by_request(ledger, monkeypatch):
    from cj_usage import hotel_budget

    monkeypatch.setattr(hotel_budget, 'DAILY_SEARCH_LIMIT', 2)
    service = service_for(ledger)
    for _ in range(2):
        service.search('owner-a', HotelSearchRequest.model_validate(payload(near=dict(query=str(uuid4())))),
                       lambda: None)
    with pytest.raises(PluginError) as limit:
        service.search('owner-a', HotelSearchRequest.model_validate(payload(near=dict(query='另一处'))), lambda: None)
    assert (limit.value.status, limit.value.code) == (429, 'quota_exceeded')
    service.search('owner-b', HotelSearchRequest.model_validate(payload(near=dict(query='另一处'))), lambda: None)
    # The day turns over in Shanghai time.
    tomorrow = ledger.clock() + timedelta(days=1)
    ledger.clock = lambda: tomorrow
    service.search('owner-a', HotelSearchRequest.model_validate(payload(near=dict(query='第三处'))), lambda: None)


def test_one_request_never_calls_gaode_twice_for_the_same_step(ledger):
    budget = HotelBudget(ledger)
    request_id = uuid4()
    budget.begin('owner', request_id, 'geocode')
    with pytest.raises(BudgetUnknown):
        budget.begin('owner', request_id, 'geocode')
    with pytest.raises(BudgetUnknown):
        budget.begin('owner', request_id, 'not-an-operation')
    budget.begin('owner', request_id, 'hotels_around')
    budget.begin('owner', request_id, 'subway')
    with pytest.raises(BudgetUnknown):
        budget.begin('owner', request_id, 'hotels_text')  # a fourth Gaode call for one search


def test_hotel_receipts_are_priced_and_counted_apart_from_entry_3(ledger, monkeypatch):
    from cj_usage import hotel_budget

    budget = HotelBudget(ledger)
    attempt = budget.begin('owner', uuid4(), 'subway')
    with ledger.connect() as db:
        counts, estimates, holds = authorization_usage(db)
    assert counts['place'] == 1 and holds['place'] == LIMITS['place'][1] * CNY_SCALE
    budget.finish(attempt, b'original supplier fixture response')
    with ledger.connect() as db:
        counts, estimates, holds = authorization_usage(db)
    assert estimates['place'] == AMAP_PRICE and holds['place'] == 0
    # JT 2026-11-25 (#1534): like Nearby, hotel calls stay out of entry 3's place allowance...
    monkeypatch.setitem(LIMITS, 'place', (1, LIMITS['place'][1]))
    ledger.begin('legacy-first-place', 'place', b'legacy input')
    with pytest.raises(BudgetUnknown, match='call allowance'):
        ledger.begin('legacy-second-place', 'place', b'legacy input')
    budget.begin('owner', uuid4(), 'geocode')  # ...and a full entry 3 allowance does not stop hotel search
    # ...but have their own M4 cap of 3000 calls.
    monkeypatch.setattr(hotel_budget, 'M4_OPERATION_LIMIT', 2)
    with pytest.raises(BudgetUnknown, match='M4'):
        budget.begin('owner', uuid4(), 'geocode')


def test_exhausted_limits_answer_quota_exceeded_and_leave_no_intent(ledger, monkeypatch):
    from cj_usage import hotel_budget

    monkeypatch.setattr(hotel_budget, 'M4_OPERATION_LIMIT', 0)
    supplier = Supplier()
    with pytest.raises(PluginError) as limit:
        service_for(ledger, supplier).search('owner-a', HotelSearchRequest.model_validate(payload()), lambda: None)
    assert (limit.value.status, limit.value.code) == (429, 'quota_exceeded')
    assert supplier.calls == []
    with ledger.connect() as db:
        assert db.execute("SELECT count(*) FROM attempt WHERE id GLOB 'amap-hotel.1:*'").fetchone()[0] == 0


def test_hotel_and_nearby_share_the_tool_cash_ceiling(ledger, monkeypatch):
    from cj_usage import authorization_budget

    monkeypatch.setattr(authorization_budget, 'TOOL_TOTAL_CNY', 2)
    monkeypatch.setattr(authorization_budget, 'TOOL_STOP_CNY', 2)
    from cj_usage import hotel_budget, nearby_budget
    monkeypatch.setattr(hotel_budget, 'TOOL_TOTAL_CNY', 2)
    monkeypatch.setattr(hotel_budget, 'TOOL_STOP_CNY', 2)
    monkeypatch.setattr(nearby_budget, 'TOOL_TOTAL_CNY', 2)
    monkeypatch.setattr(nearby_budget, 'TOOL_STOP_CNY', 2)
    HotelBudget(ledger).begin('owner', uuid4(), 'geocode')
    NearbyBudget(ledger).begin('owner', uuid4(), 'search')
    with pytest.raises(BudgetUnknown):
        HotelBudget(ledger).begin('owner', uuid4(), 'geocode')


def test_nearby_pricing_and_separate_count_are_unchanged(ledger, monkeypatch):
    nearby = NearbyBudget(ledger)
    attempt = nearby.begin('owner', uuid4(), 'search')
    nearby.finish(attempt, b'original supplier fixture response')
    with ledger.connect() as db:
        assert authorization_usage(db)[1]['place'] == AMAP_PRICE
    monkeypatch.setitem(LIMITS, 'place', (1, LIMITS['place'][1]))
    ledger.begin('legacy-first-place', 'place', b'legacy input')  # Nearby still not in the legacy count


def test_service_maps_budget_refusals_to_quota_and_duplicates(ledger):
    service = service_for(ledger)
    request = HotelSearchRequest.model_validate(payload())
    service.search('owner-a', request, lambda: None)
    service.cache.clear()
    with pytest.raises(PluginError) as duplicate:
        service.search('owner-a', request, lambda: None)
    assert (duplicate.value.status, duplicate.value.code) == (409, 'request_already_used')


# --- Gaode provider ------------------------------------------------------------------------------------------

def test_gaode_provider_keeps_nearby_paths_by_default_and_accepts_hotel_operations():
    from cj_usage.hotel_budget import OPERATIONS as HOTEL_OPERATIONS
    from cj_usage.nearby_budget import OPERATIONS as NEARBY_OPERATIONS

    paths = []

    class Transport:
        def __init__(self, host, timeout):
            assert host == 'restapi.amap.com'

        def connect(self):
            pass

        def request(self, method, path, *, headers):
            paths.append(path.split('?')[0])

        def getresponse(self):
            class Response:
                status = 200

                def read(self, limit):
                    return b'{"status":"1","infocode":"10000","pois":[]}'

                def close(self):
                    pass
            return Response()

        def close(self):
            pass

    key = 'local-fixture-key-only'
    GaodeNearby(key, connection=Transport).query('search', {}, lambda: None)
    GaodeNearby(key, connection=Transport, operations=HOTEL_OPERATIONS).query('hotels_text', {}, lambda: None)
    GaodeNearby(key, connection=Transport, operations=HOTEL_OPERATIONS).query('geocode', {}, lambda: None)
    assert paths == [NEARBY_OPERATIONS['search'], '/v5/place/text', '/v3/geocode/geo']
    with pytest.raises(KeyError):  # unchanged: Nearby knows only its own operations
        GaodeNearby(key, connection=Transport).query('hotels_text', {}, lambda: None)


def test_route_constant_matches_the_contract():
    assert ROUTE == '/v1/tools/hotel/search' and HANDOFF_PATH == '/v1/tools/hotel/out/'
