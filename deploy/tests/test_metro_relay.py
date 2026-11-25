"""HK wiring for METRO-NEARBY.1 (#1450): private worker socket, roster, station-id requests only."""

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cj_api.metro_nearby import ROUTE, VERSION, MetroNearbyService
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.metro_nearby_budget import MetroNearbyBudget, SHANGHAI
from deploy.hk import metro_relay
from deploy.hk.metro_relay import metro_request, metro_socket, register_metro_routes

STATIONS = {('guangzhou', 'gz014'): '113.321200,23.137800'}


class Supplier:
    def __init__(self):
        self.calls = []

    def query(self, operation, params, reserve):
        reserve()
        self.calls.append((operation, params))
        data = {'pois': [dict(name='天河城', id='B001', typecode='060101', location='113.322700,23.132700',
                              distance='31', address='天河路208号')]}
        return data, json.dumps(data, ensure_ascii=False).encode()


def checker():
    accepted = AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED,
                                 SimpleNamespace(issuer='internal-issuer', subject='internal'))
    denied = AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.NOT_INVITED)
    return SimpleNamespace(check=lambda token: accepted if token == 'synthetic' else denied)


def payload(**other):
    body = dict(version=VERSION, request_id=str(uuid4()), city_id='guangzhou', station_id='gz014',
                categories=['sights'], language='zh')
    body.update(other)
    return body


@contextmanager
def relay(tmp_path, *, enabled=True):
    ledger = AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 25, 19, tzinfo=SHANGHAI))
    supplier = Supplier()
    service = (MetroNearbyService(supplier, MetroNearbyBudget(ledger), stations=dict(STATIONS))
               if enabled else None)
    with TemporaryDirectory(prefix='g2c-metro-', dir='/tmp') as directory:
        path = Path(directory) / 'metro.sock'
        with metro_socket(service, checker(), {'internal'}, path=path, disabled=not enabled):
            app = FastAPI()
            register_metro_routes(app, send=lambda token, raw: metro_request(token, raw, path=path))
            with TestClient(app) as browser:
                yield browser, supplier


def test_station_search_relays_through_the_worker_and_caches_per_station(tmp_path):
    with relay(tmp_path) as (browser, supplier):
        assert browser.post(ROUTE, json=payload()).status_code == 401
        assert browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer unknown'}).status_code == 403
        response = browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer synthetic'})
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        value = response.json()
        assert value['version'] == VERSION and value['station_id'] == 'gz014' and value['items']
        again = browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer synthetic'})
        assert again.status_code == 200
    assert len(supplier.calls) == 1   # the second request is a cache hit: no call, no count


def test_unknown_station_and_positions_never_reach_gaode(tmp_path):
    with relay(tmp_path) as (browser, supplier):
        missing = browser.post(ROUTE, json=payload(station_id='gz999'), headers={'Authorization': 'Bearer synthetic'})
        assert (missing.status_code, missing.json()) == (404, {'error': 'station_not_found'})
        position = browser.post(ROUTE, json=dict(payload(), center=dict(lat=23.1, lng=113.3)),
                                headers={'Authorization': 'Bearer synthetic'})
        assert position.status_code == 400
    assert supplier.calls == []


def test_closed_relay_answers_not_enabled_and_unreachable_worker_unavailable(tmp_path):
    with relay(tmp_path, enabled=False) as (browser, supplier):
        response = browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer synthetic'})
        assert (response.status_code, response.json()) == (403, {'error': 'not_enabled'})
    assert supplier.calls == []
    app = FastAPI()
    register_metro_routes(app, send=lambda token, raw: metro_request(token, raw, path=tmp_path / 'missing.sock'))
    with TestClient(app) as browser:
        response = browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer synthetic'})
        assert (response.status_code, response.json()) == (503, {'error': 'unavailable'})


def _metro_roster(monkeypatch, subjects):
    opened = []

    @contextmanager
    def socket(service, checker, roster, *, disabled):
        opened.append((service, checker, roster, disabled))
        yield

    if subjects is None:
        monkeypatch.delenv(metro_relay.METRO_NEARBY_INTERNAL_SUBJECTS, raising=False)
    else:
        monkeypatch.setenv(metro_relay.METRO_NEARBY_INTERNAL_SUBJECTS, json.dumps(subjects))
    monkeypatch.setenv('CJ_AMAP_WEB_KEY', 'fixture-gaode-key-0123456789')
    monkeypatch.setattr(metro_relay, 'AuthorizationBudget', lambda *args, **kwargs: object())
    monkeypatch.setattr(metro_relay, 'account_checker_for',
                        lambda auth, database, *, selected_subjects: ('checker', selected_subjects))
    monkeypatch.setattr(metro_relay, 'metro_socket', socket)
    with metro_relay.active_metro(SimpleNamespace(auth=object(), database=lambda: object()), None):
        pass
    (service, checker, roster, disabled), = opened
    return service, checker, roster, disabled


def test_metro_accepts_the_authorized_cohort_with_the_metro_operations(monkeypatch):
    from cj_usage import metro_nearby_budget
    from deploy.hk.plugin_roster import generate_plugin_subjects

    cohort = generate_plugin_subjects()
    for subjects in (cohort, cohort[:1]):
        service, checker, roster, disabled = _metro_roster(monkeypatch, subjects)
        assert service is not None and not disabled
        assert service.provider._operations == metro_nearby_budget.OPERATIONS
        assert roster == frozenset(subjects) and checker == ('checker', frozenset(subjects))
    assert _metro_roster(monkeypatch, None) == (None, None, frozenset(), True)


@pytest.mark.parametrize('subjects', [[], 'not-a-list', ['outside-the-internal-cohort'], 'cohort+outside',
                                      'cohort+duplicate', [7]])
def test_metro_refuses_rosters_outside_the_authorized_cohort(monkeypatch, subjects):
    from deploy.hk.demo_login import invitation_subject

    cohort = metro_relay.generate_plugin_subjects()
    subjects = {'cohort+outside': [*cohort, invitation_subject('CJ_Tester@01')],
                'cohort+duplicate': [*cohort, cohort[0]]}.get(subjects, subjects) if type(subjects) is str else subjects

    def supplier_must_not_start(*args, **kwargs):
        pytest.fail('An unauthorized roster must be refused before supplier creation')

    monkeypatch.setattr(metro_relay, 'GaodeNearby', supplier_must_not_start)
    assert _metro_roster(monkeypatch, subjects)[:3] == (None, None, frozenset())
