from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cj_api.plugin_tools import PluginCalls, PluginError
from cj_api.taxi_tools import DiDiInformation, ESTIMATE, LINK, REVERSE_COUNT, SEARCH, TaxiService, register_taxi_routes
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal


AUTH = {'Authorization': 'Bearer internal'}
NOW = datetime(2026, 11, 20, 22, tzinfo=timezone.utc)
GCJ = dict(from_lat='39.916404',from_lng='116.410244',to_lat='39.916404',to_lng='116.410244')
FIXTURE_LINK = 'https://v.didi.cn/XvYQEWe?slat=39.916404&slng=116.410244&dlat=39.916404&dlng=116.410244'


def point(name=None):
    return dict(lat=39.915, lng=116.404, coordinate_system='WGS-84', name=name)


def payload():
    return dict(version='TAXI.1', origin=point('北京西站'), destination=point())


def check(token):
    if token in {'internal', 'internal-other', 'invited-external'}:
        principal = TrustedPrincipal('fixture-issuer', token, 'app', 1, 1, 2)
        return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal)
    return AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.IDENTITY_INVALID)


@pytest.fixture
def app_context(tmp_path):
    seen = []
    path = tmp_path / 'plugin-count.sqlite'

    def transport(tool, params):
        seen.append((tool, params))
        if tool == 'maps_textsearch':
            if params['keywords'] == '找不到':
                return {'content': [{'text': '[]'}]}
            return {'content': [{'text': json.dumps([
                dict(display_name='天安门', city='北京市', address='东长安街',
                     location=dict(lat=39.916404, lng=116.410244)),
                dict(display_name='跨城市结果', city='上海市', address='上海',
                     location=dict(lat=31.23, lng=121.47)),
            ])}]}
        if tool == 'taxi_estimate':
            return {'structuredContent': {'items': [{'productName': '快车', 'productCategory': '1',
                    'priceText': '约 20 元', 'private': 'excluded'}], 'traceId': 'fixture-trace'}}
        if tool == 'maps_regeocode':
            return {'content': [{'text': json.dumps({'display_name': '经核对的公共地点'})}]}
        return {'structuredContent': {'appLink': FIXTURE_LINK}}

    taxi = TaxiService(DiDiInformation(transport), clock=lambda: NOW)
    app = FastAPI()
    register_taxi_routes(app, taxi=taxi, checker=SimpleNamespace(check=check),
                         internal=frozenset({'internal', 'internal-other'}),
                         calls=PluginCalls(path, clock=lambda: NOW))
    with TestClient(app) as client:
        yield client, seen, path


def test_hong_kong_default_disabled():
    app = FastAPI()
    register_taxi_routes(app)
    with TestClient(app) as client:
        for route in (ESTIMATE, LINK, SEARCH):
            response = client.post(route, headers=AUTH, json=payload())
            assert response.status_code == 403
            assert response.json() == {'error': 'not_enabled'}
            assert response.headers['cache-control'] == 'no-store'


def test_search_calls_expected_city_and_normalized_coordinates(app_context):
    client, seen, _ = app_context
    body = dict(version='TAXI.1', city='Beijing', query=' 天安门 ', near=point())
    outside = client.post(SEARCH, headers={'Authorization': 'Bearer invited-external'}, json=body)
    assert outside.status_code == 403 and seen == []
    response = client.post(SEARCH, headers=AUTH, json=body)
    assert response.status_code == 200
    assert seen == [('maps_textsearch', dict(city='北京市', keywords='天安门', location='116.410244,39.916404'))]
    assert response.json() == dict(version='TAXI.1', items=[
        dict(name_zh='天安门', address_zh='东长安街', city='北京市', lat=39.916404, lng=116.410244,
             coordinate_system='GCJ-02')])
    no_match = client.post(SEARCH, headers=AUTH, json=dict(version='TAXI.1', city='北京', query='找不到'))
    assert no_match.json() == dict(version='TAXI.1', items=[])


def test_fixture_estimate_and_link_allow_no_identity_fields(app_context):
    client, seen, _ = app_context
    body = payload()
    body['origin']['name'] = '未验证的客户端文本'
    response = client.post(ESTIMATE, headers=AUTH, json=body)
    assert response.status_code == 200
    assert response.json() == {'version': 'TAXI.1',
                               'vehicles': [{'category': '1', 'name': '快车', 'currency': 'CNY',
                                             'price_display': '约 20 元'}],
                               'trace_id': 'fixture-trace', 'observed_at': NOW.isoformat()}
    response = client.post(LINK, headers=AUTH, json=dict(payload(), vehicle_category='1'))
    assert response.json() == {'version': 'TAXI.1', 'url': FIXTURE_LINK, 'link_type': 'https'}
    assert seen == [
        ('maps_regeocode', dict(location='116.410244,39.916404')),
        ('maps_regeocode', dict(location='116.410244,39.916404')),
        ('taxi_estimate', dict(GCJ, from_name='经核对的公共地点', to_name='经核对的公共地点')),
        ('taxi_generate_ride_app_link', GCJ),
    ]


@pytest.mark.parametrize('method', ['taxi_create_order', 'taxi_cancel_order', 'taxi_query_order',
                                    'taxi_get_driver_location', 'maps_unknown'])
def test_only_fixed_information_tools_can_be_dispatched(method):
    seen = []
    provider = DiDiInformation(lambda *args: seen.append(args))
    with pytest.raises(ValueError):
        provider.call(method, {})
    assert seen == []


@pytest.mark.parametrize(('headers', 'data', 'status', 'error'), [
    ({}, payload(), 401, 'sign_in_required'),
    ({'Authorization': 'Bearer invented'}, payload(), 401, 'sign_in_required'),
    ({'Authorization': 'Bearer invited-external'}, payload(), 403, 'not_enabled'),
    (AUTH, dict(payload(), subject='internal-other'), 400, 'invalid_request'),
    (AUTH, dict(payload(), origin=dict(point(), coordinate_system='BD-09')), 400, 'invalid_request'),
    (AUTH, dict(payload(), origin=dict(point(), lng=181)), 400, 'invalid_request'),
    (AUTH, dict(payload(), origin=dict(point(), lat=True)), 400, 'invalid_request'),
    (AUTH, dict(payload(), origin=dict(point(), phone='0000000')), 400, 'invalid_request'),
])
def test_auth_and_request_boundary_reject_before_supplier(app_context, headers, data, status, error):
    client, seen, path = app_context
    response = client.post(ESTIMATE, headers=headers, json=data)
    assert response.status_code == status
    assert response.json() == {'error': error}
    assert seen == []
    assert not path.exists()


def test_duplicate_and_oversized_bodies_rejected_without_dispatch(app_context):
    client, seen, path = app_context
    headers = dict(AUTH, **{'Content-Type': 'application/json'})
    raw = json.dumps(payload())[:-1] + ', "version": "TAXI.1"}'
    assert client.post(LINK, headers=headers, content=raw).status_code == 400
    assert client.post(LINK, headers=headers, content=' ' * 4097).status_code == 413
    assert seen == []
    assert not path.exists()


def test_per_account_per_route_quota_precedes_dispatch(app_context):
    client, seen, _ = app_context
    for _ in range(50):
        assert client.post(ESTIMATE, headers=AUTH, json=payload()).status_code == 200
    response = client.post(ESTIMATE, headers=AUTH, json=payload())
    assert response.status_code == 429
    assert response.json() == {'error': 'quota_exceeded'}
    assert [tool for tool, _ in seen].count('taxi_estimate') == 50
    assert client.post(LINK, headers=AUTH, json=payload()).status_code == 200
    assert client.post(ESTIMATE, headers={'Authorization': 'Bearer internal-other'},
                       json=payload()).status_code == 200


def test_count_atomic_at_boundary_and_resets_at_shanghai_midnight(tmp_path):
    path = tmp_path / 'calls.sqlite'
    owner = check('internal').principal
    before = datetime(2026, 11, 20, 15, 59, tzinfo=timezone.utc)
    after = datetime(2026, 11, 20, 16, tzinfo=timezone.utc)
    old = PluginCalls(path, clock=lambda: before)
    for _ in range(49):
        old.reserve(owner, ESTIMATE, 50)

    def reserve(_):
        try:
            PluginCalls(path, clock=lambda: before).reserve(owner, ESTIMATE, 50)
        except PluginError as error:
            return error.code
        return 'accepted'

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(reserve, range(2))) == ['accepted', 'quota_exceeded']
    PluginCalls(path, clock=lambda: after).reserve(owner, ESTIMATE, 50)


def test_upstream_error_mapping_does_not_echo_provider_message():
    provider = DiDiInformation(lambda *_: {'error': {'code': -32001, 'message': 'private'}}, wait=lambda _: None)
    with pytest.raises(PluginError, match='^rate_limited$') as raised:
        provider.call('taxi_estimate', {})
    assert raised.value.status == 429

    def timeout(*_):
        raise TimeoutError('private request URL')

    with pytest.raises(PluginError, match='^supplier_timeout$') as raised:
        DiDiInformation(timeout).call('taxi_estimate', {})
    assert raised.value.status == 504


@pytest.mark.parametrize('link', [
    FIXTURE_LINK.replace('v.didi.cn', 'v.didi.cn.evil.test'),
    FIXTURE_LINK.replace('v.didi.cn', 'x@v.didi.cn'),
    FIXTURE_LINK.replace('v.didi.cn', 'v.didi.cn:443'),
    FIXTURE_LINK.replace('https:', 'http:'),
    FIXTURE_LINK + '&opaque=private',
    FIXTURE_LINK + '#private',
    FIXTURE_LINK.replace('/XvYQEWe', '/XvYQEWe/private'),
    FIXTURE_LINK + '&%6bey=fixture',
    FIXTURE_LINK + '&slat=39.916404',
    FIXTURE_LINK.replace('dlng=116.410244', 'dlng=116.4102'),
])
def test_unapproved_provider_link_is_never_forwarded(link):
    from cj_api.taxi_tools import _public_link

    with pytest.raises(PluginError, match='^supplier_unavailable$'):
        _public_link(link, GCJ)



def test_counter_open_failure_has_stable_error(tmp_path):
    calls = PluginCalls(tmp_path / 'missing' / 'counts.sqlite', clock=lambda: NOW)
    with pytest.raises(PluginError, match='^unavailable$') as raised:
        calls.reserve(check('internal').principal, ESTIMATE, 50)
    assert raised.value.status == 503


@pytest.mark.parametrize(('lng', 'lat'), [
    (114.164, 22.308), (113.546, 22.19), (121.565, 25.033), (139.6917, 35.6895),
])
@pytest.mark.parametrize('route', [ESTIMATE, LINK])
@pytest.mark.parametrize('coordinate_system', ['WGS-84', 'GCJ-02'])
def test_non_mainland_destination_stops_before_any_didi_call(app_context, lng, lat, route, coordinate_system):
    client, seen, _ = app_context
    destination = dict(point(), lng=lng, lat=lat, coordinate_system=coordinate_system)
    result = client.post(route, headers=AUTH, json=dict(payload(), destination=destination))
    assert result.status_code == 422
    assert result.json() == {'error': 'out_of_service_area'}
    assert seen == []


def test_verified_gcj_input_is_passed_through_once(app_context):
    client, seen, _ = app_context
    body = payload()
    body['origin'] = dict(body['origin'], lng=116.410244, lat=39.916404, coordinate_system='GCJ-02')
    body['destination'] = dict(body['destination'], lng=116.410244, lat=39.916404, coordinate_system='GCJ-02')
    assert client.post(LINK, headers=AUTH, json=body).status_code == 200
    assert seen == [('taxi_generate_ride_app_link', GCJ)]


def test_unknown_reverse_name_rejects_before_estimate():
    from cj_api.taxi_tools import EstimateRequest

    calls = []
    def send(tool, params):
        calls.append(tool)
        return {'content': [{'text': '{"display_name": ""}'}]}
    with pytest.raises(PluginError, match='^coordinate_unverified$'):
        TaxiService(DiDiInformation(send)).estimate(EstimateRequest.model_validate(payload()), lambda *args: None)
    assert calls == ['maps_regeocode']


@pytest.mark.parametrize(('code', 'status', 'kind'), [
    (-32002, 502, 'supplier_unavailable'), (-32010, 400, 'invalid_request'),
    (-32050, 502, 'supplier_unavailable'),
])
def test_supplier_rpc_failure_remains_bounded_and_redacted(code, status, kind, caplog):
    provider = DiDiInformation(lambda *_: {'error': {'code': code, 'message': 'private-path'}})
    with pytest.raises(PluginError, match=f'^{kind}$') as raised:
        provider.call('taxi_estimate', {})
    assert raised.value.status == status
    assert 'private-path' not in caplog.text
    assert ('didi_key_rejected' in caplog.text) is (code == -32002)


def test_provider_rate_limit_waits_and_retries_once():
    seen = []
    def dispatch(tool, params):
        seen.append((tool, params))
        return {'error': {'code': -32001}}
    waits = []
    provider = DiDiInformation(dispatch, wait=waits.append)
    with pytest.raises(PluginError, match='^rate_limited$'):
        provider.call('taxi_estimate', {'from_name': '北京市'})
    assert waits == [0.25]
    assert seen == [('taxi_estimate', {'from_name': '北京市'})] * 2


def test_expired_link_refreshes_the_named_estimate_only_once():
    from cj_api.taxi_tools import LinkRequest

    calls = []
    def dispatch(tool, params):
        calls.append(tool)
        if tool == 'taxi_generate_ride_app_link':
            if calls.count(tool) == 1:
                return {'error': {'code': -32021}}
            return {'structuredContent': {'appLink': FIXTURE_LINK}}
        if tool == 'maps_regeocode':
            return {'content': [{'text': '{"display_name":"北京地点"}'}]}
        return {'structuredContent': {}}

    reservations = []
    result = TaxiService(DiDiInformation(dispatch)).link(
        LinkRequest.model_validate(payload()), lambda operation, limit: reservations.append((operation, limit)))
    assert result['url'] == FIXTURE_LINK
    assert calls == ['taxi_generate_ride_app_link', 'maps_regeocode', 'maps_regeocode',
                     'taxi_estimate', 'taxi_generate_ride_app_link']
    assert reservations == [(ESTIMATE,50), (REVERSE_COUNT,None), (REVERSE_COUNT,None), (LINK,50)]


def test_live_counter_never_recreates_a_missing_quota_journal(tmp_path):
    path = tmp_path/'taxi.sqlite'
    path.touch(mode=0o600)
    calls = PluginCalls(path,clock=lambda:NOW,require_existing=True)
    owner = check('internal').principal
    calls.reserve(owner,ESTIMATE,50)
    path.unlink()
    with pytest.raises(PluginError, match='^unavailable$') as rejected:
        calls.reserve(owner,ESTIMATE,50)
    assert rejected.value.status==503
    assert not path.exists()


def test_runtime_roster_and_original_counter_gate_provider_dispatch(monkeypatch, tmp_path):
    from deploy.hk import taxi_runtime
    from deploy.hk.configuration import DIDI_MCP_KEY, TAXI_INTERNAL_SUBJECTS
    from deploy.hk.demo_login import invitation_subject
    from deploy.hk.plugin_roster import generate_plugin_subjects

    subjects = generate_plugin_subjects()
    allowed, excluded = subjects[0], invitation_subject(f'CJ_Tester@{1:02d}')
    parent = tmp_path/'plugin-state'
    parent.mkdir(mode=0o700)
    database = parent/'taxi.sqlite'
    database.touch(mode=0o600)
    monkeypatch.setenv(DIDI_MCP_KEY, 'fixture-key')
    monkeypatch.setenv(TAXI_INTERNAL_SUBJECTS, json.dumps(subjects))
    seen = []

    def account_checker(auth, db, *, selected_subjects):
        assert selected_subjects == frozenset(subjects)
        def admit(token):
            subject = {'inside-fixture': allowed, 'outside-fixture': excluded}[token]
            principal = TrustedPrincipal('fixture-issuer', subject, 'app', 1, 1, 2)
            return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal)
        return SimpleNamespace(check=admit)

    def dispatch(tool, params):
        seen.append(tool)
        if tool == 'maps_regeocode':
            return {'content': [{'text': '{"display_name":"核实地点"}'}]}
        return {'structuredContent': {'items': [
            {'productName': '快车', 'productCategory': '1', 'priceText': '20 元'},
        ]}}

    monkeypatch.setattr(taxi_runtime, 'account_checker_for', account_checker)
    monkeypatch.setattr(taxi_runtime, 'DiDiMCPTransport', lambda key: dispatch)
    app = FastAPI()
    taxi_runtime.register_runtime_taxi(app, object(), object(), counts_path=database)
    body = payload()
    body['destination']['name'] = '西二旗地铁站'

    def call(client, token):
        return client.post(ESTIMATE, headers={'Authorization': 'Bearer '+token}, json=body)

    with TestClient(app) as client:
        assert call(client, 'outside-fixture').status_code == 403
        assert not seen
        assert call(client, 'inside-fixture').status_code == 200
        assert seen == ['maps_regeocode','maps_regeocode','taxi_estimate']
        database.unlink()
        denied = call(client, 'inside-fixture')
        assert denied.status_code == 503
        assert denied.json() == {'error': 'unavailable'}
        assert seen == ['maps_regeocode','maps_regeocode','taxi_estimate']
        assert not database.exists()



@pytest.mark.parametrize(('route', 'rpc_error', 'estimate_count', 'expected_calls'), [
    (ESTIMATE, -32001, 49, ['maps_regeocode','maps_regeocode','taxi_estimate']),
    (ESTIMATE, -32021, 49, ['maps_regeocode','maps_regeocode','taxi_estimate']),
    (LINK, -32021, 50, ['taxi_generate_ride_app_link']),
])
def test_additional_supplier_call_cannot_exceed_the_original_estimate_quota(
        tmp_path, route, rpc_error, estimate_count, expected_calls):
    calls = PluginCalls(tmp_path/'counter.sqlite', clock=lambda: NOW)
    owner = check('internal').principal
    seen = []
    for _ in range(estimate_count):
        calls.reserve(owner, ESTIMATE, 50)

    def transport(tool, params):
        seen.append(tool)
        if tool == 'maps_regeocode':
            return {'content': [{'text': '{"display_name": "核实地点"}'}]}
        return {'error': {'code': rpc_error}}

    service = TaxiService(DiDiInformation(transport, wait=lambda _: None))
    app=FastAPI()
    register_taxi_routes(app, taxi=service, checker=SimpleNamespace(check=check),
                         internal=frozenset({'internal'}), calls=calls)
    with TestClient(app) as client:
        error = client.post(route, headers=AUTH, json=payload())
    assert error.status_code == 429
    assert error.json() == {'error': 'quota_exceeded'}
    assert seen == expected_calls
