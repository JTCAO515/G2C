"""HK wiring for MENU.1 (#1583): private worker socket, roster, 6 MiB photo body, nothing of the body in logs."""

from base64 import b64encode
from contextlib import contextmanager
from datetime import datetime
import importlib.util
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cj_api.lio_menu import ROUTE, MemoryMenuCache, MenuService
from cj_api.translation import MAX_MEDIA, supplier_unavailable
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.menu_budget import BEIJING, MenuBudget
from cj_usage.translation_budget import TranslationBudget
from deploy.hk import menu_relay
from deploy.hk.menu_relay import MAX_BODY, menu_request, menu_socket, register_menu_routes

_spec = importlib.util.spec_from_file_location('menu_fixtures', Path(__file__).with_name('test_lio_menu.py'))
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)

MARKER = b'\xff\xd8\xff\xe0' + b'PHOTO-MARKER-7d1c' + b'\x00' * 64


def checker():
    accepted = AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED,
                                 SimpleNamespace(issuer='internal-issuer', subject='internal'))
    denied = AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.NOT_INVITED)
    return SimpleNamespace(check=lambda token: accepted if token == 'synthetic' else denied)


@contextmanager
def relay(tmp_path, *, enabled=True, reader=None):
    ledger = AuthorizationBudget(tmp_path / 'shared', clock=lambda: datetime(2026, 11, 25, 19, tzinfo=BEIJING))
    reader, model = reader or fixtures.Reader(), fixtures.Model()
    service = (MenuService(reader, model, MenuBudget(ledger), TranslationBudget(ledger), MemoryMenuCache())
               if enabled else None)
    with TemporaryDirectory(prefix='g2c-menu-', dir='/tmp') as directory:
        path = Path(directory) / 'menu.sock'
        with menu_socket(service, checker(), {'internal'}, path=path, disabled=not enabled):
            app = FastAPI()
            register_menu_routes(app, send=lambda token, raw: menu_request(token, raw, path=path))
            with TestClient(app) as browser:
                yield browser, reader, model


AUTH = {'Authorization': 'Bearer synthetic'}


def test_a_menu_photo_is_explained_through_the_worker_with_the_callers_bearer(tmp_path):
    with relay(tmp_path) as (browser, reader, model):
        body = fixtures.payload()
        assert browser.post(ROUTE, json=body).status_code == 401
        assert browser.post(ROUTE, json=body, headers={'Authorization': 'Bearer unknown'}).status_code == 403
        assert reader.calls == [] and model.messages == []
        response = browser.post(ROUTE, json=body, headers=AUTH)
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        value = response.json()
        assert value['version'] == 'MENU.1' and value['truncated'] is False
        names = {item['name_zh']: item['price_text'] for item in value['items'] if item['kind'] == 'dish'}
        assert names['宫保鸡丁'] == '¥38' and names['蛋炒饭'] == '15/份'
        assert any(item['kind'] == 'unclear' for item in value['items'])
        assert (len(reader.calls), len(model.messages)) == (1, 1)
        # The same request id is spent in the journal: no second read, no second explanation.
        again = browser.post(ROUTE, json=body, headers=AUTH)
        assert (again.status_code, again.json()) == (409, {'error': 'request_already_used'})
        assert (len(reader.calls), len(model.messages)) == (1, 1)


def test_a_full_size_photo_fits_but_a_larger_body_is_refused_before_the_worker(tmp_path):
    with relay(tmp_path) as (browser, reader, model):
        photo = b'\xff\xd8\xff\xe0' + b'\x00' * (MAX_MEDIA - 4)
        body = fixtures.payload(photo)
        assert 4_000_000 < len(json.dumps(body).encode()) < MAX_BODY   # about 4 MB of base64
        assert browser.post(ROUTE, json=body, headers=AUTH).status_code == 200
        big = browser.post(ROUTE, content=b'{' + b' ' * MAX_BODY + b'}',
                           headers={**AUTH, 'Content-Type': 'application/json'})
        assert (big.status_code, big.json()) == (413, {'error': 'request_too_large'})
        assert len(reader.calls) == 1


def test_an_invalid_body_answers_a_fixed_code_and_never_logs_the_photo(tmp_path, caplog, capfd):
    caplog.set_level(logging.DEBUG)
    encoded = b64encode(MARKER).decode()
    with relay(tmp_path) as (browser, reader, model):
        extra = dict(fixtures.payload(MARKER), diet=['peanut'])
        response = browser.post(ROUTE, json=extra, headers=AUTH)
        assert (response.status_code, response.json()) == (400, {'error': 'invalid_request'})
        gif = dict(fixtures.payload(b'GIF89a' + b'PHOTO-MARKER-7d1c' * 4))
        response = browser.post(ROUTE, json=gif, headers=AUTH)
        assert (response.status_code, response.json()) == (400, {'error': 'invalid_request'})
        assert browser.post(ROUTE, content=b'not json', headers={**AUTH, 'Content-Type': 'application/json'}
                            ).status_code == 400
        assert reader.calls == [] and model.messages == []
    out, err = capfd.readouterr()
    logged = caplog.text + out + err
    assert encoded[:24] not in logged and 'PHOTO-MARKER' not in logged


def test_unsafe_recognised_text_is_a_supplier_error_without_an_explanation(tmp_path):
    class Unsafe(fixtures.Reader):
        def require_safe_text(self, value):
            raise supplier_unavailable()

    with relay(tmp_path, reader=Unsafe()) as (browser, reader, model):
        response = browser.post(ROUTE, json=fixtures.payload(), headers=AUTH)
        assert (response.status_code, response.json()) == (502, {'error': 'supplier_unavailable'})
        assert len(reader.calls) == 1 and model.messages == []


def test_closed_relay_answers_not_enabled_and_unreachable_worker_unavailable(tmp_path):
    with relay(tmp_path, enabled=False) as (browser, reader, model):
        response = browser.post(ROUTE, json=fixtures.payload(), headers=AUTH)
        assert (response.status_code, response.json()) == (403, {'error': 'not_enabled'})
    assert reader.calls == [] and model.messages == []
    app = FastAPI()
    register_menu_routes(app, send=lambda token, raw: menu_request(token, raw, path=tmp_path / 'missing.sock'))
    with TestClient(app) as browser:
        response = browser.post(ROUTE, json=fixtures.payload(), headers=AUTH)
        assert (response.status_code, response.json()) == (503, {'error': 'unavailable'})


def _menu_roster(monkeypatch, subjects):
    opened = []

    @contextmanager
    def socket(service, checker, roster, *, disabled):
        opened.append((service, checker, roster, disabled))
        yield

    if subjects is None:
        monkeypatch.delenv(menu_relay.MENU_INTERNAL_SUBJECTS, raising=False)
    else:
        monkeypatch.setenv(menu_relay.MENU_INTERNAL_SUBJECTS, json.dumps(subjects))
    monkeypatch.setenv('CJ_MODEL_API_KEY', 'fixture-model-key')
    monkeypatch.setattr(menu_relay, 'AuthorizationBudget', lambda *args, **kwargs: object())
    monkeypatch.setattr(menu_relay, 'account_checker_for',
                        lambda auth, database, *, selected_subjects: ('checker', selected_subjects))
    monkeypatch.setattr(menu_relay, 'menu_socket', socket)
    with menu_relay.active_menu(SimpleNamespace(auth=object(), database=lambda: object()), None):
        pass
    (service, checker, roster, disabled), = opened
    return service, checker, roster, disabled


def test_menu_accepts_the_authorized_cohort_with_both_budgets(monkeypatch):
    from deploy.hk.plugin_roster import generate_plugin_subjects

    cohort = generate_plugin_subjects()
    for subjects in (cohort, cohort[:1]):
        service, checker, roster, disabled = _menu_roster(monkeypatch, subjects)
        assert service is not None and not disabled
        assert isinstance(service.budget, MenuBudget) and isinstance(service.image_budget, TranslationBudget)
        assert isinstance(service.cache, MemoryMenuCache)
        assert roster == frozenset(subjects) and checker == ('checker', frozenset(subjects))
    assert _menu_roster(monkeypatch, None) == (None, None, frozenset(), True)


@pytest.mark.parametrize('subjects', [[], 'not-a-list', ['outside-the-internal-cohort'], 'cohort+outside',
                                      'cohort+duplicate', [7]])
def test_menu_refuses_rosters_outside_the_authorized_cohort(monkeypatch, subjects):
    from deploy.hk.demo_login import invitation_subject

    cohort = menu_relay.generate_plugin_subjects()
    subjects = {'cohort+outside': [*cohort, invitation_subject('CJ_Tester@01')],
                'cohort+duplicate': [*cohort, cohort[0]]}.get(subjects, subjects) if type(subjects) is str else subjects

    def supplier_must_not_start(*args, **kwargs):
        pytest.fail('An unauthorized roster must be refused before supplier creation')

    monkeypatch.setattr(menu_relay, 'DashScopeTranslation', supplier_must_not_start)
    monkeypatch.setattr(menu_relay, 'DashScopeMenu', supplier_must_not_start)
    assert _menu_roster(monkeypatch, subjects)[:3] == (None, None, frozenset())


def test_the_worker_reads_the_menu_roster_from_its_secret_file():
    from deploy.hk import configuration
    import inspect

    assert menu_relay.MENU_INTERNAL_SUBJECTS == 'CJ_MENU_INTERNAL_SUBJECTS_JSON'
    assert 'MENU_INTERNAL_SUBJECTS' in inspect.getsource(configuration.load_secret_environment)
