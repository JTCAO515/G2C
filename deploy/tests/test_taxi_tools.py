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


# --- TAXI.1 search red-line negatives (#1422 post-merge review) ---

def search_body(**other):
    return dict(dict(version='TAXI.1', city='北京', query='天安门'), **other)


def search_client(tmp_path, transport, *, wait=lambda _: None):
    path = tmp_path / 'search-count.sqlite'
    app = FastAPI()
    register_taxi_routes(app, taxi=TaxiService(DiDiInformation(transport, wait=wait), clock=lambda: NOW),
                         checker=SimpleNamespace(check=check), internal=frozenset({'internal'}),
                         calls=PluginCalls(path, clock=lambda: NOW))
    return TestClient(app), path


def used(path):
    import sqlite3
    if not path.exists():
        return {}
    with sqlite3.connect(path) as db:
        return dict(db.execute('SELECT operation, used FROM plugin_call'))


def row(name='天安门', city='北京市', lat=39.916404, lng=116.410244, **other):
    return dict(dict(display_name=name, city=city, address='东长安街', location=dict(lat=lat, lng=lng)), **other)


def rows_reply(rows):
    return {'content': [{'text': json.dumps(rows, ensure_ascii=False)}]}


def test_search_route_quota_is_enforced_before_dispatch(tmp_path):
    seen = []
    client, path = search_client(tmp_path, lambda tool, params: seen.append(tool) or rows_reply([row()]))
    with client:
        for _ in range(50):
            assert client.post(SEARCH, headers=AUTH, json=search_body()).status_code == 200
        response = client.post(SEARCH, headers=AUTH, json=search_body())
    assert response.status_code == 429
    assert response.json() == {'error': 'quota_exceeded'}
    assert seen.count('maps_textsearch') == 50
    assert used(path) == {SEARCH: 50, 'didi:maps_textsearch': 50}


@pytest.mark.parametrize(('failure', 'status', 'error'), [
    (TimeoutError('private url'), 504, 'supplier_timeout'),
    (OSError('private url'), 502, 'supplier_unavailable'),
    ({'error': {'code': -32050, 'message': 'private'}}, 502, 'supplier_unavailable'),
    ({'error': {'code': -32002, 'message': 'private'}}, 502, 'supplier_unavailable'),
    ({'error': {'code': -32010, 'message': 'private'}}, 400, 'invalid_request'),
    ({'error': {'code': -32001, 'message': 'private'}}, 429, 'rate_limited'),
    ({'error': {'code': -32021, 'message': 'private'}}, 502, 'supplier_unavailable'),
    ({'isError': True, 'content': []}, 502, 'supplier_unavailable'),
    ({'content': [{'text': 'not json'}]}, 502, 'supplier_unavailable'),
])
def test_search_supplier_failures_map_once_and_still_count(tmp_path, failure, status, error):
    seen, waits = [], []

    def transport(tool, params):
        seen.append(tool)
        if isinstance(failure, Exception):
            raise failure
        return failure

    client, path = search_client(tmp_path, transport, wait=waits.append)
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body())
    assert (response.status_code, response.json()) == (status, {'error': error})
    assert 'private' not in response.text
    assert seen == ['maps_textsearch'] and waits == []
    assert used(path) == {SEARCH: 1, 'didi:maps_textsearch': 1}


@pytest.mark.parametrize('data', [
    search_body(subject='internal-other'),
    search_body(near=dict(point(), phone='0000000')),
    search_body(version='TAXI.2'),
    search_body(city='Paris'),
    search_body(city='北京1'),
    search_body(city='   '),
    search_body(city='北'),
    search_body(query=''),
    search_body(query='   '),
    search_body(query='x' * 101),
    search_body(query=7),
    search_body(query='天安\x00门'),
    search_body(query='天安\x7f门'),
    search_body(query='天安\x85门'),
    search_body(query='天安\u202e门'),
    search_body(query='天安\u2066门'),
    search_body(near=dict(point(), lng=181)),
    search_body(near=dict(point(), lat='39.9')),
    search_body(near=dict(point(), coordinate_system='BD-09')),
    search_body(near=dict(point(), name='名\u202e称')),
])
def test_search_request_boundary_rejects_before_any_count_or_dispatch(tmp_path, data):
    seen = []
    client, path = search_client(tmp_path, lambda tool, params: seen.append(tool))
    with client:
        response = client.post(SEARCH, headers=AUTH, json=data)
    assert (response.status_code, response.json()) == (400, {'error': 'invalid_request'})
    assert seen == [] and used(path) == {}


@pytest.mark.parametrize(('lng', 'lat'), [(114.164, 22.308), (139.6917, 35.6895), (121.565, 25.033)])
def test_search_near_outside_service_area_stops_before_didi(tmp_path, lng, lat):
    seen = []
    client, path = search_client(tmp_path, lambda tool, params: seen.append(tool))
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body(near=dict(point(), lng=lng, lat=lat)))
    assert (response.status_code, response.json()) == (422, {'error': 'out_of_service_area'})
    assert seen == [] and used(path) == {SEARCH: 1}


@pytest.mark.parametrize('city', ['香港', '香港特别行政区', '澳门', '澳門', '台北', '臺北市', '台湾', 'Hong Kong',
                                  'hongkong', 'Macau', 'Taipei', '花莲', '花蓮縣', '台东', '屏东', '宜兰', '苗栗',
                                  '彰化', '南投', '云林', '雲林', '澎湖', '金门', '金門', '中国台湾',
                                  '中国香港', '中國澳門', '中国台北市'])
def test_search_non_mainland_city_is_out_of_service_and_never_sent(tmp_path, city):
    seen = []
    client, path = search_client(tmp_path, lambda tool, params: seen.append((tool, params)))
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body(city=city))
    assert (response.status_code, response.json()) == (422, {'error': 'out_of_service_area'})
    assert seen == [] and used(path) == {SEARCH: 1}


@pytest.mark.parametrize('city', ['台州', '台山', '南京', '中山', '金华', '连云港', '花都', '连江'])
def test_search_mainland_cities_sharing_a_prefix_are_still_sent(tmp_path, city):
    seen = []
    client, _ = search_client(tmp_path, lambda tool, params: seen.append(params) or rows_reply([]))
    with client:
        assert client.post(SEARCH, headers=AUTH, json=search_body(city=city)).status_code == 200
    assert seen == [dict(keywords='天安门', city=city + '市')]


def test_search_with_only_other_city_or_non_mainland_results_is_empty_not_502(tmp_path):
    rows = [row('外滩', '上海市', 31.24, 121.49), row('维多利亚港', '香港', 22.29, 114.17),
            row('假北京', '北京市', 22.29, 114.17)]
    client, _ = search_client(tmp_path, lambda tool, params: rows_reply(rows))
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body())
    assert (response.status_code, response.json()) == (200, dict(version='TAXI.1', items=[]))


def test_search_with_only_malformed_results_is_supplier_error(tmp_path):
    rows = [dict(display_name='天安门', city='北京市'), row(lat=None), row(name='天安\u202e门'), 'x',
            row(name=None), row(name=7), row(name=''), row(city=None)]
    client, _ = search_client(tmp_path, lambda tool, params: rows_reply(rows))
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body())
    assert (response.status_code, response.json()) == (502, {'error': 'supplier_unavailable'})


def test_search_accepts_numeric_string_coordinates_and_drops_unsafe_addresses(tmp_path):
    rows = [row(lat='39.916404', lng='116.410244'), row('故宫', lat='39.9', lng='1e2'),
            row('景山', lat=39.92, lng=116.39, address='景山\u202e前街'),
            row('北海', lat=39.93, lng=116.38, address='北海\x85公园')]
    client, _ = search_client(tmp_path, lambda tool, params: rows_reply(rows))
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body())
    assert response.status_code == 200
    assert response.json()['items'] == [
        dict(name_zh='天安门', address_zh='东长安街', city='北京市', lat=39.916404, lng=116.410244,
             coordinate_system='GCJ-02'),
        dict(name_zh='景山', address_zh=None, city='北京市', lat=39.92, lng=116.39, coordinate_system='GCJ-02'),
        dict(name_zh='北海', address_zh=None, city='北京市', lat=39.93, lng=116.38, coordinate_system='GCJ-02'),
    ]


def test_search_sends_only_keyword_city_and_optional_point(tmp_path):
    seen = []
    client, _ = search_client(tmp_path, lambda tool, params: seen.append((tool, params)) or rows_reply([]))
    with client:
        assert client.post(SEARCH, headers=AUTH, json=search_body(city='Chengdu', query='宽窄巷子')).status_code == 200
        assert client.post(SEARCH, headers=AUTH, json=search_body(city='上海市', query='外滩')).status_code == 200
    assert seen == [('maps_textsearch', dict(keywords='宽窄巷子', city='成都市')),
                    ('maps_textsearch', dict(keywords='外滩', city='上海市'))]


def test_search_drops_null_names_and_keeps_usable_rows(tmp_path):
    rows = [row(name=None), row(name='   '), row('故宫', lat=39.9163, lng=116.3972)]
    client, _ = search_client(tmp_path, lambda tool, params: rows_reply(rows))
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body())
    assert response.status_code == 200
    assert [item['name_zh'] for item in response.json()['items']] == ['故宫']


@pytest.mark.parametrize('name', ['\U0001f469\u200d\U0001f467 亲子乐园', 'Caf\u00e9\u00ad馆', '\ufeff北京西站'])
def test_estimate_keeps_accepting_names_with_harmless_format_characters(app_context, name):
    client, _, _ = app_context
    assert client.post(ESTIMATE, headers=AUTH, json=dict(payload(), origin=point(name))).status_code == 200


@pytest.mark.parametrize('name', ['北京\x7f西站', '北京\x85西站', '北京\u202e西站', '北京\u2067西站',
                                  '北京\u200f西站', '北京\u2028西站'])
def test_estimate_rejects_control_and_bidi_names(app_context, name):
    client, seen, _ = app_context
    response = client.post(ESTIMATE, headers=AUTH, json=dict(payload(), origin=point(name)))
    assert (response.status_code, response.json()) == (400, {'error': 'invalid_request'})
    assert seen == []


# --- TAXI.1 search English fields (#1450, M4 entry 9 amendment #1457) ---

class Translator:
    def __init__(self, reply=None, error=None):
        self.calls, self.reply, self.error = [], reply, error

    def __call__(self, token, text):
        self.calls.append((token, text))
        if self.error is not None:
            raise self.error
        if callable(self.reply):
            return self.reply(text)
        return self.reply


def english_lines(text):
    table = {'天安门': 'Tiananmen', '东长安街': 'East Chang\'an Avenue', '故宫': 'Palace Museum',
             '景山前街4号': 'No. 4 Jingshan Front Street'}
    out = []
    for line in text.split('\n'):
        number, _, source = line.partition('] ')
        out.append(number + '] ' + table.get(source, 'Unknown'))
    return '\n'.join(out)


def english_client(tmp_path, rows, translator):
    path = tmp_path / 'english-count.sqlite'
    app = FastAPI()
    register_taxi_routes(app, taxi=TaxiService(DiDiInformation(lambda tool, params: rows_reply(rows)),
                                               clock=lambda: NOW, translator=translator),
                         checker=SimpleNamespace(check=check), internal=frozenset({'internal'}),
                         calls=PluginCalls(path, clock=lambda: NOW))
    return TestClient(app), path


def test_search_in_english_adds_translated_fields_from_one_batch(tmp_path):
    translator = Translator(english_lines)
    rows = [row(), row('故宫', lat=39.9163, lng=116.3972, address='景山前街4号')]
    client, path = english_client(tmp_path, rows, translator)
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body(locale='en'))
        plain = client.post(SEARCH, headers=AUTH, json=search_body())
    assert response.status_code == 200
    assert response.json()['items'] == [
        dict(name_zh='天安门', address_zh='东长安街', city='北京市', lat=39.916404, lng=116.410244,
             coordinate_system='GCJ-02', name_en='Tiananmen', address_en="East Chang'an Avenue"),
        dict(name_zh='故宫', address_zh='景山前街4号', city='北京市', lat=39.9163, lng=116.3972,
             coordinate_system='GCJ-02', name_en='Palace Museum', address_en='No. 4 Jingshan Front Street')]
    assert translator.calls == [('internal', '[1] 天安门\n[2] 东长安街\n[3] 故宫\n[4] 景山前街4号')]
    assert all('name_en' not in item and 'address_en' not in item for item in plain.json()['items'])
    assert used(path) == {SEARCH: 2, 'didi:maps_textsearch': 2}


def test_search_english_reuses_cached_places_and_translates_only_new_ones(tmp_path):
    translator = Translator(english_lines)
    state = {'rows': [row()]}
    path = tmp_path / 'english-count.sqlite'
    app = FastAPI()
    register_taxi_routes(app, taxi=TaxiService(DiDiInformation(lambda tool, params: rows_reply(state['rows'])),
                                               clock=lambda: NOW, translator=translator),
                         checker=SimpleNamespace(check=check), internal=frozenset({'internal'}),
                         calls=PluginCalls(path, clock=lambda: NOW))
    with TestClient(app) as client:
        assert client.post(SEARCH, headers=AUTH, json=search_body(locale='en')).status_code == 200
        state['rows'] = [row(), row('故宫', lat=39.9163, lng=116.3972, address=None)]
        second = client.post(SEARCH, headers=AUTH, json=search_body(locale='en')).json()['items']
        third = client.post(SEARCH, headers=AUTH, json=search_body(locale='en')).json()['items']
    assert translator.calls == [('internal', '[1] 天安门\n[2] 东长安街'), ('internal', '[1] 故宫')]
    assert second == third
    assert second[1]['name_en'] == 'Palace Museum' and 'address_en' not in second[1]


PARTIAL = ('[1] Tiananmen\n[2] 东长安街', '[1] Tiananmen\n[2] East\u202eAvenue', '[1] Tiananmen\n[2] ' + 'x' * 201,
           '[1] Tiananmen\n[2]    ', '[1] Tiananmen\n[2] East \U00020000 Avenue', '[1] Tiananmen\n[2] East\u3001Avenue')


@pytest.mark.parametrize('translator', [
    Translator(None),
    Translator(error=OSError('socket down')),
    Translator(error=ValueError('bad reply')),
    Translator('[1] Tiananmen'),
    Translator('Tiananmen\nEast Avenue'),
    Translator('[2] Tiananmen\n[1] East Avenue'),
    Translator('[1] Tiananmen\n[1] East Avenue'),
    *(Translator(reply) for reply in PARTIAL),
])
def test_search_english_failure_omits_only_the_affected_fields(tmp_path, translator):
    client, path = english_client(tmp_path, [row()], translator)
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body(locale='en'))
    assert response.status_code == 200
    item = response.json()['items'][0]
    assert item['name_zh'] == '天安门' and item['address_zh'] == '东长安街'
    if translator.reply in PARTIAL:
        assert item['name_en'] == 'Tiananmen' and 'address_en' not in item
    else:
        assert 'name_en' not in item and 'address_en' not in item
    assert used(path) == {SEARCH: 1, 'didi:maps_textsearch': 1}


def test_search_english_without_translator_or_results_never_calls_translation(tmp_path):
    translator = Translator(english_lines)
    client, _ = english_client(tmp_path, [], translator)
    with client:
        assert client.post(SEARCH, headers=AUTH, json=search_body(locale='en')).json()['items'] == []
    assert translator.calls == []
    (tmp_path / 'plain').mkdir()
    plain, _ = search_client(tmp_path / 'plain', lambda tool, params: rows_reply([row()]))
    with plain:
        item = plain.post(SEARCH, headers=AUTH, json=search_body(locale='en')).json()['items'][0]
    assert 'name_en' not in item


@pytest.mark.parametrize('locale', ['EN', 'fr', '', None, 1])
def test_search_rejects_unknown_locale_before_dispatch(tmp_path, locale):
    seen = []
    client, path = search_client(tmp_path, lambda tool, params: seen.append(tool))
    with client:
        response = client.post(SEARCH, headers=AUTH, json=search_body(locale=locale))
    assert (response.status_code, response.json()) == (400, {'error': 'invalid_request'})
    assert seen == [] and used(path) == {}


def test_search_english_batch_stays_within_the_translation_text_limit(tmp_path):
    long_address = '路' * 240
    rows = [row(f'地点{n:02d}', lat=39.9 + n / 1000, address=long_address) for n in range(20)]
    translator = Translator(lambda text: '\n'.join(line.partition('] ')[0] + '] Place' for line in text.split('\n')))
    client, _ = english_client(tmp_path, rows, translator)
    with client:
        items = client.post(SEARCH, headers=AUTH, json=search_body(locale='en')).json()['items']
    (_, text), = translator.calls
    assert len(text) <= 1500
    translated = [item for item in items if 'name_en' in item]
    assert translated and len(translated) < 20 and translated == items[:len(translated)]


def test_runtime_translator_uses_the_metered_translation_relay(monkeypatch):
    from deploy.hk import taxi_runtime

    sent = []

    def reply(status, body):
        def send(token, raw, *, timeout):
            sent.append((token, json.loads(raw), timeout))
            return status, body
        return send

    ok = dict(version='TRANSLATION.1', kind='text', items=[dict(source_text='天安门', translated_text='Tiananmen')])
    assert taxi_runtime.relay_translator(reply(200, ok))('internal', '天安门') == 'Tiananmen'
    (token, request, timeout), = sent
    assert token == 'internal' and timeout == taxi_runtime.TRANSLATION_TIMEOUT <= 15
    assert set(request) == {'version', 'request_id', 'kind', 'source_lang', 'target_lang', 'text'}
    assert (request['version'], request['kind'], request['source_lang'], request['target_lang'], request['text']) == (
        'TRANSLATION.1', 'text', 'zh', 'en', '天安门')
    assert len(request['request_id']) == 36
    for status, body in ((429, {'error': 'quota_exceeded'}), (403, {'error': 'not_enabled'}),
                         (200, dict(ok, version='TRANSLATION.2')),
                         (200, dict(ok, items=[dict(source_text='故宫', translated_text='x')])),
                         (200, dict(ok, items=[])), (200, {})):
        assert taxi_runtime.relay_translator(reply(status, body))('internal', '天安门') is None


def test_runtime_taxi_search_is_wired_to_the_relay_translator(monkeypatch, tmp_path):
    from deploy.hk import taxi_runtime
    from deploy.hk.configuration import DIDI_MCP_KEY, TAXI_INTERNAL_SUBJECTS
    from deploy.hk.plugin_roster import generate_plugin_subjects

    parent = tmp_path / 'plugin-state'
    parent.mkdir(mode=0o700)
    database = parent / 'taxi.sqlite'
    database.touch(mode=0o600)
    monkeypatch.setenv(DIDI_MCP_KEY, 'fixture-key')
    monkeypatch.setenv(TAXI_INTERNAL_SUBJECTS, json.dumps(generate_plugin_subjects()))
    monkeypatch.setattr(taxi_runtime, 'account_checker_for', lambda *a, **k: SimpleNamespace(check=check))
    monkeypatch.setattr(taxi_runtime, 'DiDiMCPTransport', lambda key: (lambda tool, params: {}))
    built = []
    monkeypatch.setattr(taxi_runtime, 'TaxiService', lambda provider, **kwargs: built.append(kwargs) or
                        TaxiService(provider, **kwargs))
    taxi_runtime.register_runtime_taxi(FastAPI(), object(), object(), counts_path=database)
    (kwargs,) = built
    assert callable(kwargs['translator'])


def test_search_english_cut_off_items_still_use_their_cache(tmp_path):
    translator = Translator(lambda text: '\n'.join(line.partition('] ')[0] + '] Place' for line in text.split('\n')))
    long_rows = [row(f'地点{n:02d}', lat=39.9 + n / 1000, address='路' * 240) for n in range(19)]
    tail = row('故宫', lat=39.9163, lng=116.3972, address=None)
    state = {'rows': [tail]}
    path = tmp_path / 'english-count.sqlite'
    app = FastAPI()
    register_taxi_routes(app, taxi=TaxiService(DiDiInformation(lambda tool, params: rows_reply(state['rows'])),
                                               clock=lambda: NOW, translator=translator),
                         checker=SimpleNamespace(check=check), internal=frozenset({'internal'}),
                         calls=PluginCalls(path, clock=lambda: NOW))
    with TestClient(app) as client:
        assert client.post(SEARCH, headers=AUTH, json=search_body(locale='en')).status_code == 200
        state['rows'] = [*long_rows, tail]
        items = client.post(SEARCH, headers=AUTH, json=search_body(locale='en')).json()['items']
    assert items[-1]['name_zh'] == '故宫' and items[-1]['name_en'] == 'Place'
    assert '[1] 故宫' == translator.calls[0][1] and '故宫' not in translator.calls[1][1]


def test_pass_token_requires_provider_call_counting():
    from cj_api.plugin_tools import register_plugin
    with pytest.raises(ValueError):
        register_plugin(FastAPI(), '/fixture', object, lambda *args: None, enabled=False, checker=None,
                        internal=frozenset(), calls=None, limit=1, pass_token=True)
