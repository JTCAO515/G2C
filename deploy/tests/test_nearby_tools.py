from datetime import datetime, timedelta
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
from cj_usage.authorization_budget import AMAP_PRICE, CNY_SCALE, LIMITS, AuthorizationBudget, authorization_usage, journal_state
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.nearby_budget import NearbyBudget, NearbyDuplicate, SHANGHAI
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


@pytest.mark.parametrize('mode', ['mixed','empty','invalid'])
def test_nearby_projection_preserves_usable_rows_and_distinguishes_empty_results(ledger, caplog, mode):
    class ProjectionSupplier(Supplier):
        def query(self, operation, params, reserve):
            value, raw = super().query(operation, params, reserve)
            if operation != 'search':
                return value, raw
            invalid = dict(name='synthetic POI without coordinates',id='B456',typecode='050501',location=[])
            if mode == 'mixed':
                value['pois'].append(invalid)
            elif mode == 'empty':
                value = {'count':'0'}
            else:
                value['pois'] = [invalid]
            return value, json.dumps(value).encode()

    provider = ProjectionSupplier()
    service = NearbyService(provider, NearbyBudget(ledger))
    body = NearbySearchRequest.model_validate(payload(categories=['coffee'], radius_m=500, sort='distance'))
    if mode == 'invalid':
        with pytest.raises(PluginError) as rejected:
            service.search('owner', body, lambda: None)
        assert rejected.value.status == 502
    else:
        result = service.search('owner', body, lambda: None)
        if mode == 'mixed':
            assert result['omitted_items'] == 1
            assert [row['id'] for row in result['items']] == ['B123']
        else:
            assert result == dict(version='NEARBY.1', source='Gaode', items=[])
    assert [row['state'] for row in ledger.inspect()] == ['RECEIVED','RECEIVED']
    if mode != 'empty':
        assert 'coordinate' in caplog.text and 'synthetic POI without coordinates' not in caplog.text


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


def test_nearby_unresolved_attempt_retains_the_original_export_and_cross_day_deduplication(ledger):
    from scripts.m4_budget_transfer import attempts

    nearby = NearbyBudget(ledger)
    request_id = uuid4()
    attempt = nearby.begin('owner', request_id, 'search')
    with ledger.connect() as db:
        assert attempts(db) == journal_state(db)
        assert authorization_usage(db)[2]['place'] == LIMITS['place'][1] * CNY_SCALE
    tomorrow = ledger.clock() + timedelta(days=1)
    ledger.clock = lambda: tomorrow
    with pytest.raises(NearbyDuplicate):
        nearby.begin('owner', request_id, 'search')
    nearby.finish(attempt, b'original supplier fixture response')
    with ledger.connect() as db:
        assert attempts(db) == journal_state(db)
        assert authorization_usage(db)[1]['place'] == AMAP_PRICE


@pytest.mark.parametrize('encoded', [False, True])
def test_gaode_response_cannot_echo_the_server_key(encoded):
    fixture_key = 'local-fixture-key-only'
    if encoded:
        quoted = ''.join(f'%{ord(char):02X}' for char in fixture_key)
        row = {'photos': [{'url': f'https://store.is.autonavi.com/picture?marker={quoted}'}]}
    else:
        row = {'name': fixture_key}

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
                dict(status='1', infocode='10000', pois=[row])).encode())

        def close(self):
            pass

    service = GaodeNearby(fixture_key, connection=Transport)
    with pytest.raises(PluginError) as mismatch:
        service.query('search', {'location': '116.4,39.9'}, lambda: None)
    assert mismatch.value.status == 502 and fixture_key not in str(mismatch.value)


def _nearby_roster(monkeypatch, subjects):
    from contextlib import contextmanager
    from deploy.hk import nearby_relay

    opened = []

    @contextmanager
    def socket(service, checker, roster, *, disabled):
        opened.append((service, checker, roster, disabled))
        yield

    monkeypatch.setenv(nearby_relay.NEARBY_INTERNAL_SUBJECTS, json.dumps(subjects))
    monkeypatch.setenv('CJ_AMAP_WEB_KEY', 'fixture-gaode-key-0123456789')
    monkeypatch.setattr(nearby_relay, 'AuthorizationBudget', lambda *args, **kwargs: object())
    monkeypatch.setattr(nearby_relay, 'account_checker_for',
                        lambda auth, database, *, selected_subjects: ('checker', selected_subjects))
    monkeypatch.setattr(nearby_relay, 'nearby_socket', socket)
    runtime = SimpleNamespace(auth=object(), database=lambda: object())
    with nearby_relay.active_nearby(runtime, None):
        pass
    (service, checker, roster, disabled), = opened
    return service, checker, roster, disabled


def test_nearby_accepts_the_authorized_internal_cohort(monkeypatch):
    from deploy.hk.plugin_roster import generate_plugin_subjects

    cohort = generate_plugin_subjects()
    for subjects in (cohort, cohort[:1], cohort[:11]):
        service, checker, roster, disabled = _nearby_roster(monkeypatch, subjects)
        assert service is not None and not disabled
        assert roster == frozenset(subjects) and checker == ('checker', frozenset(subjects))


@pytest.mark.parametrize('subjects', [
    [],
    'not-a-list',
    ['outside-the-internal-cohort'],
    'cohort+outside',
    'cohort+duplicate',
    [7],
])
def test_nearby_refuses_rosters_outside_the_authorized_cohort(monkeypatch, subjects):
    from deploy.hk import nearby_relay
    from deploy.hk.demo_login import invitation_subject

    cohort = nearby_relay.generate_plugin_subjects()
    subjects = {'cohort+outside': [*cohort, invitation_subject('CJ_Tester@01')],
                'cohort+duplicate': [*cohort, cohort[0]]}.get(subjects, subjects) if type(subjects) is str else subjects

    def supplier_must_not_start(_key):
        pytest.fail('An unauthorized roster must be refused before supplier creation')

    monkeypatch.setattr(nearby_relay, 'GaodeNearby', supplier_must_not_start)
    assert _nearby_roster(monkeypatch, subjects)[:3] == (None, None, frozenset())


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
