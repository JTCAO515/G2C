"""#1771 operations console: roster, switches and route admission without a database."""
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from cj_api.ops_console_routes import PREFIX, register_ops_console_routes
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal
from cj_service_request.ops import FLAG, ROSTER, NotStaff, Roster, console_enabled
from cj_service_request.store import FLAG as SERVICE_FLAG, enabled

STAFF = {'issuer': 'https://local.g2c.invalid', 'subject': 'staff1', 'staff_ref': 'ops-test-01'}


def principal(subject):
    return TrustedPrincipal('https://local.g2c.invalid', subject, 'g2c-local', 1, 1, 2)


def test_switches_default_off():
    assert not console_enabled({}) and not console_enabled({FLAG: 'true'}) and console_enabled({FLAG: '1'})
    assert not enabled({}) and SERVICE_FLAG == 'CJ_SERVICE_REQUEST_ENABLED'


def test_roster(tmp_path):
    roster = Roster([STAFF])
    assert roster.staff_ref(principal('staff1')) == 'ops-test-01' and len(roster) == 1
    with pytest.raises(NotStaff):
        roster.staff_ref(principal('someone'))
    with pytest.raises(NotStaff):
        roster.staff_ref(TrustedPrincipal('https://other.invalid', 'staff1', 'g2c-local', 1, 1, 2))
    for bad in ([STAFF, dict(STAFF, staff_ref='x')], [STAFF, dict(STAFF, subject='s2')], [dict(STAFF, role='admin')],
                [dict(STAFF, subject=' staff1')], [dict(STAFF, staff_ref='')]):
        with pytest.raises(ValueError):
            Roster(bad)
    assert len(Roster.from_environment({})) == 0  # no configured roster: nobody is staff
    path = tmp_path / 'roster.json'
    path.write_text(json.dumps({'staff': [STAFF]}))
    assert len(Roster.from_environment({ROSTER: str(path)})) == 1
    path.write_text('{"staff":[],"staff":[]}')
    with pytest.raises(ValueError):
        Roster.from_file(path)


class Checker:
    def check(self, token):
        if token == 'staff-token':
            return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal('staff1'))
        if token == 'user-token':
            return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal('customer'))
        if token == 'unknown-token':
            return AdmissionDecision(AdmissionStatus.UNKNOWN, AdmissionReason.FACTS_UNKNOWN)
        return AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.IDENTITY_INVALID)


class Console:
    def __init__(self):
        self.calls = []

    def list_requests(self, ref):
        self.calls.append(('list', ref))
        return []

    def detail(self, ref, rid):
        self.calls.append(('view', ref, rid))
        return {'request_id': rid}


def client(switch):
    app = FastAPI()

    @app.middleware('http')
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        return await call_next(request)
    console = Console()
    register_ops_console_routes(app, Checker(), console, Roster([STAFF]), enabled=lambda: switch['on'])
    return TestClient(app), console


def test_route_admission():
    switch = {'on': True}
    http, console = client(switch)
    auth = lambda t: {'Authorization': 'Bearer ' + t}
    assert http.get(PREFIX, headers=auth('staff-token')).status_code == 200
    assert http.get(PREFIX + '/sr_x', headers=auth('staff-token')).json() == {'request_id': 'sr_x'}
    assert http.get(PREFIX, headers=auth('user-token')).status_code == 403
    assert http.get(PREFIX, headers=auth('bad')).status_code == 401
    assert http.get(PREFIX).status_code == 401
    assert http.get(PREFIX, headers=auth('unknown-token')).status_code == 503
    assert http.post(PREFIX + '/sr_x/transitions', headers=auth('staff-token'), content=b'[]').status_code == 400
    switch['on'] = False
    assert http.get(PREFIX, headers=auth('staff-token')).status_code == 404
    assert console.calls == [('list', 'ops-test-01'), ('view', 'ops-test-01', 'sr_x')]


def test_composition_requires_both_parts():
    from cj_api import composition
    with pytest.raises(composition.CompositionUnavailable):
        composition.create_composed_app(environment='local', jwt_configuration=None, verification_keys=None,
                                        access_provider=None, resolve_repository=None, new_run_id=lambda: 'r',
                                        max_body_bytes=1, ops_console=SimpleNamespace())
