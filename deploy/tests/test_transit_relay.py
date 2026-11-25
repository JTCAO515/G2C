"""HK wiring for TRANSPORT.1 (#1520, #1521): the worker's metered AMap transit relay and the API composition."""

from contextlib import contextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cj_api.lio_transport import ROUTE, TransportService, register_transport
from cj_api.lio_transport_rail import TransitRailService
from cj_api.plugin_tools import PluginCalls, PluginError, SHANGHAI
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.transit_budget import TransitBudget
from deploy.hk import travel_runtime
from deploy.hk.transit_relay import TransitRelayClient, transit_request, transit_socket

REPLY = dict(status='1', infocode='10000', count='1', route=dict(transits=[dict(duration='18000', segments=[
    dict(walking={}, bus={}, railway=dict(
        trip='G2', departure_stop=dict(name='上海虹桥', time='0800'), arrival_stop=dict(name='北京南', time='1228'),
        spaces=[dict(code='O', cost='626.0')]))])]))


class Supplier:
    def __init__(self):
        self.calls = []

    def query(self, operation, params, reserve):
        reserve()
        self.calls.append(operation)
        return REPLY, json.dumps(REPLY, ensure_ascii=False).encode()


def checker():
    accepted = AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED,
                                 SimpleNamespace(issuer='internal-issuer', subject='internal'))
    denied = AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.NOT_INVITED)
    return SimpleNamespace(check=lambda token: accepted if token == 'synthetic' else denied)


@contextmanager
def relay(tmp_path, *, enabled=True):
    ledger = AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 25, 19, tzinfo=SHANGHAI))
    supplier = Supplier()
    service = TransitRailService(supplier, TransitBudget(ledger)) if enabled else None
    with TemporaryDirectory(prefix='g2c-transit-', dir='/tmp') as directory:
        path = Path(directory) / 'transit.sock'
        with transit_socket(service, checker(), {'internal'}, path=path, disabled=not enabled):
            yield TransitRelayClient(send=lambda token, raw: transit_request(token, raw, path=path)), supplier, path


def day(offset=7):
    return (datetime.now(SHANGHAI).date() + timedelta(days=offset)).isoformat()


def test_worker_relay_runs_one_metered_transit_call_with_the_callers_bearer(tmp_path):
    with relay(tmp_path) as (client, supplier, _):
        items = client.trains('synthetic', '7b4a6f5e-1c2d-4e3f-8a9b-0c1d2e3f4a5b', 'shanghai', 'beijing', day())
        assert [item['number'] for item in items] == ['G2']
        with pytest.raises(PluginError) as foreign:
            client.trains('unknown', '0b4a6f5e-1c2d-4e3f-8a9b-0c1d2e3f4a5b', 'shanghai', 'beijing', day())
        assert foreign.value.status == 403
        with pytest.raises(PluginError) as again:
            client.trains('synthetic', '7b4a6f5e-1c2d-4e3f-8a9b-0c1d2e3f4a5b', 'shanghai', 'beijing', day())
        assert (again.value.status, again.value.code) == (409, 'request_already_used')
        with pytest.raises(PluginError) as bad:
            client.trains('synthetic', '1b4a6f5e-1c2d-4e3f-8a9b-0c1d2e3f4a5b', 'shanghai', 'atlantis', day())
        assert (bad.value.status, bad.value.code) == (400, 'invalid_request')
    assert supplier.calls == ['transit']


@pytest.mark.parametrize('document', [
    dict(request_id='x', origin_id='shanghai', destination_id='beijing'),
    dict(request_id='x', origin_id='shanghai', destination_id='beijing', day='2026-12-03', extra='1'),
    dict(request_id=7, origin_id='shanghai', destination_id='beijing', day='2026-12-03'),
    ['not', 'an', 'object'],
])
def test_worker_refuses_malformed_frames_before_any_amap_call(tmp_path, document):
    with relay(tmp_path) as (_, supplier, path):
        raw = json.dumps(document).encode()
        assert transit_request('synthetic', raw, path=path) == (400, {'error': 'invalid_request'})
        assert transit_request('synthetic', b'x' * 513, path=path) == (413, {'error': 'request_too_large'})
    assert supplier.calls == []


def test_closed_worker_answers_not_enabled_and_the_route_reports_the_rail_mode_closed(tmp_path):
    with relay(tmp_path, enabled=False) as (client, supplier, _):
        with pytest.raises(PluginError) as closed:
            client.trains('synthetic', '7b4a6f5e-1c2d-4e3f-8a9b-0c1d2e3f4a5b', 'shanghai', 'beijing', day())
        assert (closed.value.status, closed.value.code) == (403, 'not_enabled')
        app = FastAPI()
        register_transport(app, service=TransportService(rail=client), checker=checker(),
                           internal=frozenset({'internal'}), calls=PluginCalls(tmp_path / 'flights.sqlite'))
        with TestClient(app) as browser:
            body = dict(version='TRANSPORT.1', origin='shanghai', destination='beijing', date=day(), modes=['rail'])
            response = browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer synthetic'})
            assert response.status_code == 200 and response.json()['rail']['status'] == 'not_enabled'
    assert supplier.calls == []


def test_transport_route_forwards_the_bearer_through_the_worker_and_projects_trains(tmp_path):
    with relay(tmp_path) as (client, supplier, _):
        app = FastAPI()
        register_transport(app, service=TransportService(rail=client), checker=checker(),
                           internal=frozenset({'internal'}), calls=PluginCalls(tmp_path / 'flights.sqlite'))
        with TestClient(app) as browser:
            body = dict(version='TRANSPORT.1', origin='shanghai', destination='beijing', date=day(), modes=['rail'])
            assert browser.post(ROUTE, json=body).status_code == 401
            response = browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer synthetic'})
            assert response.status_code == 200
            rail = response.json()['rail']
            assert rail['status'] == 'ok' and [item['number'] for item in rail['items']] == ['G2']
    assert supplier.calls == ['transit']


def test_unreachable_worker_is_an_unavailable_rail_mode_not_a_route_failure(tmp_path):
    client = TransitRelayClient(send=lambda token, raw: transit_request(token, raw, path=tmp_path / 'missing.sock'))
    app = FastAPI()
    register_transport(app, service=TransportService(rail=client), checker=checker(),
                       internal=frozenset({'internal'}), calls=PluginCalls(tmp_path / 'flights.sqlite'))
    with TestClient(app) as browser:
        body = dict(version='TRANSPORT.1', origin='shanghai', destination='beijing', date=day(), modes=['rail'])
        response = browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer synthetic'})
        assert response.status_code == 200 and response.json()['rail']['status'] == 'unavailable'


# --- API composition -----------------------------------------------------------------------------------------

def _compose(monkeypatch, tmp_path, config, *, flights_key='offline-variflight-key'):
    registered = {}
    for name in ('register_weather', 'register_flights', 'register_transport'):
        monkeypatch.setattr(travel_runtime, name,
                            lambda app, name=name, **kwargs: registered.__setitem__(name, kwargs))
    path = tmp_path / 'travel-providers.json'
    path.write_text(json.dumps(config))
    monkeypatch.setattr(travel_runtime, '_config', lambda _: json.loads(path.read_text()))
    monkeypatch.setattr(travel_runtime, '_state', lambda target: ('calls', target.name))
    monkeypatch.setattr(travel_runtime, 'VariFlight', lambda key: ('variflight', key))
    monkeypatch.setattr(travel_runtime, 'account_checker_for', lambda auth, database, *, selected_subjects: 'checker')
    monkeypatch.delenv(travel_runtime.QWEATHER_KEY, raising=False)
    if flights_key:
        monkeypatch.setenv(travel_runtime.VARIFLIGHT_MCP_KEY, flights_key)
    else:
        monkeypatch.delenv(travel_runtime.VARIFLIGHT_MCP_KEY, raising=False)
    travel_runtime.register_runtime_travel(FastAPI(), object(), object(), state=tmp_path)
    return registered


def test_flights_and_transport_share_one_guarded_client_counter_and_payment_hold(monkeypatch, tmp_path):
    registered = _compose(monkeypatch, tmp_path, dict(flights_enabled=True, transport_enabled=True))
    flights, transport = registered['register_flights'], registered['register_transport']
    service = transport['service']
    assert service.flights is flights['service'] and flights['calls'] is transport['calls']
    assert transport['calls'] == ('calls', 'flights.sqlite')
    assert service.flights.hold == tmp_path / 'flights.payment-hold'
    assert isinstance(service.rail, TransitRelayClient)
    assert registered['register_weather'] == {}


def test_transport_without_the_flight_key_keeps_rail_and_reports_flights_closed(monkeypatch, tmp_path):
    registered = _compose(monkeypatch, tmp_path, dict(transport_enabled=True), flights_key=None)
    assert registered['register_flights'] == {}
    service = registered['register_transport']['service']
    assert service.flights is None and isinstance(service.rail, TransitRelayClient)


@pytest.mark.parametrize('config', [{}, dict(flights_enabled=True), dict(transport_enabled=False)])
def test_transport_route_stays_closed_unless_explicitly_enabled(monkeypatch, tmp_path, config):
    assert _compose(monkeypatch, tmp_path, config)['register_transport'] == {}


@pytest.mark.parametrize('raw', [dict(transport_enabled='yes'), dict(transport_enabled=1), dict(trains=True),
                                 dict(flights_enabled='true')])
def test_travel_configuration_refuses_unknown_or_non_boolean_switches(raw):
    with pytest.raises(ValueError):
        travel_runtime._validated(raw)


def test_travel_configuration_accepts_the_transport_switch():
    config = dict(weather_host='example.qweatherapi.com', flights_enabled=False, transport_enabled=True)
    assert travel_runtime._validated(config) == config


# --- worker roster -------------------------------------------------------------------------------------------

def _transit_roster(monkeypatch, subjects):
    from deploy.hk import transit_relay

    opened = []

    @contextmanager
    def socket(service, checker, roster, *, disabled):
        opened.append((service, checker, roster, disabled))
        yield

    if subjects is None:
        monkeypatch.delenv(transit_relay.TRANSIT_INTERNAL_SUBJECTS, raising=False)
    else:
        monkeypatch.setenv(transit_relay.TRANSIT_INTERNAL_SUBJECTS, json.dumps(subjects))
    monkeypatch.setenv('CJ_AMAP_WEB_KEY', 'fixture-gaode-key-0123456789')
    monkeypatch.setattr(transit_relay, 'AuthorizationBudget', lambda *args, **kwargs: object())
    monkeypatch.setattr(transit_relay, 'account_checker_for',
                        lambda auth, database, *, selected_subjects: ('checker', selected_subjects))
    monkeypatch.setattr(transit_relay, 'transit_socket', socket)
    runtime = SimpleNamespace(auth=object(), database=lambda: object())
    with transit_relay.active_transit(runtime, None):
        pass
    (service, checker, roster, disabled), = opened
    return service, checker, roster, disabled


def test_transit_accepts_the_authorized_cohort_with_the_transit_operation(monkeypatch):
    from cj_usage import transit_budget
    from deploy.hk.plugin_roster import generate_plugin_subjects

    cohort = generate_plugin_subjects()
    for subjects in (cohort, cohort[:1]):
        service, checker, roster, disabled = _transit_roster(monkeypatch, subjects)
        assert service is not None and not disabled
        assert service.provider._operations == transit_budget.OPERATIONS
        assert roster == frozenset(subjects) and checker == ('checker', frozenset(subjects))
    assert _transit_roster(monkeypatch, None) == (None, None, frozenset(), True)


@pytest.mark.parametrize('subjects', [[], 'not-a-list', ['outside-the-internal-cohort'], 'cohort+outside',
                                      'cohort+duplicate', [7]])
def test_transit_refuses_rosters_outside_the_authorized_cohort(monkeypatch, subjects):
    from deploy.hk import transit_relay
    from deploy.hk.demo_login import invitation_subject

    cohort = transit_relay.generate_plugin_subjects()
    subjects = {'cohort+outside': [*cohort, invitation_subject('CJ_Tester@01')],
                'cohort+duplicate': [*cohort, cohort[0]]}.get(subjects, subjects) if type(subjects) is str else subjects

    def supplier_must_not_start(*args, **kwargs):
        pytest.fail('An unauthorized roster must be refused before supplier creation')

    monkeypatch.setattr(transit_relay, 'transit_provider', supplier_must_not_start)
    assert _transit_roster(monkeypatch, subjects)[:3] == (None, None, frozenset())
