from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from deploy.hk import readiness_monitor as monitor


def test_checks_only_two_public_routes_in_order():
    fetch = Mock(side_effect=lambda route, expected: dict(route=route, status=200))
    value, code = monitor.run(datetime(2026, 11, 17, 9, tzinfo=timezone.utc), fetch)
    assert code == 0 and value['state'] == 'PUBLIC_HEALTH_OBSERVED'
    assert fetch.call_args_list == [
        (('/health/live', 'alive'),), (('/health/ready', 'ready'),)]
    assert value['business_requests'] == value['provider_calls'] == 0


@pytest.mark.parametrize('hour,state', [(14, 'PUBLIC_HEALTH_OBSERVED'),
    (15, 'SKIPPED_QUIET_HOURS'), (23, 'SKIPPED_QUIET_HOURS'),
    (0, 'PUBLIC_HEALTH_OBSERVED')])
def test_actual_start_time_checks_beijing_quiet_hours(hour, state):
    fetch = Mock(return_value={})
    value, code = monitor.run(datetime(2026, 11, 17, hour, tzinfo=timezone.utc), fetch)
    assert value['state'] == state and code == 0
    assert fetch.call_count == (2 if state == 'PUBLIC_HEALTH_OBSERVED' else 0)


def test_expired_authorization_and_drill_never_contact_server():
    fetch = Mock()
    value, code = monitor.run(datetime(2027, 1, 1, 1, tzinfo=timezone.utc), fetch)
    assert code == 0 and value['state'] == 'SKIPPED_EXPIRED'
    value, code = monitor.run(datetime(2026, 11, 17, 9, tzinfo=timezone.utc),
                              fetch, notification_drill=True)
    assert code == 1 and value['state'] == 'ALERT_TRANSPORT_DRILL_NO_SERVER_REQUEST'
    fetch.assert_not_called()


@pytest.mark.parametrize('status,kind,body,reason', [
    (503, 'application/json', b'private-response', 'http_status'),
    (302, 'application/json', b'private-response', 'http_status'),
    (200, 'text/html', b'private-response', 'content_type'),
    (200, 'application/json', b'x' * 4097, 'response_too_large'),
    (200, 'application/json', b'private-response', 'invalid_json'),
    (200, 'application/json', b'{"status":"private-response"}', 'health_state'),
    (200, 'application/json', b'["private-response"]', 'health_state'),
])
def test_response_boundary_rejects_failure_without_exposing_body(status, kind, body, reason):
    with pytest.raises(monitor.ProbeFailure, match='^' + reason + '$'):
        monitor.validate_response(status, kind, body, 'ready')


def test_first_failure_stops_new_requests():
    fetch = Mock(side_effect=monitor.ProbeFailure('transport'))
    value, code = monitor.run(datetime(2026, 11, 17, 9, tzinfo=timezone.utc), fetch)
    assert code == 1 and value['category'] == 'transport'
    assert fetch.call_count == 1


def test_real_http_adapter_verifies_tls_and_bounds_read_without_auth_or_redirect():
    response = Mock(status=200)
    response.getheader.return_value = 'application/json; charset=utf-8'
    response.read.return_value = b'{"status":"ready","component":null}'
    connection = Mock()
    connection.getresponse.return_value = response
    with patch.object(monitor.http.client, 'HTTPSConnection', return_value=connection) as https:
        observed = monitor.get('/health/ready', 'ready')
    assert https.call_args.args == ('api-beta.go2china.space',)
    context = https.call_args.kwargs['context']
    assert context.check_hostname and context.verify_mode == monitor.ssl.CERT_REQUIRED
    assert https.call_args.kwargs['timeout'] == 10
    connection.request.assert_called_once_with('GET', '/health/ready', headers={
        'Accept': 'application/json', 'User-Agent': 'G2C-readiness-monitor/1'})
    response.read.assert_called_once_with(4097)
    connection.close.assert_called_once()
    assert observed['status'] == 200
    assert set(observed) == {'route', 'status', 'duration_ms'}


def test_transport_error_text_is_not_reported_and_connection_is_closed():
    connection = Mock()
    connection.request.side_effect = OSError('private-response')
    with patch.object(monitor.http.client, 'HTTPSConnection', return_value=connection):
        with pytest.raises(monitor.ProbeFailure, match='^transport$'):
            monitor.get('/health/live', 'alive')
    connection.close.assert_called_once()
