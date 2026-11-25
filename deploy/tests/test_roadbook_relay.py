"""HK wiring for ROADBOOK.1 (#1516): private worker socket, roster, larger body bound, long relay timeout."""

from contextlib import contextmanager
from datetime import datetime
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cj_api.lio_roadbook import ROUTE, MemoryRoadbookCache, RoadbookService
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.roadbook_budget import BEIJING, RoadbookBudget, RoadbookPlaceBudget
from deploy.hk import roadbook_relay
from deploy.hk.roadbook_relay import register_roadbook_routes, roadbook_request, roadbook_socket

_spec = importlib.util.spec_from_file_location('roadbook_fixtures', Path(__file__).with_name('test_lio_roadbook.py'))
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)


def checker():
    accepted = AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED,
                                 SimpleNamespace(issuer='internal-issuer', subject='internal'))
    denied = AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.NOT_INVITED)
    return SimpleNamespace(check=lambda token: accepted if token == 'synthetic' else denied)


@contextmanager
def relay(tmp_path, *, enabled=True):
    ledger = AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 25, 19, tzinfo=BEIJING))
    gaode, flash = fixtures.Gaode(), fixtures.Flash()
    service = (RoadbookService(gaode, flash, RoadbookBudget(ledger), RoadbookPlaceBudget(ledger), MemoryRoadbookCache())
               if enabled else None)
    with TemporaryDirectory(prefix='g2c-roadbook-', dir='/tmp') as directory:
        path = Path(directory) / 'roadbook.sock'
        with roadbook_socket(service, checker(), {'internal'}, path=path, disabled=not enabled):
            app = FastAPI()
            register_roadbook_routes(app, send=lambda token, raw: roadbook_request(token, raw, path=path))
            with TestClient(app) as browser:
                yield browser, gaode, flash, path


def palace():
    return dict(id='stop-1', name_zh='故宫博物院', name_en='Palace Museum', city='北京')


def test_enrichment_relays_through_the_worker_with_the_callers_bearer(tmp_path):
    with relay(tmp_path) as (browser, gaode, flash, _):
        body = fixtures.payload(palace())
        assert browser.post(ROUTE, json=body).status_code == 401
        assert browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer unknown'}).status_code == 403
        response = browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer synthetic'})
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        value = response.json()
        assert value['version'] == 'ROADBOOK.1'
        (place,) = value['places']
        assert place['id'] == 'stop-1' and place['status'] == 'ready'
        calls = (len(gaode.calls), len(flash.calls))
        assert calls[0] and calls[1]
        # The same public place is now cached: a repeat costs no supplier call and needs no new budget.
        repeat = browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer synthetic'})
        assert repeat.status_code == 200 and repeat.json()['places'][0]['status'] == 'ready'
        assert (len(gaode.calls), len(flash.calls)) == calls


def test_twenty_places_fit_the_body_bound_but_a_larger_body_is_refused(tmp_path):
    with relay(tmp_path) as (browser, gaode, _, _path):
        many = [dict(palace(), id=f'stop-{n}', name_zh='故宫博物院' + '馆' * 40) for n in range(20)]
        body = fixtures.payload(*many)
        assert len(json.dumps(body, ensure_ascii=False).encode()) > 4096   # over the generic plugin bound
        response = browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer synthetic'})
        assert response.status_code == 200 and len(response.json()['places']) == 20
        big = browser.post(ROUTE, content=b'{' + b' ' * (16 * 1024) + b'}', headers={
            'Authorization': 'Bearer synthetic', 'Content-Type': 'application/json'})
        assert (big.status_code, big.json()) == (413, {'error': 'request_too_large'})
        bad = browser.post(ROUTE, json=dict(version='ROADBOOK.1', places=[]), headers={'Authorization': 'Bearer synthetic'})
        assert bad.status_code == 400


def test_closed_relay_answers_not_enabled_without_supplier_calls(tmp_path):
    with relay(tmp_path, enabled=False) as (browser, gaode, flash, _):
        response = browser.post(ROUTE, json=fixtures.payload(palace()), headers={'Authorization': 'Bearer synthetic'})
        assert (response.status_code, response.json()) == (403, {'error': 'not_enabled'})
    assert gaode.calls == [] and flash.calls == []


def test_unreachable_worker_is_unavailable(tmp_path):
    app = FastAPI()
    register_roadbook_routes(app, send=lambda token, raw: roadbook_request(token, raw, path=tmp_path / 'missing.sock'))
    with TestClient(app) as browser:
        response = browser.post(ROUTE, json=fixtures.payload(palace()), headers={'Authorization': 'Bearer synthetic'})
        assert (response.status_code, response.json()) == (503, {'error': 'unavailable'})


def _roadbook_roster(monkeypatch, subjects):
    opened = []

    @contextmanager
    def socket(service, checker, roster, *, disabled):
        opened.append((service, checker, roster, disabled))
        yield

    if subjects is None:
        monkeypatch.delenv(roadbook_relay.ROADBOOK_INTERNAL_SUBJECTS, raising=False)
    else:
        monkeypatch.setenv(roadbook_relay.ROADBOOK_INTERNAL_SUBJECTS, json.dumps(subjects))
    monkeypatch.setenv('CJ_AMAP_WEB_KEY', 'fixture-gaode-key-0123456789')
    monkeypatch.setenv('CJ_MODEL_API_KEY', 'fixture-model-key')
    monkeypatch.setattr(roadbook_relay, 'AuthorizationBudget', lambda *args, **kwargs: object())
    monkeypatch.setattr(roadbook_relay, 'account_checker_for',
                        lambda auth, database, *, selected_subjects: ('checker', selected_subjects))
    monkeypatch.setattr(roadbook_relay, 'roadbook_socket', socket)
    with roadbook_relay.active_roadbook(SimpleNamespace(auth=object(), database=lambda: object()), None):
        pass
    (service, checker, roster, disabled), = opened
    return service, checker, roster, disabled


def test_roadbook_accepts_the_authorized_cohort_with_both_budgets(monkeypatch):
    from cj_usage.roadbook_budget import AMAP_OPERATIONS
    from deploy.hk.plugin_roster import generate_plugin_subjects

    cohort = generate_plugin_subjects()
    for subjects in (cohort, cohort[:1]):
        service, checker, roster, disabled = _roadbook_roster(monkeypatch, subjects)
        assert service is not None and not disabled
        assert service.gaode._operations == AMAP_OPERATIONS
        assert isinstance(service.budget, RoadbookBudget) and isinstance(service.places, RoadbookPlaceBudget)
        assert isinstance(service.cache, MemoryRoadbookCache)
        assert roster == frozenset(subjects) and checker == ('checker', frozenset(subjects))
    assert _roadbook_roster(monkeypatch, None) == (None, None, frozenset(), True)


@pytest.mark.parametrize('subjects', [[], 'not-a-list', ['outside-the-internal-cohort'], 'cohort+outside',
                                      'cohort+duplicate', [7]])
def test_roadbook_refuses_rosters_outside_the_authorized_cohort(monkeypatch, subjects):
    from deploy.hk.demo_login import invitation_subject

    cohort = roadbook_relay.generate_plugin_subjects()
    subjects = {'cohort+outside': [*cohort, invitation_subject('CJ_Tester@01')],
                'cohort+duplicate': [*cohort, cohort[0]]}.get(subjects, subjects) if type(subjects) is str else subjects

    def supplier_must_not_start(*args, **kwargs):
        pytest.fail('An unauthorized roster must be refused before supplier creation')

    monkeypatch.setattr(roadbook_relay, 'GaodeNearby', supplier_must_not_start)
    assert _roadbook_roster(monkeypatch, subjects)[:3] == (None, None, frozenset())
