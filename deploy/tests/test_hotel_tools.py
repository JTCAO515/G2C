import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cj_api.hotel_tools import HotelService, ROUTE, register_hotel_route
from cj_api.plugin_tools import PluginCalls
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal


AUTH = {'Authorization': 'Bearer internal'}
ORIGIN = 'https://hotel.example.invalid'
HANDLE = 'fixture_handle_aaaaaaaaaaaa'
PAYLOAD = dict(version='HOTEL.1', city='北京', check_in='2026-12-03',
               check_out='2026-12-05', guests=2, language='zh')


def allowed(token):
    principal = TrustedPrincipal('fixture-issuer', token, 'app', 1, 1, 2)
    return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal)


@pytest.fixture
def context(tmp_path):
    def adapter(request):
        supplied.append(request.model_dump(exclude_none=True))
        return {'handle': HANDLE, 'applied_filters': ['location']}

    supplied = []
    path = tmp_path / 'hotel-count.sqlite'
    app = FastAPI()
    register_hotel_route(app, hotel=HotelService(adapter, ORIGIN),
                          checker=SimpleNamespace(check=allowed), internal=frozenset({'internal'}),
                          calls=PluginCalls(path))
    with TestClient(app) as client:
        yield client, supplied, path


def test_default_disabled():
    app = FastAPI()
    register_hotel_route(app)
    with TestClient(app) as client:
        response = client.post(ROUTE, headers=AUTH, json=PAYLOAD)
        assert response.status_code == 403
        assert response.json() == {'error': 'not_enabled'}
        assert 'no-store' == response.headers['Cache-Control']
        assert client.post('/v1/tools/hotel/search', headers=AUTH, json=PAYLOAD).status_code == 404


def test_city_and_geo_inputs_count_and_never_claim_unverified_filters(context):
    client, supplied, path = context
    location = dict(lat=39.9, lng=116.4, radius_m=600)
    geo = dict(PAYLOAD, city=None, location=location)
    for item in (PAYLOAD, geo):
        response = client.post(ROUTE, headers=AUTH, json=item)
        assert response.status_code == 200
        assert response.json() == {
            'version': 'HOTEL.1', 'url': f'{ORIGIN}/v1/tools/hotel/out/{HANDLE}',
            'applied_filters': ['location'],
            'unapplied_filters': ['check_in', 'check_out', 'guests', 'language', 'accepts_foreign_guests'],
        }
    assert supplied == [PAYLOAD, {key: value for key, value in geo.items() if value is not None}]
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT operation, used FROM plugin_call').fetchall() == [(ROUTE, 2)]


@pytest.mark.parametrize('data', [
    dict(PAYLOAD, location=dict(lat=39.9, lng=116.4, radius_m=500)),
    dict(PAYLOAD, city=None),
    dict(PAYLOAD, check_out='2026-12-02'),
    dict(PAYLOAD, check_in='20261203'),
    dict(PAYLOAD, guests=True),
    dict(PAYLOAD, city='北京', phone='1234'),
    dict(PAYLOAD, city=None, location=dict(lat=39.9, lng=116.4, radius_m=-1)),
])
def test_bad_input_rejected_without_count_or_dispatch(context, data):
    client, supplied, path = context
    assert client.post(ROUTE, headers=AUTH, json=data).status_code == 400
    assert supplied == []
    assert not path.exists()


def test_missing_or_external_session_never_dispatches(context):
    client, supplied, path = context
    assert client.post(ROUTE, json=PAYLOAD).status_code == 401
    assert client.post(ROUTE, headers={'Authorization': 'Bearer externally-invited'},
                       json=PAYLOAD).status_code == 403
    assert supplied == []
    assert not path.exists()


@pytest.mark.parametrize('handoff', [
    {'handle': HANDLE, 'applied_filters': ['location', 'location']},
    {'handle': HANDLE, 'applied_filters': ['undocumented']},
    {'handle': 'https://thirdparty.example.invalid/?affiliate=test', 'applied_filters': []},
    {'handle': HANDLE, 'applied_filters': [], 'affiliate_id': 'private-config'},
])
def test_unexpected_handoff_is_not_returned(tmp_path, handoff):
    app = FastAPI()
    register_hotel_route(app, hotel=HotelService(lambda _: handoff, ORIGIN),
                          checker=SimpleNamespace(check=allowed), internal=frozenset({'internal'}),
                          calls=PluginCalls(tmp_path / 'counts.sqlite'))
    with TestClient(app) as client:
        response = client.post(ROUTE, headers=AUTH, json=PAYLOAD)
    assert response.status_code == 502
    assert response.json() == {'error': 'supplier_unavailable'}
