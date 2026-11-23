from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cj_api.nearby_tools import GaodeNearby, NearbyLocationRequest, NearbySearchRequest, NearbyService, REVERSE
from cj_api.plugin_tools import PluginError
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus
from cj_usage.authorization_budget import AMAP_PRICE, LIMITS, AuthorizationBudget, authorization_usage
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.nearby_budget import NearbyBudget, SHANGHAI
from deploy.hk.nearby_relay import nearby_request, nearby_socket, register_nearby_routes


def payload(*, crs='WGS-84', **other):
    return dict(version='NEARBY.1', request_id=str(uuid4()),
                center=dict(lat=39.91, lng=116.40, coordinate_system=crs), **other)


class Supplier:
    def __init__(self):
        self.calls = []

    def query(self, operation, params, reserve):
        reserve()
        self.calls.append((operation, params))
        replies = dict(
            convert={'locations': '116.406171,39.911230'},
            search={'pois': [dict(name='咖啡厅', id='B123', typecode='050501', location='116.406170,39.911210',
                                  distance='26', business={'rating': '4.5', 'cost': '38'},
                                  photos=[{'url': 'https://store.is.autonavi.com/showpic/a'}])]},
            reverse={'regeocode': {'formatted_address': '北京市东城区示例地点'}},
        )
        data = replies[operation]
        return data, json.dumps(data).encode()


@pytest.fixture
def ledger(tmp_path):
    return AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 23, 19, tzinfo=SHANGHAI))


def test_nearby_converts_then_searches_once_and_reuses_short_cache(ledger):
    supplier = Supplier()
    service = NearbyService(supplier, NearbyBudget(ledger))
    args = dict(categories=['coffee', 'sights'], radius_m=500, sort='distance')
    request = NearbySearchRequest.model_validate(payload(**args))
    result = service.search('owner-a', request, lambda: None)
    assert result['items'][0]['name_zh'] == '咖啡厅'
    assert result['items'][0]['distance_m'] == 26 and result['items'][0]['coordinate_system'] == 'GCJ-02'
    assert result['items'][0]['opening_hours'] is None
    assert supplier.calls == [
        ('convert', {'locations': '116.400000,39.910000', 'coordsys': 'gps'}),
        ('search', {'location': '116.406171,39.911230', 'types': '050500|110000', 'radius': 500,
                    'sortrule': 'distance', 'page_size': 25, 'page_num': 1, 'show_fields': 'business,photos'}),
    ]
    later = NearbySearchRequest.model_validate(payload(**args))
    assert service.search('owner-b', later, lambda: None) == result
    assert len(supplier.calls) == 2
    with ledger.connect() as db:
        counts, estimates, _ = authorization_usage(db)
    assert counts['place'] == 2 and estimates['place'] == 2 * AMAP_PRICE
    assert '116.406171' not in str(ledger.inspect())


def test_reverse_uses_same_scope_limit_and_never_resends_an_original(ledger, monkeypatch):
    from cj_usage import nearby_budget

    monkeypatch.setattr(nearby_budget, 'DAILY_ACCOUNT_LIMIT', 1)
    monkeypatch.setattr(nearby_budget, 'M4_OPERATION_LIMIT', 2)
    supplier = Supplier()
    service = NearbyService(supplier, NearbyBudget(ledger))
    original = NearbyLocationRequest.model_validate(payload(crs='GCJ-02'))
    assert service.reverse('owner-a', original, lambda: None)['address_zh'] == '北京市东城区示例地点'
    with pytest.raises(PluginError) as duplicate:
        service.reverse('owner-a', original, lambda: None)
    assert duplicate.value.status == 409
    next_one = NearbyLocationRequest.model_validate(payload(crs='GCJ-02'))
    with pytest.raises(PluginError) as account_limit:
        service.reverse('owner-a', next_one, lambda: None)
    assert account_limit.value.status == 429
    service.reverse('owner-b', next_one, lambda: None)
    with pytest.raises(PluginError) as shared_limit:
        service.reverse('owner-c', next_one, lambda: None)
    assert shared_limit.value.status == 429
    assert len(supplier.calls) == 2 and all(op == 'reverse' for op, _ in supplier.calls)


def test_nearby_charges_share_cash_and_preserve_the_legacy_place_count(ledger, monkeypatch):
    monkeypatch.setitem(LIMITS, 'place', (1, LIMITS['place'][1]))
    service = NearbyService(Supplier(), NearbyBudget(ledger))
    service.reverse('owner-a', NearbyLocationRequest.model_validate(payload(crs='GCJ-02')), lambda: None)
    ledger.begin('legacy-first-place', 'place', b'legacy input')
    with pytest.raises(BudgetUnknown, match='call allowance'):
        ledger.begin('legacy-second-place', 'place', b'legacy input')


def test_gaode_response_cannot_echo_the_server_key():
    fixture_key = 'local-fixture-key-only'

    class Transport:
        def __init__(self, host, timeout):
            assert host == 'restapi.amap.com' and timeout == 8

        def connect(self):
            pass

        def request(self, method, path, *, headers):
            parsed = urlsplit(path)
            assert method == 'GET' and parsed.path == '/v5/place/around' and headers == {'Accept':'application/json'}
            assert parse_qs(parsed.query) == {'location':['116.4,39.9'], 'key':[fixture_key], 'output':['json']}

        def getresponse(self):
            return SimpleNamespace(status=200, close=lambda: None, read=lambda _: json.dumps(
                dict(status='1', infocode='10000', pois=[{'name': fixture_key}])).encode())

        def close(self):
            pass

    service = GaodeNearby(fixture_key, connection=Transport)
    with pytest.raises(PluginError) as mismatch:
        service.query('search', {'location': '116.4,39.9'}, lambda: None)
    assert mismatch.value.status == 502 and fixture_key not in str(mismatch.value)


@pytest.mark.parametrize('enabled', [False, True])
def test_nearby_http_relay_respects_internal_admission_and_closed_state(ledger, enabled):
    supplier = Supplier()
    service = NearbyService(supplier, NearbyBudget(ledger)) if enabled else None
    accepted = AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED,
                                 SimpleNamespace(issuer='internal-issuer', subject='internal'))
    denied = AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.NOT_INVITED)
    checker = SimpleNamespace(check=lambda token: accepted if token == 'synthetic' else denied)
    with TemporaryDirectory(prefix='g2c-nearby-', dir='/tmp') as directory:
        path = Path(directory) / 'area.sock'
        with nearby_socket(service, checker, {'internal'}, path=path, disabled=not enabled):
            app = FastAPI()
            register_nearby_routes(app, send=lambda action, token, raw: nearby_request(action, token, raw, path=path))
            with TestClient(app) as browser:
                body = payload(crs='GCJ-02')
                assert browser.post(REVERSE, json=body, headers={'Authorization': 'Bearer unknown'}).status_code == 403
                response = browser.post(REVERSE, json=body, headers={'Authorization': 'Bearer synthetic'})
                assert response.status_code == (200 if enabled else 403)
                if enabled:
                    assert response.json()['address_zh'] == '北京市东城区示例地点'
                else:
                    assert response.json() == {'error':'not_enabled'}
    assert len(supplier.calls) == int(enabled)
