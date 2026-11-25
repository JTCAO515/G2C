"""HK wiring for HOTEL.2 (#1511): private worker socket, roster, Trip.com hand-off route."""

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cj_api.lio_hotel_search import HANDOFF_PATH, ROUTE, TRIP_LIST, HandoffStore, HotelSearchService
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.hotel_budget import HotelBudget, SHANGHAI
from deploy.hk.hotel_relay import (
    hotel_handoff_request, hotel_search_request, hotel_socket, register_hotel_routes,
)

ORIGIN = 'https://relay.example.invalid'
HOTELS = [dict(name='北京王府井希尔顿酒店', id='B0H1', typecode='100102', location='116.412700,39.913900',
               address='王府井东街8号', cityname='北京市', business={'rating': '4.7'})]
STATIONS = [dict(name='王府井(地铁站)', id='BV1', typecode='150500', location='116.411200,39.910800')]


def payload(**other):
    body = dict(version='HOTEL.2', request_id=str(uuid4()), city='北京', near=dict(query='王府井'),
                check_in='2026-12-03', check_out='2026-12-05', guests=2, language='zh')
    body.update(other)
    return body


class Supplier:
    def __init__(self, *, landmark=True):
        self.calls = []
        self.landmark = landmark

    def query(self, operation, params, reserve):
        reserve()
        self.calls.append(operation)
        replies = dict(geocode={'geocodes': [{'location': '116.410886,39.911521'}] if self.landmark else []},
                       hotels_around={'pois': HOTELS}, hotels_text={'pois': HOTELS}, subway={'pois': STATIONS})
        data = replies[operation]
        return data, json.dumps(data, ensure_ascii=False).encode()


def checker():
    accepted = AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED,
                                 SimpleNamespace(issuer='internal-issuer', subject='internal'))
    denied = AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.NOT_INVITED)
    return SimpleNamespace(check=lambda token: accepted if token == 'synthetic' else denied)


@contextmanager
def relay(tmp_path, *, enabled=True, supplier=None):
    ledger = AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 25, 19, tzinfo=SHANGHAI))
    supplier = supplier or Supplier()
    handoffs = HandoffStore() if enabled else None
    service = HotelSearchService(supplier, HotelBudget(ledger), handoffs, public_origin=ORIGIN) if enabled else None
    with TemporaryDirectory(prefix='g2c-hotel-', dir='/tmp') as directory:
        path = Path(directory) / 'hotel.sock'
        with hotel_socket(service, handoffs, checker(), {'internal'}, path=path, disabled=not enabled):
            app = FastAPI()
            register_hotel_routes(app, search=lambda token, raw: hotel_search_request(token, raw, path=path),
                                  handoff=lambda handle: hotel_handoff_request(handle, path=path))
            with TestClient(app, follow_redirects=False) as browser:
                yield browser, supplier, handoffs


def test_search_relays_through_the_worker_and_hands_off_to_trip_com(tmp_path):
    with relay(tmp_path) as (browser, supplier, _):
        assert browser.post(ROUTE, json=payload()).status_code == 401
        assert browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer unknown'}).status_code == 403
        response = browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer synthetic'})
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        body = response.json()
        assert body['version'] == 'HOTEL.2' and body['affiliate_links'] is False
        (item,) = body['items']
        assert item['name_zh'] == '北京王府井希尔顿酒店' and item['metro']['name_zh'] == '王府井站'
        booking = urlsplit(item['booking_url'])
        assert item['booking_url'].startswith(ORIGIN + HANDOFF_PATH)
        handle = booking.path.removeprefix(HANDOFF_PATH)
        # The browser carries no bearer: the handle alone opens the fixed Trip.com list.
        out = browser.get(HANDOFF_PATH + handle)
        assert out.status_code == 302 and out.headers['location'].startswith(TRIP_LIST + '?cityId=1&')
        assert out.headers['cache-control'] == 'no-store' and out.headers['referrer-policy'] == 'no-referrer'
        for unknown in ('A' * 22, 'short', 'B' * 22 + '..'):
            missing = browser.get(HANDOFF_PATH + unknown)
            assert missing.status_code == 404 and 'location' not in missing.headers
    assert supplier.calls == ['geocode', 'hotels_around', 'subway']


def test_unknown_landmark_and_duplicate_request_pass_through(tmp_path):
    with relay(tmp_path, supplier=Supplier(landmark=False)) as (browser, _, _):
        response = browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer synthetic'})
        assert (response.status_code, response.json()) == (404, {'error': 'place_not_found'})
    with relay(tmp_path) as (browser, _, _):
        body = payload()
        assert browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer synthetic'}).status_code == 200
        # A new near value misses the cache, so the same request_id reaches its already-recorded geocode step.
        repeat = browser.post(ROUTE, json=dict(body, near=dict(query='东单')), headers={'Authorization': 'Bearer synthetic'})
        assert (repeat.status_code, repeat.json()) == (409, {'error': 'request_already_used'})


def test_closed_relay_answers_not_enabled_and_never_redirects(tmp_path):
    with relay(tmp_path, enabled=False) as (browser, supplier, _):
        response = browser.post(ROUTE, json=payload(), headers={'Authorization': 'Bearer synthetic'})
        assert (response.status_code, response.json()) == (403, {'error': 'not_enabled'})
        assert browser.get(HANDOFF_PATH + 'A' * 22).status_code == 404
    assert supplier.calls == []


def test_handoff_route_only_redirects_to_the_fixed_trip_com_pages():
    app = FastAPI()
    replies = {'A' * 22: (200, {'url': 'https://evil.example/hotels/list?x=1'}),
               'B' * 22: (200, {'url': TRIP_LIST + '?cityId=2'}),
               'C' * 22: (503, {'error': 'unavailable'})}
    register_hotel_routes(app, search=None, handoff=lambda handle: replies[handle])
    with TestClient(app, follow_redirects=False) as browser:
        assert browser.get(HANDOFF_PATH + 'A' * 22).status_code == 404
        good = browser.get(HANDOFF_PATH + 'B' * 22)
        assert good.status_code == 302 and good.headers['location'] == TRIP_LIST + '?cityId=2'
        assert browser.get(HANDOFF_PATH + 'C' * 22).status_code == 503


def _hotel_roster(monkeypatch, subjects):
    from deploy.hk import hotel_relay

    opened = []

    @contextmanager
    def socket(service, handoffs, checker, roster, *, disabled):
        opened.append((service, handoffs, checker, roster, disabled))
        yield

    monkeypatch.setenv(hotel_relay.HOTEL_INTERNAL_SUBJECTS, json.dumps(subjects))
    monkeypatch.setenv('CJ_AMAP_WEB_KEY', 'fixture-gaode-key-0123456789')
    monkeypatch.setattr(hotel_relay, 'AuthorizationBudget', lambda *args, **kwargs: object())
    monkeypatch.setattr(hotel_relay, 'account_checker_for',
                        lambda auth, database, *, selected_subjects: ('checker', selected_subjects))
    monkeypatch.setattr(hotel_relay, 'hotel_socket', socket)
    runtime = SimpleNamespace(auth=object(), database=lambda: object())
    with hotel_relay.active_hotel(runtime, None):
        pass
    (service, handoffs, checker, roster, disabled), = opened
    return service, handoffs, checker, roster, disabled


def test_hotel_accepts_the_authorized_internal_cohort_with_hotel_operations(monkeypatch):
    from cj_usage import hotel_budget
    from deploy.hk.plugin_roster import generate_plugin_subjects

    cohort = generate_plugin_subjects()
    for subjects in (cohort, cohort[:1]):
        service, handoffs, checker, roster, disabled = _hotel_roster(monkeypatch, subjects)
        assert service is not None and handoffs is service.handoffs and not disabled
        assert service.provider._operations == hotel_budget.OPERATIONS
        assert service.public_origin == 'https://api-beta.go2china.space'
        assert roster == frozenset(subjects) and checker == ('checker', frozenset(subjects))


@pytest.mark.parametrize('subjects', [[], 'not-a-list', ['outside-the-internal-cohort'], 'cohort+outside',
                                      'cohort+duplicate', [7]])
def test_hotel_refuses_rosters_outside_the_authorized_cohort(monkeypatch, subjects):
    from deploy.hk import hotel_relay
    from deploy.hk.demo_login import invitation_subject

    cohort = hotel_relay.generate_plugin_subjects()
    subjects = {'cohort+outside': [*cohort, invitation_subject('CJ_Tester@01')],
                'cohort+duplicate': [*cohort, cohort[0]]}.get(subjects, subjects) if type(subjects) is str else subjects

    def supplier_must_not_start(*args, **kwargs):
        pytest.fail('An unauthorized roster must be refused before supplier creation')

    monkeypatch.setattr(hotel_relay, 'GaodeNearby', supplier_must_not_start)
    assert _hotel_roster(monkeypatch, subjects)[:4] == (None, None, None, frozenset())


def test_unset_roster_keeps_the_route_closed(monkeypatch):
    from deploy.hk import hotel_relay

    opened = []

    @contextmanager
    def socket(service, handoffs, checker, roster, *, disabled):
        opened.append((service, disabled))
        yield

    monkeypatch.delenv(hotel_relay.HOTEL_INTERNAL_SUBJECTS, raising=False)
    monkeypatch.setattr(hotel_relay, 'hotel_socket', socket)
    with hotel_relay.active_hotel(SimpleNamespace(), None):
        pass
    assert opened == [(None, True)]
