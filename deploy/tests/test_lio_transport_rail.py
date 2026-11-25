"""TRANSPORT.1 Part 2 (#1520): worker-side AMap cross-city trains, metered in the HK AMap cash journal.

M4 entry 12 item 4 (JT 2026-11-25, #1518): at most 30 searches per account per day, at most 1500 AMap calls
in all, one call per search; counted apart from entry 3's route allowance and sharing only the ¥500 tool cash.
"""
from datetime import datetime, timedelta
import json
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from cj_api.lio_transport import CITIES
from cj_api.lio_transport_rail import TransitRailService, transit_provider
from cj_api.plugin_tools import PluginError
from cj_usage.authorization_budget import (
    AMAP_PRICE, AuthorizationBudget, CNY_SCALE, LIMITS, _price_receipt, authorization_usage, journal_state,
    shared_tool_services,
)
from cj_usage.hotel_budget import HotelBudget
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.nearby_budget import NearbyBudget
from cj_usage.transit_budget import SERVICE, SHANGHAI, TransitBudget, TransitDuplicate, TransitLimit


DAY = '2026-12-03'
REPLY = dict(status='1', infocode='10000', count='1', route=dict(transits=[dict(duration='18000', segments=[
    dict(walking={}, bus={}, railway=dict(
        trip='G2', departure_stop=dict(name='上海虹桥', time='0800'), arrival_stop=dict(name='北京南', time='1228'),
        spaces=[dict(code='O', cost='626.0')]))])]))


class Supplier:
    def __init__(self, reply=REPLY):
        self.calls = []
        self.reply = reply

    def query(self, operation, params, reserve):
        reserve()
        self.calls.append((operation, params))
        return self.reply, json.dumps(self.reply, ensure_ascii=False).encode()


@pytest.fixture
def ledger(tmp_path):
    return AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 25, 19, tzinfo=SHANGHAI))


def trains(service, scope='owner', request_id=None):
    return service.trains(scope, str(request_id or uuid4()), 'shanghai', 'beijing', DAY, lambda: None)


def test_one_amap_transit_call_per_search_projected_to_trains(ledger):
    supplier = Supplier()
    items = trains(TransitRailService(supplier, TransitBudget(ledger)))
    assert [item['number'] for item in items] == ['G2'] and items[0]['availability'] is None
    (operation, params), = supplier.calls
    assert operation == 'transit'
    assert params['city'] == '上海' and params['cityd'] == '北京' and params['date'] == DAY
    assert params['origin'] == '%.6f,%.6f' % CITIES['shanghai'].centre
    assert params['destination'] == '%.6f,%.6f' % CITIES['beijing'].centre
    assert 'key' not in params


def test_transit_receipts_are_priced_as_route_and_counted_apart_from_entry_3(ledger, monkeypatch):
    budget = TransitBudget(ledger)
    attempt = budget.begin('owner', uuid4(), 'transit')
    with ledger.connect() as db:
        counts, estimates, holds = authorization_usage(db)
    assert counts['route'] == 1 and counts['place'] == 0 and holds['route'] == LIMITS['route'][1] * CNY_SCALE
    budget.finish(attempt, b'original supplier fixture response')
    with ledger.connect() as db:
        counts, estimates, holds = authorization_usage(db)
    assert estimates['route'] == AMAP_PRICE and holds['route'] == 0
    # A full Lio route allowance does not stop trains, and trains never use the Lio route allowance.
    monkeypatch.setitem(LIMITS, 'route', (1, LIMITS['route'][1]))
    ledger.begin('legacy-first-route', 'route', b'legacy input')
    with pytest.raises(BudgetUnknown, match='call allowance'):
        ledger.begin('legacy-second-route', 'route', b'legacy input')
    budget.begin('owner', uuid4(), 'transit')


def test_service_table_carries_the_kind_and_keeps_nearby_and_hotel(ledger):
    services = shared_tool_services()
    assert services['amap-transit.1'] == ('route', 'https://restapi.amap.com',
                                          {'transit': '/v3/direction/transit/integrated'}, True)
    assert services['amap-nearby.1'][0] == 'place' and services['amap-nearby.1'][3] is True
    assert services['amap-hotel.1'][0] == 'place' and services['amap-hotel.1'][3] is True


def test_receipt_of_the_wrong_kind_is_never_priced():
    transit = json.dumps(dict(service=SERVICE, operation='transit', day=DAY,
                              endpoint='https://restapi.amap.com/v3/direction/transit/integrated',
                              response_sha256='0' * 64))
    nearby = json.dumps(dict(service='amap-nearby.1', operation='search', day=DAY,
                             endpoint='https://restapi.amap.com/v5/place/around', response_sha256='0' * 64))
    assert _price_receipt('route', transit) == AMAP_PRICE
    assert _price_receipt('place', transit) is None
    assert _price_receipt('route', nearby) is None
    wrong_path = json.loads(transit) | {'endpoint': 'https://restapi.amap.com/v3/direction/driving'}
    assert _price_receipt('route', json.dumps(wrong_path)) is None


def test_daily_and_m4_caps_refuse_before_dispatch_and_leave_no_intent(ledger, monkeypatch):
    from cj_usage import transit_budget

    budget = TransitBudget(ledger)
    for _ in range(30):
        budget.begin('owner-a', uuid4(), 'transit')
    with pytest.raises(TransitLimit, match='daily'):
        budget.begin('owner-a', uuid4(), 'transit')
    budget.begin('owner-b', uuid4(), 'transit')
    monkeypatch.setattr(transit_budget, 'M4_OPERATION_LIMIT', 31)
    with pytest.raises(TransitLimit, match='M4'):
        budget.begin('owner-c', uuid4(), 'transit')
    with ledger.connect() as db:
        assert db.execute("SELECT count(*) FROM attempt WHERE id GLOB 'amap-transit.1:*'").fetchone()[0] == 31
    # The next Shanghai day is a new day for owner-a, but not a new M4 allowance.
    tomorrow = ledger.clock() + timedelta(days=1)
    ledger.clock = lambda: tomorrow
    with pytest.raises(TransitLimit, match='M4'):
        budget.begin('owner-a', uuid4(), 'transit')


def test_one_request_never_calls_amap_twice(ledger):
    budget = TransitBudget(ledger)
    request_id = uuid4()
    budget.begin('owner', request_id, 'transit')
    with pytest.raises(TransitDuplicate):
        budget.begin('owner', request_id, 'transit')
    with pytest.raises(BudgetUnknown):
        budget.begin('owner', uuid4(), 'not-an-operation')


def test_trains_share_the_tool_cash_ceiling_with_hotel_and_nearby(ledger, monkeypatch):
    from cj_usage import authorization_budget, hotel_budget, nearby_budget, transit_budget

    for module in (authorization_budget, hotel_budget, nearby_budget, transit_budget):
        monkeypatch.setattr(module, 'TOOL_TOTAL_CNY', 3)
        monkeypatch.setattr(module, 'TOOL_STOP_CNY', 3)
    HotelBudget(ledger).begin('owner', uuid4(), 'geocode')
    NearbyBudget(ledger).begin('owner', uuid4(), 'search')
    TransitBudget(ledger).begin('owner', uuid4(), 'transit')
    with pytest.raises(BudgetUnknown):
        TransitBudget(ledger).begin('owner', uuid4(), 'transit')
    with pytest.raises(BudgetUnknown):
        HotelBudget(ledger).begin('owner', uuid4(), 'geocode')


def test_unresolved_transit_attempt_exports_with_the_shared_history(ledger):
    from scripts.m4_budget_transfer import attempts

    budget = TransitBudget(ledger)
    attempt = budget.begin('owner', uuid4(), 'transit')
    with ledger.connect() as db:
        assert attempts(db) == journal_state(db)
    budget.finish(attempt, b'original supplier fixture response')
    with ledger.connect() as db:
        assert attempts(db) == journal_state(db)
        assert authorization_usage(db)[1]['route'] == AMAP_PRICE


@pytest.mark.parametrize(('limit', 'status'), [('daily', (429, 'quota_exceeded')), ('duplicate', (409, 'request_already_used'))])
def test_service_maps_budget_refusals_without_calling_amap(ledger, monkeypatch, limit, status):
    from cj_usage import transit_budget

    supplier = Supplier()
    service = TransitRailService(supplier, TransitBudget(ledger))
    request_id = uuid4()
    if limit == 'daily':
        monkeypatch.setattr(transit_budget, 'DAILY_SEARCH_LIMIT', 0)
    else:
        TransitBudget(ledger).begin('owner', request_id, 'transit')
    with pytest.raises(PluginError) as refused:
        trains(service, request_id=request_id)
    assert (refused.value.status, refused.value.code) == status and supplier.calls == []


def test_unusable_amap_reply_is_a_supplier_failure_not_an_empty_day(ledger):
    broken = dict(REPLY, route=dict(transits=[dict(segments=[dict(railway=dict(trip='G2; DROP'))])]))
    with pytest.raises(PluginError) as failure:
        trains(TransitRailService(Supplier(broken), TransitBudget(ledger)))
    assert (failure.value.status, failure.value.code) == (502, 'supplier_unavailable')
    empty = dict(REPLY, route=dict(transits=[]))
    assert trains(TransitRailService(Supplier(empty), TransitBudget(ledger))) == []


def test_unknown_city_or_day_never_reaches_amap(ledger):
    supplier = Supplier()
    service = TransitRailService(supplier, TransitBudget(ledger))
    for origin, destination, day in (('hongkong', 'beijing', DAY), ('shanghai', 'shanghai', DAY),
                                     ('shanghai', 'beijing', '2026-12-3')):
        with pytest.raises(PluginError) as invalid:
            service.trains('owner', str(uuid4()), origin, destination, day, lambda: None)
        assert invalid.value.status == 400
    with pytest.raises(PluginError):
        service.trains('owner', 'not-a-uuid', 'shanghai', 'beijing', DAY, lambda: None)
    assert supplier.calls == []


class FakeConnection:
    seen = []

    def __init__(self, host, timeout):
        self.host = host

    def connect(self):
        pass

    def request(self, method, path, headers):
        FakeConnection.seen.append((self.host, method, path))

    def getresponse(self):
        body = json.dumps(REPLY, ensure_ascii=False).encode()

        class Response:
            status = 200

            def read(self, size):
                return body

            def close(self):
                pass
        return Response()

    def close(self):
        pass


def test_provider_uses_the_registered_transit_path_and_keeps_the_key_in_the_query(ledger):
    FakeConnection.seen.clear()
    provider = transit_provider('offlineamapkey0123456789', connection=FakeConnection)
    assert trains(TransitRailService(provider, TransitBudget(ledger)))[0]['number'] == 'G2'
    (host, method, path), = FakeConnection.seen
    parsed = urlsplit(path)
    assert (host, method, parsed.path) == ('restapi.amap.com', 'GET', '/v3/direction/transit/integrated')
    query = parse_qs(parsed.query)
    assert query['key'] == ['offlineamapkey0123456789'] and query['cityd'] == ['北京']
