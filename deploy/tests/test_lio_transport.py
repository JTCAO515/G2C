"""TRANSPORT.1 (#1520): intercity trains (AMap via the worker relay) and flights (VariFlight) for the Tools tab."""
from contextlib import contextmanager
from datetime import datetime
import json
from uuid import UUID

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cj_api import lio_transport
from cj_api.lio_transport import ROUTE, TransportService, rail_items, register_transport
from cj_api.plugin_tools import PluginCalls, PluginError, SHANGHAI
from cj_api.variflight_tools import ROUTE as FLIGHTS, VariFlight, register_flights
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal
from deploy.hk import travel_runtime


FLIGHT_KEY = 'offline-provider-key'
HEADERS = {'Authorization': 'Bearer fixture-token'}
BODY = dict(version='TRANSPORT.1', origin='shanghai', destination='beijing', date='2026-12-03',
            modes=['rail', 'flight'])
FLIGHT_BODY = dict(version='FLIGHTS.1', date='2026-12-03', departure='SHA', arrival='PEK')
TODAY = datetime(2026, 11, 25, 9, tzinfo=SHANGHAI)


class Checker:
    def check(self, token):
        subject = 'inside' if token == 'fixture-token' else 'outside'
        return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED,
                                 TrustedPrincipal('issuer', subject, 'app', 1, 1, 2))


def fixture_transport(handler):
    @contextmanager
    def client():
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as connection:
            yield connection
    return client


def railway(trip, dep, arr, depart, arrive, spaces=()):
    return dict(id='rail-' + trip, trip=trip, name=trip + '(上海虹桥-北京南)', type='高速列车', time='16080',
                departure_stop=dict(id='d', name=dep, location='121.320,31.194', adcode='310112', time=depart),
                arrival_stop=dict(id='a', name=arr, location='116.378,39.865', adcode='110106', time=arrive),
                spaces=[dict(code=code, cost=cost) for code, cost in spaces])


def amap_reply(*rails):
    transits = [dict(duration='18000', segments=[dict(walking={}, bus={}, railway=rail)]) for rail in rails]
    return dict(status='1', infocode='10000', count=str(len(transits)),
                route=dict(origin='121.473701,31.230416', destination='116.407526,39.904030', transits=transits))


DEFAULT_RAILS = (
    railway('G2', '上海虹桥', '北京南', '0800', '1228', (('O', '626.0'), ('M', '1006.0'), ('XX', '1.0'))),
    railway('G2', '上海虹桥', '北京南', '0800', '1228'),
    railway('D312', '上海', '北京', '19:45', '07:36', (('O', '309.5'), ('M', '12.345'), ('9', 'free'))),
)
TRAINS = [
    dict(number='G2', depart_station=dict(name_zh='上海虹桥站', name_en='Shanghai Hongqiao Railway Station'),
         arrive_station=dict(name_zh='北京南站', name_en='Beijing South Railway Station'),
         depart_time='08:00', arrive_time='12:28', duration_min=268, next_day=False,
         seats=[dict(class_zh='二等座', class_en='Second class', price_cny_minor=62600),
                dict(class_zh='一等座', class_en='First class', price_cny_minor=100600)],
         availability=None),
    dict(number='D312', depart_station=dict(name_zh='上海站', name_en='Shanghai Railway Station'),
         arrive_station=dict(name_zh='北京站', name_en='Beijing Railway Station'),
         depart_time='19:45', arrive_time='07:36', duration_min=711, next_day=True,
         seats=[dict(class_zh='二等座', class_en='Second class', price_cny_minor=30950)], availability=None),
]


class FakeRail:
    """Stands in for the worker relay client (deploy/hk, S line)."""

    def __init__(self, outcome=None):
        self.outcome = TRAINS if outcome is None else outcome
        self.calls = []

    def trains(self, token, request_id, origin, destination, day):
        self.calls.append((token, request_id, origin, destination, day))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def flight_reply(rows, events=None, status=200):
    def reply(http):
        call = json.loads(http.content)
        if events is not None:
            events.append(call.get('params', {}).get('arguments') or call['method'])
        if status != 200:
            return httpx.Response(status, text='recharge the provider account')
        if call['method'] == 'initialize':
            return httpx.Response(200, json=dict(jsonrpc='2.0', id=1, result={'protocolVersion': '2025-06-18'}))
        if call['method'] == 'notifications/initialized':
            return httpx.Response(202)
        assert call['params']['name'] == 'getFlightList'
        arguments = call['params']['arguments']
        matching = [row for row in rows if (row['dep'], row['arr']) == (arguments['dep'], arguments['arr'])]
        return httpx.Response(200, json=dict(jsonrpc='2.0', id=2, result={'structuredContent': {'flights': matching}}))
    return reply


DEFAULT_FLIGHTS = [
    dict(flightNo='MU5101', dep='SHA', arr='PEK', flightDeptimePlan='2026-12-03 07:30:00',
         flightArrtimePlan='2026-12-03 09:40:00', airlineNameZh='东方航空', airlineNameEn='China Eastern'),
    dict(flightNo='CA1858', dep='PVG', arr='PKX', flightDeptimePlan='2026-12-03 13:05:00',
         flightArrtimePlan='2026-12-03 15:25:00'),
    dict(flightNo='HO1251', dep='SHA', arr='PEK', flightDeptimePlan='broken', flightArrtimePlan='2026-12-03 12:00:00'),
    dict(flightNo='MU5199', dep='SHA', arr='PEK', flightDeptimePlan='2026-12-04 07:30:00',
         flightArrtimePlan='2026-12-04 09:40:00'),
]


def make_client(tmp_path, *, rail=None, flights=None, extra=None):
    flight = VariFlight(FLIGHT_KEY, client=fixture_transport(flights)) if callable(flights) else flights
    service = TransportService(rail=rail, flights=flight)
    calls = PluginCalls(tmp_path / 'calls.sqlite', clock=lambda: TODAY)
    app = FastAPI()
    register_transport(app, service=service, checker=Checker(), internal=frozenset({'inside'}), calls=calls)
    if extra:
        extra(app, calls)
    return TestClient(app)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(lio_transport, 'today', lambda: TODAY.date())


def test_closed_by_default_and_internal_testers_only(tmp_path):
    app = FastAPI()
    register_transport(app)
    with TestClient(app) as client:
        assert client.post(ROUTE, json=BODY, headers=HEADERS).json() == {'error': 'not_enabled'}
        assert client.post(ROUTE, json=BODY).status_code == 401
    rail = FakeRail()
    with make_client(tmp_path, rail=rail) as client:
        outside = client.post(ROUTE, json=BODY, headers={'Authorization': 'Bearer outside'})
        assert outside.status_code == 403 and rail.calls == []


@pytest.mark.parametrize('change', [
    dict(origin='hongkong'), dict(destination='shanghai'), dict(date='2026-11-24'), dict(date='2027-02-01'),
    dict(date='2026-12-3'), dict(modes=[]), dict(modes=['rail', 'rail']), dict(modes=['bus']),
    dict(locale='en'), dict(version='TRANSPORT.2'),
])
def test_invalid_requests_never_reach_providers(tmp_path, change):
    rail = FakeRail()
    with make_client(tmp_path, rail=rail) as client:
        response = client.post(ROUTE, json=dict(BODY, **change), headers=HEADERS)
    assert response.status_code == 400 and response.json() == {'error': 'invalid_request'} and rail.calls == []


def test_rail_goes_through_the_worker_relay_with_the_callers_own_bearer(tmp_path):
    rail = FakeRail()
    with make_client(tmp_path, rail=rail) as client:
        first = client.post(ROUTE, json=dict(BODY, modes=['rail']), headers=HEADERS)
        client.post(ROUTE, json=dict(BODY, modes=['rail']), headers=HEADERS)
    assert first.status_code == 200 and first.headers['cache-control'] == 'no-store'
    (token, request_id, origin, destination, day), second = rail.calls
    assert (token, origin, destination, day) == ('fixture-token', 'shanghai', 'beijing', '2026-12-03')
    assert UUID(request_id).version == 4 and second[1] != request_id
    body = first.json()
    assert body['version'] == 'TRANSPORT.1' and 'flight' not in body
    assert body['rail'] == dict(status='ok', source='AMap', items=TRAINS,
                                availability_note_zh='余票以 12306 为准',
                                availability_note_en='Seats left: check on 12306')
    assert [(link['provider'], link['url']) for link in body['links']] == [
        ('12306', 'https://www.12306.cn/en/index.html'),
        ('trip.com', 'https://www.trip.com/trains/china/route/shanghai-to-beijing/')]


def test_non_rail_segments_with_an_empty_railway_object_are_skipped():
    # Real AMap cross-city replies often carry "railway": {"alters": [], "spaces": []} on walking/metro segments.
    reply = amap_reply(*DEFAULT_RAILS)
    for transit in reply['route']['transits']:
        transit['segments'].insert(0, dict(walking={'distance': '300'}, bus={}, railway=dict(alters=[], spaces=[])))
        transit['segments'].append(dict(walking={}, bus={}, railway=dict(alters=[], spaces=[], trip='')))
    assert rail_items(reply) == TRAINS


def test_station_names_with_unpaired_surrogates_are_rejected():
    with pytest.raises(ValueError):
        rail_items(amap_reply(railway('G2', '上海\ud800虹桥', '北京南', '0800', '1228')))


def test_rail_projection_keeps_only_known_seats_and_never_claims_availability():
    assert rail_items(amap_reply(*DEFAULT_RAILS)) == TRAINS
    assert rail_items(amap_reply()) == []
    for broken in (railway('G2; DROP', '上海虹桥', '北京南', '0800', '1228'),
                   railway('G2', '上海虹桥', '北京南', '25:00', '1228'),
                   railway('G2', '', '北京南', '0800', '1228'),
                   railway('G2', '上海\u0085虹桥', '北京南', '0800', '1228')):
        with pytest.raises(ValueError):
            rail_items(amap_reply(broken))
    with pytest.raises(ValueError):
        rail_items(dict(status='1', route=dict(transits=[{}] * 33)))
    with pytest.raises(ValueError):
        rail_items([])


@pytest.mark.parametrize(('outcome', 'status'), [
    (PluginError(502, 'supplier_unavailable'), 'unavailable'), (PluginError(504, 'supplier_timeout'), 'unavailable'),
    (PluginError(429, 'rate_limited'), 'unavailable'), (OSError('socket'), 'unavailable'),
    (ValueError('reply'), 'unavailable'), (PluginError(429, 'quota_exceeded'), 'quota_exceeded'),
    (PluginError(503, 'not_enabled'), 'not_enabled'), ([], 'empty'),
])
def test_rail_outcomes_only_affect_rail(tmp_path, outcome, status):
    with make_client(tmp_path, rail=FakeRail(outcome), flights=flight_reply(DEFAULT_FLIGHTS)) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body['rail']['status'] == status and body['rail']['items'] == []
    assert body['flight']['status'] == 'ok'


def test_a_changed_sign_in_fails_the_whole_request(tmp_path):
    with make_client(tmp_path, rail=FakeRail(PluginError(401, 'sign_in_required'))) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 401 and response.json() == {'error': 'sign_in_required'}


def test_flights_share_the_flights_plugin_daily_count(tmp_path):
    events = []
    reply = flight_reply(DEFAULT_FLIGHTS, events)

    def also_flights(app, calls):
        register_flights(app, service=VariFlight(FLIGHT_KEY, client=fixture_transport(reply)), checker=Checker(),
                         internal=frozenset({'inside'}), calls=calls)

    with make_client(tmp_path, flights=reply, extra=also_flights) as client:
        flight = client.post(ROUTE, json=dict(BODY, modes=['flight']), headers=HEADERS).json()['flight']
        assert flight['status'] == 'ok' and flight['source'] == 'VariFlight'
        assert flight['price_note_zh'] == '价格随时变动，以订票页为准'
        assert flight['items'] == [
            dict(number='MU5101', carrier=dict(name_zh='东方航空', name_en='China Eastern'),
                 depart_airport=dict(iata='SHA', name_zh='上海虹桥国际机场', name_en='Shanghai Hongqiao International Airport'),
                 arrive_airport=dict(iata='PEK', name_zh='北京首都国际机场', name_en='Beijing Capital International Airport'),
                 depart_time='07:30', arrive_time='09:40', duration_min=130, next_day=False),
            dict(number='CA1858',
                 depart_airport=dict(iata='PVG', name_zh='上海浦东国际机场', name_en='Shanghai Pudong International Airport'),
                 arrive_airport=dict(iata='PKX', name_zh='北京大兴国际机场', name_en='Beijing Daxing International Airport'),
                 depart_time='13:05', arrive_time='15:25', duration_min=140, next_day=False),
        ]
        assert sorted(arguments['dep'] + arguments['arr'] for arguments in events if type(arguments) is dict) == [
            'PVGPEK', 'PVGPKX', 'SHAPEK', 'SHAPKX']
        for _ in range(49):
            assert client.post(FLIGHTS, json=FLIGHT_BODY, headers=HEADERS).status_code == 200
        assert client.post(FLIGHTS, json=FLIGHT_BODY, headers=HEADERS).status_code == 429
        assert client.post(ROUTE, json=dict(BODY, modes=['flight']), headers=HEADERS).json()['flight']['status'] == \
            'quota_exceeded'


def test_payment_hold_from_transport_stops_the_flights_route_too(tmp_path, monkeypatch):
    monkeypatch.setattr(travel_runtime, 'authorization', lambda: None)
    events = []
    hold = tmp_path / 'flights.payment-hold'
    reply = flight_reply(DEFAULT_FLIGHTS, events, status=402)
    transport_side = travel_runtime.GuardedTravel(VariFlight(FLIGHT_KEY, client=fixture_transport(reply)), hold)
    flights_side = travel_runtime.GuardedTravel(VariFlight(FLIGHT_KEY, client=fixture_transport(reply)), hold)

    def also_flights(app, calls):
        register_flights(app, service=flights_side, checker=Checker(), internal=frozenset({'inside'}), calls=calls)

    with make_client(tmp_path, rail=FakeRail(), flights=transport_side, extra=also_flights) as client:
        for _ in range(2):
            body = client.post(ROUTE, json=BODY, headers=HEADERS).json()
            assert body['flight'] == dict(status='not_enabled', source='VariFlight', items=[],
                                          price_note_zh='价格随时变动，以订票页为准',
                                          price_note_en='Prices change often; check when booking')
            assert body['rail']['status'] == 'ok' and 'recharge' not in json.dumps(body)
        blocked = client.post(FLIGHTS, json=FLIGHT_BODY, headers=HEADERS)
        assert blocked.status_code == 503 and blocked.json() == {'error': 'not_enabled'}
    assert hold.exists() and len(events) == 1


def test_unconfigured_modes_are_reported_not_guessed(tmp_path):
    with make_client(tmp_path) as client:
        body = client.post(ROUTE, json=BODY, headers=HEADERS).json()
    assert body['rail']['status'] == 'not_enabled' and body['rail']['items'] == []
    assert body['flight']['status'] == 'not_enabled' and body['flight']['items'] == []
    flight_link, = [link for link in body['links'] if link['mode'] == 'flight']
    assert flight_link == dict(mode='flight', provider='trip.com', url=(
        'https://www.trip.com/flights/showfarefirst?dcity=sha&acity=bjs&ddate=2026-12-03&triptype=ow&class=y&quantity=1'))
