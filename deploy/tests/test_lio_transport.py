"""TRANSPORT.1 (#1520): intercity trains (AMap) and flights (VariFlight) for the Tools tab."""
from contextlib import contextmanager
from datetime import datetime
import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cj_api import lio_transport
from cj_api.lio_transport import AmapRail, ROUTE, TotalCalls, TransportService, register_transport
from cj_api.plugin_tools import PluginCalls, SHANGHAI
from cj_api.variflight_tools import ROUTE as FLIGHTS, VariFlight, register_flights
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal
from deploy.hk import travel_runtime


AMAP_KEY = 'offlineamapkey0123456789'
FLIGHT_KEY = 'offline-provider-key'
HEADERS = {'Authorization': 'Bearer fixture-token'}
BODY = dict(version='TRANSPORT.1', origin='shanghai', destination='beijing', date='2026-12-03',
            modes=['rail', 'flight'])
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


def amap_reply(*rails, status='1', infocode='10000'):
    transits = [dict(duration='18000', segments=[dict(walking={}, bus={}, railway=rail)]) for rail in rails]
    return dict(status=status, infocode=infocode, count=str(len(transits)),
                route=dict(origin='121.473701,31.230416', destination='116.407526,39.904030', transits=transits))


DEFAULT_RAILS = (
    railway('G2', '上海虹桥', '北京南', '0800', '1228', (('O', '626.0'), ('M', '1006.0'), ('XX', '1.0'))),
    railway('G2', '上海虹桥', '北京南', '0800', '1228'),
    railway('D312', '上海', '北京', '19:45', '07:36', (('O', '309.5'),)),
)


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
]


def make_client(tmp_path, *, amap=None, flights=None, total=1500, calls=None, extra=None):
    rail = AmapRail(AMAP_KEY, client=fixture_transport(amap)) if amap else None
    flight = VariFlight(FLIGHT_KEY, client=fixture_transport(flights)) if callable(flights) else flights
    service = TransportService(rail=rail, flights=flight,
                               total=TotalCalls(tmp_path / 'transport-total.sqlite', limit=total))
    calls = calls or PluginCalls(tmp_path / 'calls.sqlite', clock=lambda: TODAY)
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
    seen = []
    with make_client(tmp_path, amap=lambda http: seen.append(http) or httpx.Response(500)) as client:
        outside = client.post(ROUTE, json=BODY, headers={'Authorization': 'Bearer outside'})
        assert outside.status_code == 403 and seen == []


@pytest.mark.parametrize('change', [
    dict(origin='hongkong'), dict(destination='shanghai'), dict(date='2026-11-24'), dict(date='2027-02-01'),
    dict(date='2026-12-3'), dict(modes=[]), dict(modes=['rail', 'rail']), dict(modes=['bus']),
    dict(locale='en'), dict(version='TRANSPORT.2'),
])
def test_invalid_requests_never_reach_providers(tmp_path, change):
    seen = []
    with make_client(tmp_path, amap=lambda http: seen.append(http) or httpx.Response(500)) as client:
        response = client.post(ROUTE, json=dict(BODY, **change), headers=HEADERS)
    assert response.status_code == 400 and response.json() == {'error': 'invalid_request'} and seen == []


def test_rail_projects_amap_trains_without_inventing_seats(tmp_path):
    seen = []

    def amap(http):
        seen.append(http)
        return httpx.Response(200, json=amap_reply(*DEFAULT_RAILS))

    with make_client(tmp_path, amap=amap) as client:
        response = client.post(ROUTE, json=dict(BODY, modes=['rail']), headers=HEADERS)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    request, = seen
    assert request.url.host == 'restapi.amap.com' and request.url.path == '/v3/direction/transit/integrated'
    params = dict(request.url.params)
    assert params['city'] == '上海' and params['cityd'] == '北京' and params['date'] == '2026-12-03'
    assert params['key'] == AMAP_KEY and set(params) >= {'origin', 'destination'}
    body = response.json()
    assert body['version'] == 'TRANSPORT.1' and 'flight' not in body
    assert AMAP_KEY not in response.text
    rail = body['rail']
    assert rail['status'] == 'ok' and rail['source'] == 'AMap'
    assert rail['items'] == [
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
    assert rail['availability_note_zh'] == '余票以 12306 为准'
    assert {link['provider'] for link in body['links']} == {'12306', 'trip.com'}
    assert 'https://www.trip.com/trains/china/route/shanghai-to-beijing/' in {link['url'] for link in body['links']}


@pytest.mark.parametrize('reply', [
    httpx.Response(500), httpx.Response(200, json=amap_reply(status='0', infocode='10003')),
    httpx.Response(200, json=amap_reply(railway('G2', AMAP_KEY, '北京南', '0800', '1228'))),
    httpx.Response(200, text='not json'),
])
def test_rail_failure_only_affects_rail(tmp_path, reply):
    events = []
    with make_client(tmp_path, amap=lambda http: reply, flights=flight_reply(DEFAULT_FLIGHTS, events)) as client:
        response = client.post(ROUTE, json=BODY, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body['rail'] == dict(status='unavailable', source='AMap', items=[],
                                availability_note_zh='余票以 12306 为准',
                                availability_note_en='Seats left: check on 12306')
    assert body['flight']['status'] == 'ok' and AMAP_KEY not in response.text


def test_rail_daily_and_total_caps_are_enforced_before_dispatch(tmp_path):
    seen = []

    def amap(http):
        seen.append(http)
        return httpx.Response(200, json=amap_reply(*DEFAULT_RAILS))

    with make_client(tmp_path, amap=amap) as client:
        for _ in range(30):
            assert client.post(ROUTE, json=dict(BODY, modes=['rail']), headers=HEADERS).json()['rail']['status'] == 'ok'
        capped = client.post(ROUTE, json=dict(BODY, modes=['rail']), headers=HEADERS).json()
    assert capped['rail']['status'] == 'quota_exceeded' and len(seen) == 30

    seen.clear()
    (tmp_path / 'total').mkdir()
    with make_client(tmp_path / 'total', amap=amap, total=2) as client:
        statuses = [client.post(ROUTE, json=dict(BODY, modes=['rail']), headers=HEADERS).json()['rail']['status']
                    for _ in range(3)]
    assert statuses == ['ok', 'ok', 'quota_exceeded'] and len(seen) == 2


def test_flights_share_the_flights_plugin_daily_count(tmp_path):
    events = []
    reply = flight_reply(DEFAULT_FLIGHTS, events)

    def also_flights(app, calls):
        register_flights(app, service=VariFlight(FLIGHT_KEY, client=fixture_transport(reply)), checker=Checker(),
                         internal=frozenset({'inside'}), calls=calls)

    with make_client(tmp_path, flights=reply, extra=also_flights) as client:
        first = client.post(ROUTE, json=dict(BODY, modes=['flight']), headers=HEADERS).json()
        flight = first['flight']
        assert flight['status'] == 'ok' and flight['source'] == 'VariFlight'
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
            assert client.post(FLIGHTS, json=dict(version='FLIGHTS.1', date='2026-12-03', departure='SHA',
                                                    arrival='PEK'), headers=HEADERS).status_code == 200
        assert client.post(FLIGHTS, json=dict(version='FLIGHTS.1', date='2026-12-03', departure='SHA',
                                               arrival='PEK'), headers=HEADERS).status_code == 429
        assert client.post(ROUTE, json=dict(BODY, modes=['flight']), headers=HEADERS).json()['flight']['status'] == \
            'quota_exceeded'


def test_flight_payment_hold_stops_flights_and_keeps_rail(tmp_path, monkeypatch):
    monkeypatch.setattr(travel_runtime, 'authorization', lambda: None)
    events = []
    hold = tmp_path / 'flights.payment-hold'
    guarded = travel_runtime.GuardedTravel(VariFlight(FLIGHT_KEY, client=fixture_transport(
        flight_reply(DEFAULT_FLIGHTS, events, status=402))), hold)
    amap = lambda http: httpx.Response(200, json=amap_reply(*DEFAULT_RAILS))
    with make_client(tmp_path, amap=amap, flights=guarded) as client:
        for _ in range(2):
            body = client.post(ROUTE, json=BODY, headers=HEADERS).json()
            assert body['flight'] == dict(status='not_enabled', source='VariFlight', items=[],
                                          price_note_zh='价格随时变动，以订票页为准',
                                          price_note_en='Prices change often; check when booking')
            assert body['rail']['status'] == 'ok' and 'recharge' not in json.dumps(body)
    assert hold.exists() and len(events) == 1


def test_unconfigured_mode_is_reported_not_guessed(tmp_path):
    with make_client(tmp_path, amap=lambda http: httpx.Response(200, json=amap_reply(*DEFAULT_RAILS))) as client:
        body = client.post(ROUTE, json=BODY, headers=HEADERS).json()
    assert body['rail']['status'] == 'ok'
    assert body['flight']['status'] == 'not_enabled' and body['flight']['items'] == []
    flight_link, = [link for link in body['links'] if link['mode'] == 'flight']
    assert flight_link['url'] == ('https://www.trip.com/flights/showfarefirst?dcity=sha&acity=bjs'
                                  '&ddate=2026-12-03&triptype=ow&class=y&quantity=1')
