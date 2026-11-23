from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cj_api.currency_tools import CurrencyRates, ROUTE, register_currency_route
from cj_api.plugin_tools import PluginCalls, PluginError
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus
from deploy.hk.currency_runtime import configured_reference_subjects
from deploy.hk.plugin_roster import generate_plugin_subjects


FEED = b'''<Envelope xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<Cube><Cube time="2026-11-23"><Cube currency="CNY" rate="8.2157"/>
<Cube currency="USD" rate="1.1823"/></Cube></Cube></Envelope>'''
REQUEST = {'version': 'CURRENCY.1'}


def client(path, fetch, clock, *, enabled=True):
    app = FastAPI()
    principal = SimpleNamespace(issuer='issuer', subject='internal')
    admitted = AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal)
    denied = AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.NOT_INVITED)
    checker = SimpleNamespace(check=lambda value: admitted if value == 'known' else denied)
    path.touch(mode=0o600, exist_ok=True)
    currency = CurrencyRates(path, fetch=fetch, clock=clock) if enabled else None
    register_currency_route(app, currency=currency, checker=checker, internal={'internal'},
                            calls=PluginCalls(path, require_existing=True))
    return TestClient(app, headers={'Authorization': 'Bearer known'})


def test_currency_reuses_the_reference_snapshot_on_restart_and_reports_the_ecb_date(tmp_path):
    calls = []
    path = tmp_path / 'rates.sqlite'
    now = datetime(2026, 11, 23, 18, tzinfo=timezone.utc)

    def fetch():
        calls.append(now)
        return FEED

    expected = dict(version='CURRENCY.1', source='ECB', base='EUR', date='2026-11-23',
                    rates={'EUR': '1', 'CNY': '8.2157', 'USD': '1.1823'})
    with client(path, fetch, lambda: now) as app:
        assert app.post(ROUTE, json=REQUEST).json() == expected
    with client(path, fetch, lambda: now) as app:
        assert app.post(ROUTE, json=REQUEST).json() == expected
        assert len(calls) == 1
        now += timedelta(days=1)
        assert app.post(ROUTE, json=REQUEST).json() == expected
        assert len(calls) == 2


def test_invalid_provider_result_consumes_only_one_daily_fetch_and_does_not_return_stale_data(tmp_path):
    calls = []
    now = datetime(2026, 11, 23, 18, tzinfo=timezone.utc)

    def fetch():
        calls.append(now)
        if len(calls) == 1:
            return FEED
        raise PluginError(502, 'supplier_unavailable')

    with client(tmp_path / 'rates.sqlite', fetch, lambda: now) as app:
        assert app.post(ROUTE, json=REQUEST).status_code == 200
        now += timedelta(days=1)
        assert app.post(ROUTE, json=REQUEST).status_code == 502
        assert app.post(ROUTE, json=REQUEST).status_code == 503
        assert len(calls) == 2


def test_disabled_uninvited_and_invalid_requests_never_send_to_ecb(tmp_path):
    def unused():
        raise AssertionError('outbound request should not run')

    now = datetime(2026, 11, 23, 18, tzinfo=timezone.utc)
    path = tmp_path / 'rates.sqlite'
    with client(path, unused, lambda: now, enabled=False) as app:
        assert app.post(ROUTE, json=REQUEST).json() == {'error': 'not_enabled'}
    with client(path, unused, lambda: now) as app:
        assert app.post(ROUTE, json=REQUEST, headers={'Authorization': 'Bearer other'}).status_code == 403
        assert app.post(ROUTE, json=REQUEST | {'query': 'unexpected'}).status_code == 400


def test_currency_can_be_enabled_for_an_explicit_internal_subset():
    first, second, *_ = generate_plugin_subjects()
    assert configured_reference_subjects(json.dumps([first, second])) == {first, second}
    for roster in ([], [first, first], [first, 'outside-internal-roster']):
        with pytest.raises(ValueError):
            configured_reference_subjects(json.dumps(roster))
