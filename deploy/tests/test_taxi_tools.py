from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cj_api.plugin_tools import PluginCalls, PluginError
from cj_api.taxi_tools import DiDiInformation, ESTIMATE, LINK, TaxiService, register_taxi_routes
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal


AUTH = {'Authorization': 'Bearer internal'}
NOW = datetime(2026, 11, 20, 22, tzinfo=timezone.utc)
FIXTURE_LINK = 'https://taxi.example.invalid/route'


def point(name=None):
    return dict(lat=39.9, lng=116.4, coordinate_system='WGS-84', name=name)


def payload():
    return dict(version='TAXI.1', origin=point('北京西站'), destination=point())


def check(token):
    if token in {'internal', 'internal-other', 'invited-external'}:
        principal = TrustedPrincipal('fixture-issuer', token, 'app', 1, 1, 2)
        return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal)
    return AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.IDENTITY_INVALID)


@pytest.fixture
def app_context(tmp_path):
    seen = []
    path = tmp_path / 'plugin-count.sqlite'

    def transport(tool, params):
        seen.append((tool, params))
        if tool == 'taxi_estimate':
            return {'structuredContent': {'items': [{'productName': '快车', 'productCategory': '1',
                    'priceText': '约 20 元', 'private': 'excluded'}], 'traceId': 'fixture-trace'}}
        return {'structuredContent': {'url': FIXTURE_LINK}}

    def resolve(value, include_name):
        assert value.coordinate_system == 'WGS-84'
        return SimpleNamespace(lat='39.901', lng='116.406', name=value.name or '经核对的公共地点')

    taxi = TaxiService(DiDiInformation(transport), resolve, {FIXTURE_LINK},
                       clock=lambda: NOW)
    app = FastAPI()
    register_taxi_routes(app, taxi=taxi, checker=SimpleNamespace(check=check),
                         internal=frozenset({'internal', 'internal-other'}),
                         calls=PluginCalls(path, clock=lambda: NOW))
    with TestClient(app) as client:
        yield client, seen, path


def test_hong_kong_default_disabled():
    app = FastAPI()
    register_taxi_routes(app)
    with TestClient(app) as client:
        for route in (ESTIMATE, LINK):
            response = client.post(route, headers=AUTH, json=payload())
            assert response.status_code == 403
            assert response.json() == {'error': 'not_enabled'}
            assert response.headers['cache-control'] == 'no-store'


def test_fixture_estimate_and_link_allow_no_identity_fields(app_context):
    client, seen, _ = app_context
    response = client.post(ESTIMATE, headers=AUTH, json=payload())
    assert response.status_code == 200
    assert response.json() == {'version': 'TAXI.1',
                               'vehicles': [{'category': '1', 'name': '快车', 'currency': 'CNY',
                                             'price_display': '约 20 元'}],
                               'trace_id': 'fixture-trace', 'observed_at': NOW.isoformat()}
    response = client.post(LINK, headers=AUTH, json=dict(payload(), vehicle_category='1'))
    assert response.json() == {'version': 'TAXI.1', 'url': FIXTURE_LINK, 'link_type': 'https'}
    assert seen == [
        ('taxi_estimate', dict(from_lat='39.901', from_lng='116.406', to_lat='39.901', to_lng='116.406',
                               from_name='北京西站', to_name='经核对的公共地点')),
        ('taxi_generate_ride_app_link', dict(from_lat='39.901', from_lng='116.406', to_lat='39.901',
                                             to_lng='116.406')),
    ]


@pytest.mark.parametrize('method', ['taxi_create_order', 'taxi_cancel_order', 'taxi_query_order',
                                    'taxi_get_driver_location', 'maps_unknown'])
def test_only_fixed_information_tools_can_be_dispatched(method):
    seen = []
    provider = DiDiInformation(lambda *args: seen.append(args))
    with pytest.raises(ValueError):
        provider.call(method, {})
    assert seen == []


@pytest.mark.parametrize(('headers', 'data', 'status', 'error'), [
    ({}, payload(), 401, 'sign_in_required'),
    ({'Authorization': 'Bearer invented'}, payload(), 401, 'sign_in_required'),
    ({'Authorization': 'Bearer invited-external'}, payload(), 403, 'not_enabled'),
    (AUTH, dict(payload(), subject='internal-other'), 400, 'invalid_request'),
    (AUTH, dict(payload(), origin=dict(point(), coordinate_system='BD-09')), 400, 'invalid_request'),
    (AUTH, dict(payload(), origin=dict(point(), lng=181)), 400, 'invalid_request'),
    (AUTH, dict(payload(), origin=dict(point(), lat=True)), 400, 'invalid_request'),
    (AUTH, dict(payload(), origin=dict(point(), phone='0000000')), 400, 'invalid_request'),
])
def test_auth_and_request_boundary_reject_before_supplier(app_context, headers, data, status, error):
    client, seen, path = app_context
    response = client.post(ESTIMATE, headers=headers, json=data)
    assert response.status_code == status
    assert response.json() == {'error': error}
    assert seen == []
    assert not path.exists()


def test_duplicate_and_oversized_bodies_rejected_without_dispatch(app_context):
    client, seen, path = app_context
    headers = dict(AUTH, **{'Content-Type': 'application/json'})
    raw = json.dumps(payload())[:-1] + ', "version": "TAXI.1"}'
    assert client.post(LINK, headers=headers, content=raw).status_code == 400
    assert client.post(LINK, headers=headers, content=' ' * 4097).status_code == 413
    assert seen == []
    assert not path.exists()


def test_per_account_per_route_quota_precedes_dispatch(app_context):
    client, seen, _ = app_context
    for _ in range(50):
        assert client.post(ESTIMATE, headers=AUTH, json=payload()).status_code == 200
    response = client.post(ESTIMATE, headers=AUTH, json=payload())
    assert response.status_code == 429
    assert response.json() == {'error': 'quota_exceeded'}
    assert len(seen) == 50
    assert client.post(LINK, headers=AUTH, json=payload()).status_code == 200
    assert client.post(ESTIMATE, headers={'Authorization': 'Bearer internal-other'},
                       json=payload()).status_code == 200


def test_count_atomic_at_boundary_and_resets_at_shanghai_midnight(tmp_path):
    path = tmp_path / 'calls.sqlite'
    owner = check('internal').principal
    before = datetime(2026, 11, 20, 15, 59, tzinfo=timezone.utc)
    after = datetime(2026, 11, 20, 16, tzinfo=timezone.utc)
    old = PluginCalls(path, clock=lambda: before)
    for _ in range(49):
        old.reserve(owner, ESTIMATE, 50)

    def reserve(_):
        try:
            PluginCalls(path, clock=lambda: before).reserve(owner, ESTIMATE, 50)
        except PluginError as error:
            return error.code
        return 'accepted'

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(reserve, range(2))) == ['accepted', 'quota_exceeded']
    PluginCalls(path, clock=lambda: after).reserve(owner, ESTIMATE, 50)


def test_upstream_error_mapping_does_not_echo_provider_message():
    provider = DiDiInformation(lambda *_: {'error': {'code': -32001, 'message': 'private'}})
    with pytest.raises(PluginError, match='^rate_limited$') as raised:
        provider.call('taxi_estimate', {})
    assert raised.value.status == 429

    def timeout(*_):
        raise TimeoutError('private request URL')

    with pytest.raises(PluginError, match='^supplier_timeout$') as raised:
        DiDiInformation(timeout).call('taxi_estimate', {})
    assert raised.value.status == 504


@pytest.mark.parametrize('link', ['https://taxi.example.invalid.evil.test/', 'https://x@taxi.example.invalid/',
                                 'https://taxi.example.invalid:443/', 'http://taxi.example.invalid/',
                                 'https://taxi.example.invalid/route?opaque=private',
                                 'https://taxi.example.invalid/route#private',
                                 'https://taxi.example.invalid/route/private',
                                 'https://taxi.example.invalid/?%6bey=fixture'])
def test_unapproved_provider_link_is_never_forwarded(link):
    from cj_api.taxi_tools import _public_link

    with pytest.raises(PluginError, match='^supplier_unavailable$'):
        _public_link(link, {FIXTURE_LINK})



def test_counter_open_failure_has_stable_error(tmp_path):
    calls = PluginCalls(tmp_path / 'missing' / 'counts.sqlite', clock=lambda: NOW)
    with pytest.raises(PluginError, match='^unavailable$') as raised:
        calls.reserve(check('internal').principal, ESTIMATE, 50)
    assert raised.value.status == 503
