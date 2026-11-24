from contextlib import contextmanager
from datetime import datetime
import json
import os

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cj_api.plugin_tools import PluginCalls, SHANGHAI
from cj_api.qweather_tools import QWeather, ROUTE as WEATHER, register_weather
from cj_api.variflight_tools import VariFlight, ROUTE as FLIGHTS, register_flights
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal
from deploy.hk import travel_runtime
from deploy.hk.travel_provider_credentials import install


KEY = 'offline-provider-key'
WEATHER_BODY = dict(version='WEATHER.1', kind='current', language='en', city='beijing')
FLIGHT_BODY = dict(version='FLIGHTS.1', date='2026-11-24', flight_number='MU5102')
HEADERS = {'Authorization': 'Bearer fixture-token'}
OBSERVATION = {
    'metadata': {'attributions': ['https://developer.qweather.com/attribution.html']},
    'validTime': '2026-11-24T10:10+08:00',
    'condition': {'text': 'Few Clouds', 'code': '102'},
    'temperature': {'value': 14.2, 'unit': '°C'},
    'humidity': 0.69,
}


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


def route_client(tmp_path, register, service):
    app = FastAPI()
    register(app, service=service, checker=Checker(), internal=frozenset({'inside'}),
             calls=PluginCalls(tmp_path / 'calls.sqlite', clock=lambda: datetime(2026, 11, 24, tzinfo=SHANGHAI)))
    return TestClient(app)


def test_weather_signed_internal_city_cache_and_daily_limit(tmp_path):
    seen = []

    def reply(http):
        seen.append(http.url)
        assert http.url.host == 'example.yun.qweatherapi.com'
        assert http.url.path == '/weather/v1/current/39.90/116.41'
        assert dict(http.url.params) == {'lang': 'en', 'localTime': 'true'}
        assert http.headers['x-qw-api-key'] == KEY
        assert 'fixture-token' not in str(http.url)
        return httpx.Response(200, json=OBSERVATION)

    provider = QWeather('example.yun.qweatherapi.com', KEY, client=fixture_transport(reply))
    with route_client(tmp_path, register_weather, provider) as client:
        outside = client.post(WEATHER, json=WEATHER_BODY, headers={'Authorization': 'Bearer outside'})
        assert outside.status_code == 403 and seen == []
        assert client.post(WEATHER, json=dict(WEATHER_BODY, lat=1, lng=1), headers=HEADERS).status_code == 400
        first = client.post(WEATHER, json=WEATHER_BODY, headers=HEADERS)
        assert first.status_code == 200 and first.json()['items'][0]['humidity_percent'] == 69
        for _ in range(199):
            assert client.post(WEATHER, json=WEATHER_BODY, headers=HEADERS).json() == first.json()
        assert client.post(WEATHER, json=WEATHER_BODY, headers=HEADERS).status_code == 429
    assert len(seen) == 1


@pytest.mark.parametrize(('kind', 'route', 'data'), [
    ('hourly', 'weather/v1/hourly', dict(hours=[dict(OBSERVATION, forecastTime='2026-11-24T11:00+08:00')])),
    ('daily', 'weather/v1/daily', dict(days=[dict(forecastStartTime='2026-11-24T07:00+08:00',
          temperatureMin=dict(value=3, unit='°C'), temperatureMax=dict(value=12, unit='°C'),
          daytime=dict(condition=dict(text='Sunny')))])),
    ('alerts', 'weatheralert/v1/current', dict(alerts=[dict(id='alert-1', headline='Strong wind',
          description='Test official alert', senderName='Test Authority', issuedTime='2026-11-24T10:00+08:00')])),
])
def test_weather_projections(tmp_path, kind, route, data):
    def reply(http):
        assert http.url.path.startswith('/' + route)
        return httpx.Response(200, json=dict(data, metadata=OBSERVATION['metadata']))

    service = QWeather('example.qweatherapi.com', KEY, client=fixture_transport(reply))
    with route_client(tmp_path, register_weather, service) as client:
        result = client.post(WEATHER, json=dict(WEATHER_BODY, kind=kind), headers=HEADERS)
    assert result.status_code == 200 and len(result.json()['items']) == 1
    if kind == 'alerts':
        assert result.json()['items'][0]['sender'] == 'Test Authority'


def test_flights_caches_fixed_read_only_tool_and_enforces_limit(tmp_path):
    events = []

    def reply(http):
        assert str(http.url) == 'https://c-gw.variflight.com/chat_message/mcp/api'
        assert http.headers['authorization'] == 'Bearer ' + KEY
        call = json.loads(http.content)
        events.append(call['method'])
        if call['method'] == 'initialize':
            value = {'protocolVersion': '2025-06-18'}
            return httpx.Response(200, json=dict(jsonrpc='2.0', id=1, result=value),
                                  headers={'Mcp-Session-Id': 'fixture-session'})
        assert http.headers['mcp-session-id'] == 'fixture-session'
        if call['method'] == 'notifications/initialized':
            return httpx.Response(202)
        assert call['method'] == 'tools/call'
        assert call['params'] == {'name': 'getFlightStatus', 'arguments': {'fnum': 'MU5102', 'date': '2026-11-24'}}
        result = {'structuredContent': {'flights': [{'flightNo': 'MU5102', 'gate': 'B2', 'dep': 'SHA'}]}}
        body = 'event: message\r\ndata: ' + json.dumps(dict(jsonrpc='2.0', id=2, result=result)) + '\r\n\r\n'
        return httpx.Response(200, text=body, headers={'Content-Type': 'text/event-stream'})

    with route_client(tmp_path, register_flights, VariFlight(KEY, client=fixture_transport(reply))) as client:
        assert client.post(FLIGHTS, json=dict(FLIGHT_BODY, date='2026-02-30'), headers=HEADERS).status_code == 400
        for _ in range(50):
            response = client.post(FLIGHTS, json=FLIGHT_BODY, headers=HEADERS)
            assert response.status_code == 200
            assert response.json()['items'] == [{'flight_number': 'MU5102', 'departure': 'SHA', 'gate': 'B2'}]
        assert client.post(FLIGHTS, json=FLIGHT_BODY, headers=HEADERS).status_code == 429
    assert events == ['initialize', 'notifications/initialized', 'tools/call']


def test_provider_payment_hold_survives_restart_and_never_redirects(tmp_path, monkeypatch):
    seen = []

    def reply(http):
        seen.append(http.url.host)
        return httpx.Response(402, text='recharge the provider account')

    monkeypatch.setattr(travel_runtime, 'authorization', lambda: None)
    stop = tmp_path / 'weather.payment-hold'
    for _ in range(2):
        provider = QWeather('example.qweatherapi.com', KEY, client=fixture_transport(reply))
        guard = travel_runtime.GuardedTravel(provider, stop)
        with route_client(tmp_path, register_weather, guard) as client:
            result = client.post(WEATHER, json=WEATHER_BODY, headers=HEADERS)
            assert result.status_code == 503 and 'recharge' not in result.text
    assert seen == ['example.qweatherapi.com']
    assert stop.stat().st_mode & 0o777 == 0o600

    def redirected(http):
        assert http.url.host == 'example.qweatherapi.com'
        return httpx.Response(302, headers={'Location': 'https://elsewhere.invalid/collect'})

    with route_client(tmp_path, register_weather, QWeather('example.qweatherapi.com', KEY, client=fixture_transport(redirected))) as client:
        assert client.post(WEATHER, json=WEATHER_BODY, headers=HEADERS).status_code == 502


@pytest.mark.parametrize('payload', [dict(OBSERVATION, condition=dict(text=KEY)), dict(OBSERVATION, precipitation='broken')])
def test_provider_response_echo_and_invalid_fields_are_rejected(tmp_path, payload):
    def reply(_):
        return httpx.Response(200, json=payload)

    with route_client(tmp_path, register_weather, QWeather('example.qweatherapi.com', KEY, client=fixture_transport(reply))) as client:
        result = client.post(WEATHER, json=WEATHER_BODY, headers=HEADERS)
        assert result.status_code == 502 and KEY not in result.text


def test_optional_credentials_backup_only_one_row_and_fail_closed(tmp_path):
    env = tmp_path / 'api.env'
    before = (b'CJ_SUPABASE_RUNTIME_URI=fixture\nCJ_BETA_CONFIRMATION_B64=fixture\n'
              b'CJ_QWEATHER_KEY=old-weather\nCJ_BETA_HISTORY_B64=fixture\n')
    env.write_bytes(before)
    env.chmod(0o600)
    owner = (os.getuid(), os.getgid())
    install(env, 'CJ_QWEATHER_KEY', b'replacement-weather\n', owner)
    assert env.read_bytes() == before.replace(b'old-weather', b'replacement-weather')
    backup, = tmp_path.glob('api.env.before-travel-*')
    assert backup.read_bytes() == before and backup.stat().st_mode & 0o777 == 0o600
    assert env.stat().st_mode & 0o777 == 0o600
    env.chmod(0o640)
    with pytest.raises(ValueError, match='identity'):
        install(env, 'CJ_VARIFLIGHT_MCP_KEY', b'other-fixture-key\n', owner)
    assert b'CJ_VARIFLIGHT_MCP_KEY' not in env.read_bytes()
    env.chmod(0o600)
    env.write_bytes(before.replace(b'old-weather', 'unusual\u0085separator'.encode()))
    with pytest.raises(ValueError, match='format'):
        install(env, 'CJ_VARIFLIGHT_MCP_KEY', b'other-fixture-key\n', owner)
